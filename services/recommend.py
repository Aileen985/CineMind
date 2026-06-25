# services/recommend.py
"""
推荐算法
"""
import random
import numpy as np
import tempfile
import os
import requests
from services.search import text_search, image_search, get_image_collection
from services.tmdb import get_tmdb_movie_info
from services.llm import call_llm
from services.llm import get_or_generate_reason
from services.cache import CacheTTL
from db.ratings import get_user_ratings as get_ratings_from_db
from db.pools import get_hot_pool, get_cold_pool
from db.profiles import get_text_profile, get_visual_profile
from db.movie_cache import get_cached_classify
from components import convert_to_5_star
from config import TMDB_API_KEY, TMDB_IMAGE_BASE
import streamlit as st
from utils.logger import get_logger

logger = get_logger("recommend")


# ================== CLIP 向量 ==================
def get_movie_poster_embedding(tmdb_id):
    try:
        collection = get_image_collection()
        if collection is None:
            return None
        results = collection.get(ids=[str(tmdb_id)], include=["embeddings"])
        embeddings = results.get('embeddings')
        # 不要直接 if embeddings，而是检查是否存在且长度 > 0
        if embeddings is not None and len(embeddings) > 0:
            embedding = embeddings[0]
            if embedding is not None:
                # 若 embedding 是 NumPy 数组，检查其 size；否则检查长度
                if isinstance(embedding, np.ndarray):
                    if embedding.size == 0:
                        return None
                elif not isinstance(embedding, (list, tuple)) or len(embedding) == 0:
                    return None
                return np.array(embedding)
    except Exception as e:
        logger.error(f"获取海报向量失败: {e}")
    return None

# ================== 辅助函数 ==================
def get_user_top_movie_info(username):
    """获取用户评分最高的电影信息"""
    ratings = get_ratings_from_db(username)
    if not ratings:
        return None
    sorted_ratings = sorted(ratings, key=lambda x: x[1], reverse=True)
    top_tmdb_id = sorted_ratings[0][0]
    top_info = get_tmdb_movie_info(top_tmdb_id)
    if top_info and top_info.get('poster_url'):
        return top_info
    return None

def get_random_movies_cached(count=20):
    """获取随机电影（带缓存）"""
    import random
    from services.tmdb import fetch_tmdb_movies, get_movie_detail
    from services.llm import get_or_generate_reason

    page = random.randint(1, 20)
    movies = fetch_tmdb_movies(page=page)
    if not movies:
        return []

    random.shuffle(movies)
    detailed = []
    for m in movies[:count]:
        detail = get_movie_detail(m.get('id'))
        if detail and detail.get('vote_average', 0) >= 3:
            reason = get_or_generate_reason(detail['id'], detail['title'], "随机推荐")
            detail['reason'] = reason
            detailed.append(detail)
    return detailed or []


