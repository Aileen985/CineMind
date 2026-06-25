# services/search.py
"""
检索服务：文本检索、图像检索、多模态融合检索
"""
import os
import random
import numpy as np
import ollama
import chromadb
import torch
import pandas as pd
from PIL import Image

from db.preferences import get_user_disliked_movies
from services.models import (
    get_text_collection,
    get_image_collection,
    get_clip_model,
    _load_clip,
    generate_blip_description,
)

from db.preferences import get_user_disliked_movies
from config import CHROMA_FEATURE_PATH, CHROMA_RECALL_PATH, TMDB_CSV_PATH


# ---------- 文本检索 ----------
def text_search(query, top_k=10, username=None, exclude_ids=None):
    """
    基于 BGE-M3 的文本检索
    返回电影列表，增加多样性
    """
    collection = get_text_collection()
    try:
        resp = ollama.embeddings(model='bge-m3', prompt=query)
        q_vec = np.array(resp['embedding'], dtype=np.float32)
        q_vec = q_vec / np.linalg.norm(q_vec)
    except Exception as e:
        print(f"Ollama 错误: {e}")
        return []

    n_results = top_k * 3 if exclude_ids else top_k * 2
    results = collection.query(
        query_embeddings=[q_vec.tolist()],
        n_results=n_results,
        include=["metadatas", "distances"]
    )

    recs = []
    for meta, dist in zip(results['metadatas'][0], results['distances'][0]):
        recs.append({
            'movieId': int(meta['movieId']),
            'title': meta['title'],
            'tmdbId': int(meta.get('tmdbId', 0)),
            'genres': meta['genres'],
            'similarity': 1 - dist
        })

    # 排除已推荐的
    if exclude_ids:
        recs = [r for r in recs if r['movieId'] not in exclude_ids]

    # 排除不喜欢的
    if username:
        disliked = get_user_disliked_movies(username)
        recs = [r for r in recs if r['movieId'] not in disliked]

    # 随机打乱前30%，增加多样性
    if len(recs) > top_k:
        import random
        top_n = max(top_k, len(recs) // 3)
        top_candidates = recs[:top_n]
        random.shuffle(top_candidates)
        recs = top_candidates + recs[top_n:]

    return recs[:top_k]


def text_search_bge(query, top_k=80):
    """
    基于 BGE-M3 的文本检索（原始版本，用于混合推荐）
    """
    resp = ollama.embeddings(model='bge-m3', prompt=query)
    q_vec = np.array(resp['embedding'], dtype=np.float32)
    q_vec = q_vec / np.linalg.norm(q_vec)
    client = chromadb.PersistentClient(path=CHROMA_RECALL_PATH)
    collection = client.get_collection("movies_bge_m3")
    results = collection.query(
        query_embeddings=[q_vec.tolist()],
        n_results=top_k,
        include=["metadatas", "distances"]
    )
    recs = []
    for meta, dist in zip(results['metadatas'][0], results['distances'][0]):
        recs.append({
            'movieId': int(meta['movieId']),
            'title': meta['title'],
            'genres': meta['genres'],
            'sim': 1 - dist
        })
    return recs


# ---------- 图像检索 ----------
def image_search(image_path, top_k=10):
    """
    基于 CLIP 的图像检索（用户级）
    """
    model, processor = get_clip_model()
    device = next(model.parameters()).device
    image = Image.open(image_path).convert("RGB")
    inputs = processor(images=image, return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.no_grad():
        vision_outputs = model.vision_model(pixel_values=inputs['pixel_values'])
        pooled = vision_outputs.pooler_output
        projected = model.visual_projection(pooled)
    feat = projected[0].cpu().numpy()
    feat = feat / np.linalg.norm(feat)
    query_emb = [feat.tolist()]
    client = chromadb.PersistentClient(path=CHROMA_FEATURE_PATH)
    collection = client.get_collection("movie_posters")
    results = collection.query(
        query_embeddings=query_emb,
        n_results=top_k,
        include=["metadatas", "distances"]
    )
    recs = []
    for meta, dist in zip(results['metadatas'][0], results['distances'][0]):
        recs.append({
            'movieId': int(meta['movieId']),
            'title': meta['title'],
            'genres': meta['genres'],
            'similarity': 1 - dist
        })
    return recs


def image_search_clip(image_path, top_k=80):
    """
    基于 CLIP 的视觉相似检索（用于混合推荐）
    """
    model, processor = _load_clip()
    device = next(model.parameters()).device
    image = Image.open(image_path).convert("RGB")
    inputs = processor(images=image, return_tensors="pt").to(device)
    with torch.no_grad():
        vision_outputs = model.vision_model(pixel_values=inputs['pixel_values'])
        pooled = vision_outputs.pooler_output
        projected = model.visual_projection(pooled)
    vec = projected[0].cpu().numpy()
    vec = vec / np.linalg.norm(vec)
    client = chromadb.PersistentClient(path=CHROMA_FEATURE_PATH)
    collection = client.get_collection("movie_posters")
    results = collection.query(
        query_embeddings=[vec.tolist()],
        n_results=top_k,
        include=["metadatas", "distances"]
    )
    recs = []
    for meta, dist in zip(results['metadatas'][0], results['distances'][0]):
        recs.append({
            'movieId': int(meta['movieId']),
            'title': meta['title'],
            'genres': meta['genres'],
            'sim': 1 - dist
        })
    return recs


def clip_text_search_for_images(query_text, top_k=10):
    """
    使用 CLIP 文本编码器检索图像库
    """
    model, processor = get_clip_model()
    device = next(model.parameters()).device
    inputs = processor(text=[query_text], return_tensors="pt", padding=True, truncation=True, max_length=77)
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.no_grad():
        text_emb = model.get_text_features(**inputs)
    query_vec = text_emb[0].cpu().numpy()
    query_vec = query_vec / np.linalg.norm(query_vec)
    query_emb = [query_vec.tolist()]
    client = chromadb.PersistentClient(path=CHROMA_FEATURE_PATH)
    try:
        collection = client.get_collection("movie_posters")
    except:
        raise Exception("集合 'movie_posters' 不存在，请先运行构建脚本")
    results = collection.query(
        query_embeddings=query_emb,
        n_results=top_k,
        include=["metadatas", "distances"]
    )
    recs = []
    for meta, dist in zip(results['metadatas'][0], results['distances'][0]):
        recs.append({
            'movieId': int(meta['movieId']),
            'title': meta['title'],
            'genres': meta['genres'],
            'similarity': 1 - dist
        })
    return recs


# ---------- 多模态融合 ----------
def rrf_fusion(text_recs, img_recs, top_k=8, k=60):
    """
    Reciprocal Rank Fusion (RRF) 融合文本和图像检索结果
    """
    scores = {}
    for idx, rec in enumerate(text_recs):
        scores[rec['movieId']] = scores.get(rec['movieId'], 0) + 1 / (k + idx + 1)
    for idx, rec in enumerate(img_recs):
        scores[rec['movieId']] = scores.get(rec['movieId'], 0) + 1 / (k + idx + 1)
    sorted_ids = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
    result = []
    for mid, _ in sorted_ids:
        for r in text_recs + img_recs:
            if r['movieId'] == mid:
                result.append(r)
                break
    return result


def multi_modal_search(query_text, image_path, mode, top_k=8):
    """
    根据模式执行多模态检索
    mode: text, image, caption, fusion
    """
    if mode == "text":
        return text_search(query_text, top_k)
    elif mode == "image":
        if image_path and os.path.exists(image_path):
            return image_search(image_path, top_k)
        else:
            return []
    elif mode == "caption":
        return clip_text_search_for_images(query_text, top_k)
    elif mode == "fusion":
        text_recs = text_search(query_text, top_k=20) if query_text else []
        img_recs = []
        if image_path and os.path.exists(image_path):
            img_recs = image_search(image_path, top_k=20)
        return rrf_fusion(text_recs, img_recs, top_k)
    else:
        return []


# ---------- 混合推荐（视觉 + 文本 + 类型/导演加权） ----------
def hybrid_recommendation(image_path, alpha=0.4, genre_bonus=0.01, director_bonus=0.05, top_k=10):
    """
    多模态混合推荐（视觉 + 文本 + 类型/导演加权）
    """
    import pandas as pd

    # 1. 并行检索
    vis_list = image_search_clip(image_path, top_k=80)
    if not vis_list:
        return []
    blip_desc = generate_blip_description(image_path)
    txt_list = text_search_bge(blip_desc, top_k=80)

    # 2. 基础融合分（线性衰减排名）
    scores = {}
    for idx, m in enumerate(vis_list):
        scores[m['movieId']] = alpha * (1 - idx / 80)
    for idx, m in enumerate(txt_list):
        mid = m['movieId']
        scores[mid] = scores.get(mid, 0) + (1 - alpha) * (1 - idx / 80)

    # 3. 获取目标电影的信息（用于加分的基准）
    df = pd.read_csv(TMDB_CSV_PATH)
    target_mid = vis_list[0]['movieId']
    target_row = df[df['movieId'] == target_mid]
    if target_row.empty:
        return []
    target_row = target_row.iloc[0]
    target_genres = set(target_row['genres'].split('|'))
    target_dir = target_row.get('director', '')
    target_dir_keyword = target_dir.split()[-1] if target_dir and pd.notna(target_dir) else None

    # 4. 构建最终候选（按总分排序）
    candidate_movies = []
    for mid, base_score in scores.items():
        row = df[df['movieId'] == mid]
        if row.empty:
            continue
        row = row.iloc[0]
        total = base_score
        curr_genres = set(row['genres'].split('|'))
        overlap = len(target_genres & curr_genres)
        total += overlap * genre_bonus
        if target_dir_keyword and pd.notna(row.get('director')) and target_dir_keyword in str(row['director']):
            total += director_bonus
        candidate_movies.append({
            'movieId': mid,
            'title': row['title'],
            'genres': row['genres'],
            'director': row.get('director', ''),
            'score': total
        })

    candidate_movies.sort(key=lambda x: x['score'], reverse=True)
    return candidate_movies[:top_k]