# ================== 个性化推荐 ==================
def get_personalized_recommendations(username, top_k=12):
    """多路召回个性化推荐（核心算法）"""
    import numpy as np
    import random

    text_profile = get_text_profile(username)
    visual_vec = get_visual_profile(username)

    if not text_profile or text_profile.get('total_count', 0) == 0:
        hot = get_hot_pool(limit=top_k)
        if not hot:
            return text_search("popular movies", top_k=top_k, username=username)
        result = hot[:int(top_k * 0.7)]
        extra = text_search("popular movies", top_k=top_k * 2, username=username)
        hot_ids = {h.get('tmdb_id') or h.get('id') for h in hot}
        extra = [m for m in extra if (m.get('tmdbId') or m.get('movieId')) not in hot_ids]
        selected_genres = set()
        for m in result:
            g = m.get('genres', '').split('|')[0] if m.get('genres') else ''
            if g:
                selected_genres.add(g)
        for m in extra:
            if len(result) >= top_k:
                break
            g = m.get('genres', '').split('|')[0] if m.get('genres') else ''
            if g and g not in selected_genres:
                result.append(m)
                selected_genres.add(g)
        if len(result) < top_k:
            result.extend(extra[:top_k - len(result)])
        return result

    user_tags = set(text_profile.get('top_tags', [])[:5])
    user_atm = text_profile.get('top_atm_style')
    user_vis = text_profile.get('top_vis_style')
    user_fav_types = text_profile.get('top_tags', [])[:2]

    candidates = []
    seen_ids = set()

    # 路径1: 文本语义召回
    profile_text = f"{', '.join(user_tags[:3])} 电影" if user_tags else "popular movies"
    text_recs = text_search(profile_text, top_k=30, username=username)
    for m in text_recs:
        mid = m.get('tmdbId') or m.get('movieId')
        if mid and mid not in seen_ids:
            seen_ids.add(mid)
            candidates.append(m)

    # 路径2: 热门池召回
    hot_pool = get_hot_pool(limit=30)
    for m in hot_pool:
        mid = m.get('tmdb_id')
        if mid and mid not in seen_ids:
            seen_ids.add(mid)
            candidates.append(m)

    # 路径3: 用户高分种子扩展
    ratings = get_ratings_from_db(username)
    high_rated = [mid for mid, rating, _ in ratings if rating >= 4][:5]
    if high_rated:
        for seed_id in high_rated:
            seed_info = get_tmdb_movie_info(seed_id)
            if seed_info and seed_info.get('title'):
                seed_recs = text_search(seed_info['title'], top_k=5, username=username)
                for m in seed_recs:
                    mid = m.get('tmdbId') or m.get('movieId')
                    if mid and mid not in seen_ids:
                        seen_ids.add(mid)
                        candidates.append(m)

    # 路径4: 类型定向召回
    for fav_type in user_fav_types:
        if fav_type:
            type_recs = text_search(fav_type, top_k=10, username=username)
            for m in type_recs:
                mid = m.get('tmdbId') or m.get('movieId')
                if mid and mid not in seen_ids:
                    seen_ids.add(mid)
                    candidates.append(m)

    if not candidates:
        return text_search("popular movies", top_k=top_k, username=username)

    scored = []
    for movie in candidates:
        tmdb_id = movie.get('tmdbId') or movie.get('movieId')
        if not tmdb_id:
            continue

        tags_info = get_cached_classify(tmdb_id)
        if tags_info:
            movie_tags = set(tags_info.get('tags', [])[:5])
            movie_atm = tags_info.get('atmosphere_style')
            movie_vis = tags_info.get('visual_style')
        else:
            movie_tags = set(movie.get('genres', '').split('|'))
            movie_atm = None
            movie_vis = None

        tag_sim = len(user_tags & movie_tags) / max(len(user_tags | movie_tags), 1) if user_tags and movie_tags else 0.0
        movie_types = set(movie.get('genres', '').split('|'))
        type_overlap = len(set(user_fav_types) & movie_types) / max(len(set(user_fav_types)), 1) if user_fav_types else 0.0

        vis_sim = 0.0
        if visual_vec is not None:
            movie_vec = get_movie_poster_embedding(tmdb_id)
            if movie_vec is not None:
                vis_sim = float(np.dot(visual_vec, movie_vec))

        seed_sim = 0.0
        if visual_vec is not None and high_rated:
            movie_vec = get_movie_poster_embedding(tmdb_id)
            if movie_vec is not None:
                seed_sim = float(np.dot(visual_vec, movie_vec))

        style_score = 0.0
        if user_atm and movie_atm and user_atm == movie_atm:
            style_score += 0.5
        if user_vis and movie_vis and user_vis == movie_vis:
            style_score += 0.5

        pop = movie.get('popularity', 0)
        norm_pop = min(pop / 200, 1.0)

        score = (0.25 * tag_sim +
                 0.15 * type_overlap +
                 0.20 * vis_sim +
                 0.15 * seed_sim +
                 0.15 * style_score +
                 0.10 * norm_pop)

        scored.append({
            'movie': movie,
            'score': score,
            'genre': movie.get('genres', '').split('|')[0] if movie.get('genres') else '其他',
            'director': movie.get('director', '')
        })

    scored.sort(key=lambda x: x['score'], reverse=True)

    genre_groups = {}
    for item in scored:
        genre = item['genre']
        genre_groups.setdefault(genre, []).append(item)

    diversified = []
    used_directors = {}

    while len(diversified) < top_k and genre_groups:
        for genre in list(genre_groups.keys()):
            if not genre_groups[genre]:
                del genre_groups[genre]
                continue
            item = genre_groups[genre].pop(0)
            director = item.get('director', '')
            if director:
                used_directors[director] = used_directors.get(director, 0) + 1
                if used_directors[director] > 2:
                    genre_groups[genre].append(item)
                    continue
            diversified.append(item['movie'])
            if len(diversified) >= top_k:
                break
        for genre in list(genre_groups.keys()):
            if not genre_groups[genre]:
                del genre_groups[genre]

    if len(diversified) < top_k:
        remaining = [item['movie'] for item in scored if item['movie'] not in diversified]
        diversified.extend(remaining[:top_k - len(diversified)])

    return diversified


# ================== 视觉相似 ==================
@st.cache_data(ttl=CacheTTL.SHORT)
def get_visual_similar_movies(poster_url, top_k=12):
    """基于海报的视觉相似检索"""
    if not poster_url:
        return []
    try:
        response = requests.get(poster_url, timeout=10)
        if response.status_code != 200:
            return []
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as f:
            f.write(response.content)
            temp_path = f.name
        results = image_search(temp_path, top_k=top_k)
        os.unlink(temp_path)
        return results
    except Exception as e:
        logger.error(f"视觉检索失败: {e}")
        return []


def get_visual_recommendations(username, top_k=6, exclude_ids=None):
    """视觉同源推荐"""
    user_visual = get_visual_profile(username)
    text_profile = get_text_profile(username)

    candidates = []
    seen_ids = set()

    if user_visual is not None:
        collection = get_image_collection()
        if collection is not None:
            try:
                results = collection.query(
                    query_embeddings=[user_visual.tolist()],
                    n_results=top_k * 8,
                    include=["metadatas", "distances"]
                )
                for meta, dist in zip(results['metadatas'][0], results['distances'][0]):
                    mid = meta.get('movieId')
                    if mid and mid not in seen_ids:
                        if exclude_ids and mid in exclude_ids:
                            continue
                        seen_ids.add(mid)
                        candidates.append({
                            'movie_id': int(mid),
                            'vis_sim': 1 - dist,
                            'title': meta.get('title', ''),
                            'poster_path': meta.get('poster_path', '')
                        })
            except Exception as e:
                logger.error(f"向量查询失败: {e}")

    top_movie = get_user_top_movie_info(username)
    if top_movie and top_movie.get('poster_url'):
        seed_results = get_visual_similar_movies(top_movie['poster_url'], top_k=30)
        for m in seed_results:
            mid = m.get('movieId')
            if mid and mid not in seen_ids:
                if exclude_ids and mid in exclude_ids:
                    continue
                seen_ids.add(mid)
                candidates.append({
                    'movie_id': mid,
                    'vis_sim': m.get('similarity', 0),
                    'title': m.get('title', ''),
                    'poster_path': m.get('poster_path', '')
                })

    if len(candidates) < top_k:
        logger.info(f"视觉候选不足 ({len(candidates)}), 从热门池补充")
        hot_pool = get_hot_pool(limit=20)
        for m in hot_pool:
            mid = m.get('tmdb_id')
            if mid and mid not in seen_ids:
                if exclude_ids and mid in exclude_ids:
                    continue
                seen_ids.add(mid)
                candidates.append({
                    'movie_id': mid,
                    'vis_sim': 0.3,
                    'title': m.get('title', ''),
                    'poster_path': m.get('poster_path', '')
                })
                if len(candidates) >= top_k * 2:
                    break

    if not candidates:
        return []

    user_vis_style = text_profile.get('top_vis_style') if text_profile else None
    user_atm_style = text_profile.get('top_atm_style') if text_profile else None
    user_tags = set(text_profile.get('top_tags', [])[:5]) if text_profile else set()

    scored = []
    for c in candidates:
        mid = c['movie_id']
        tags_info = get_cached_classify(mid)
        if tags_info:
            movie_tags = set(tags_info.get('tags', [])[:5])
            movie_vis = tags_info.get('visual_style')
            movie_atm = tags_info.get('atmosphere_style')
        else:
            movie_tags = set()
            movie_vis = None
            movie_atm = None

        style_match = 1.0 if (user_vis_style and movie_vis and user_vis_style == movie_vis) else 0.0
        atm_match = 1.0 if (user_atm_style and movie_atm and user_atm_style == movie_atm) else 0.0
        tag_sim = len(user_tags & movie_tags) / max(len(user_tags | movie_tags), 1) if user_tags and movie_tags else 0.0

        score = 0.45 * c['vis_sim'] + 0.20 * style_match + 0.15 * atm_match + 0.10 * tag_sim
        scored.append({
            'movie': c,
            'score': score,
            'vis_style': movie_vis,
        })

    scored.sort(key=lambda x: x['score'], reverse=True)

    style_count = {}
    final = []
    style_limit = 3 if len(scored) > 10 else 4

    for item in scored:
        style = item['vis_style'] or '未知'
        if style_count.get(style, 0) >= style_limit:
            continue
        final.append(item['movie'])
        style_count[style] = style_count.get(style, 0) + 1
        if len(final) >= top_k:
            break

    if len(final) < top_k:
        remaining = [item['movie'] for item in scored if item['movie'] not in final]
        final.extend(remaining[:top_k - len(final)])

    enriched = []
    for m in final[:top_k]:
        mid = m['movie_id']
        detail = get_tmdb_movie_info(mid)
        if detail:
            enriched.append({
                'tmdb_id': mid,
                'title': detail.get('title', m.get('title', '')),
                'genres_ch': detail.get('genres', ''),
                'rating_ch': convert_to_5_star(detail.get('vote_average', 0)),
                'poster_url': detail.get('poster_url'),
            })
        else:
            enriched.append({
                'tmdb_id': mid,
                'title': m.get('title', ''),
                'genres_ch': '',
                'rating_ch': 0,
                'poster_url': f"{TMDB_IMAGE_BASE}{m.get('poster_path')}" if m.get('poster_path') else None,
            })
    return enriched[:top_k]


# ================== 冷门宝藏 ==================
def get_cold_recommendations(username, top_k=6, exclude_ids=None):
    """冷门宝藏推荐"""
    cold_movies = get_cold_pool(limit=top_k * 8)
    if not cold_movies:
        return []

    pops = [m.get('popularity', 0) for m in cold_movies]
    max_pop = max(pops) if pops else 1
    for m in cold_movies:
        pop = m.get('popularity', 0)
        S_cold = max(0.05, min(1, 1 - (pop / max_pop) if max_pop > 0 else 0))
        m['S_cold'] = S_cold

        vote_avg = m.get('vote_average', 0) / 10
        vote_cnt_norm = min(m.get('vote_count', 0) / 1000, 1)
        base_gem = 0.6 * vote_avg + 0.4 * vote_cnt_norm
        genres = m.get('genres', '')
        positive_genres = ['Documentary', 'Drama', 'Animation', 'History', 'War', 'Western']
        genre_bonus = 0.1 if any(g in genres for g in positive_genres) else 0
        S_gem = min(1, base_gem + genre_bonus)
        m['S_gem'] = S_gem

    cold_movies = [m for m in cold_movies if m.get('S_gem', 0) >= 0.35]
    if not cold_movies:
        return []

    text_profile = get_text_profile(username)
    visual_profile = get_visual_profile(username)
    user_tags = set(text_profile.get('top_tags', [])[:5]) if text_profile else set()
    user_atm = text_profile.get('top_atm_style') if text_profile else None
    user_vis = text_profile.get('top_vis_style') if text_profile else None

    ratings = get_ratings_from_db(username)
    if ratings:
        all_pops = [m.get('popularity', 0) for m in cold_movies]
        median_pop = np.median(all_pops) if all_pops else 0
        cold_like_count = 0
        total_high = 0
        for tmdb_id, rating, _ in ratings:
            if rating < 4:
                continue
            total_high += 1
            for m in cold_movies:
                if m.get('tmdb_id') == tmdb_id:
                    if m.get('popularity', 0) < median_pop:
                        cold_like_count += 1
                    break
        cold_ratio = cold_like_count / total_high if total_high > 0 else 0

        common_genres = {'Action', 'Adventure', 'Comedy', 'Drama', 'Romance', 'Sci-Fi', 'Thriller', 'Horror', 'Animation'}
        rare_tag_count = sum(1 for tag in user_tags if tag not in common_genres) if user_tags else 0
        rarity_factor = min(1, rare_tag_count / 3)

        if cold_ratio < 0.15 and rarity_factor < 0.3:
            level_factor = 0.3
        elif cold_ratio < 0.4 or rarity_factor < 0.6:
            level_factor = 0.6
        else:
            level_factor = 1.0
    else:
        level_factor = 0.5

    scored = []
    for m in cold_movies:
        tmdb_id = m.get('tmdb_id')
        if exclude_ids and tmdb_id in exclude_ids:
            continue

        tags_info = get_cached_classify(tmdb_id)
        if tags_info:
            movie_tags = set(tags_info.get('tags', [])[:5])
            movie_atm = tags_info.get('atmosphere_style')
            movie_vis = tags_info.get('visual_style')
        else:
            genres = set(m.get('genres', '').split('|'))
            movie_tags = genres
            movie_atm = None
            movie_vis = None

        tag_sim = len(user_tags & movie_tags) / max(len(user_tags | movie_tags), 1) if user_tags and movie_tags else 0
        atm_match = 1.0 if user_atm and movie_atm and user_atm == movie_atm else 0.0
        vis_match = 1.0 if user_vis and movie_vis and user_vis == movie_vis else 0.0
        vis_vec_sim = 0.0
        if visual_profile is not None:
            movie_vec = get_movie_poster_embedding(tmdb_id)
            if movie_vec is not None:
                vis_vec_sim = float(np.dot(visual_profile, movie_vec))

        match_score = (0.4 * tag_sim + 0.2 * atm_match + 0.2 * vis_match + 0.2 * vis_vec_sim)
        S_cold = m.get('S_cold', 0)
        S_gem = m.get('S_gem', 0)
        score = S_cold * S_gem * (0.7 * match_score + 0.3 * level_factor)
        scored.append((m, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    selected = [m for m, _ in scored[:top_k]]

    enriched = []
    for m in selected:
        tmdb_id = m.get('tmdb_id')
        if tmdb_id:
            detail = get_tmdb_movie_info(tmdb_id)
            if detail:
                enriched.append({
                    'tmdb_id': tmdb_id,
                    'title': detail.get('title', m.get('title', '')),
                    'genres_ch': detail.get('genres', ''),
                    'rating_ch': convert_to_5_star(detail.get('vote_average', 0)),
                    'poster_url': detail.get('poster_url'),
                })
            else:
                enriched.append({
                    'tmdb_id': tmdb_id,
                    'title': m.get('title', ''),
                    'genres_ch': m.get('genres', '').replace('|', ' · '),
                    'rating_ch': convert_to_5_star(m.get('vote_average', 0)),
                    'poster_url': f"{TMDB_IMAGE_BASE}{m.get('poster_path')}" if m.get('poster_path') else None,
                })
    return enriched


# ================== 批量生成推荐理由 ==================
def generate_batch_reasons(movies, user_profile_text, context="推荐"):
    """批量生成推荐理由"""
    if not movies:
        return []
    movie_lines = "\n".join([f"{i + 1}. 《{m['title']}》" for i, m in enumerate(movies)])
    prompt = f"""用户偏好：{user_profile_text}
请为以下{len(movies)}部电影分别生成一句{context}理由（20字以内），突出与用户偏好的契合点。
按顺序输出，用分号隔开，不要编号。

电影列表：
{movie_lines}
理由："""
    try:
        result = call_llm(prompt, max_tokens=200)
        reasons = [r.strip() for r in result.split('；') if r.strip()]
        while len(reasons) < len(movies):
            reasons.append("值得一看")
        return reasons
    except Exception as e:
        logger.error(f"批量生成理由失败: {e}")
        return ["值得一看"] * len(movies)


