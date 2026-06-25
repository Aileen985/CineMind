# pool_builder.py
"""
热门/冷门池构建器（纯 TMDB API 版）
规则：按 TMDB popularity 从高到低排序
- 前 HOT_RATIO → 热门池（过滤：评分≥MIN_VOTE_AVG，票数≥MIN_VOTE_COUNT）
- 后 COLD_RATIO → 冷门池（过滤：评分≥MIN_VOTE_AVG，不在热门池）
- 中间部分 → 丢弃
"""

import requests
import os
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any

from db.pools import (
    save_hot_pool,
    save_cold_pool,
    update_pool_meta,
    init_table,
    get_pool_meta  # 现在可以导入了
)
from config import TMDB_API_KEY, POOL_DB_PATH,TMDB_BASE_URL

# ========== 配置 ==========

# 池子参数
HOT_RATIO = 0.30  # 热门区比例
COLD_RATIO = 0.35  # 冷门区比例
MIN_VOTE_AVG = 6.0  # 最低评分（10分制）
MIN_VOTE_COUNT = 50  # 最低票数（仅热门区要求）
MAX_PAGES = 50  # 最多获取页数（每页20条，总计1000条，可根据需要调整）
REQUEST_DELAY = 0.2  # 请求间隔（秒），避免触发限流


# ========== TMDB API 函数 ==========
def fetch_tmdb_movies(page: int) -> List[Dict[str, Any]]:
    """获取单页 TMDB 热门电影（已按 popularity 降序）"""
    url = f"{TMDB_BASE_URL}/movie/popular"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "zh-CN",
        "page": page
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("results", [])
        else:
            print(f"请求失败 {page}: {resp.status_code}")
            return []
    except Exception as e:
        print(f"请求异常 {page}: {e}")
        return []


def fetch_movie_details(tmdb_id: int) -> Dict[str, Any]:
    """获取单部电影的详细信息（用于补充 genres、overview 等）"""
    url = f"{TMDB_BASE_URL}/movie/{tmdb_id}"
    params = {
        "api_key": TMDB_API_KEY,
        "language": "zh-CN"
    }
    try:
        resp = requests.get(url, params=params, timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"获取详情失败 {tmdb_id}: {e}")
    return {}


def fetch_all_tmdb_movies(max_pages: int = MAX_PAGES) -> List[Dict[str, Any]]:
    """获取多页 TMDB 热门电影，合并并去重（TMDB 保证每页不重复）"""
    all_movies = []
    for page in range(1, max_pages + 1):
        movies = fetch_tmdb_movies(page)
        if not movies:
            break
        all_movies.extend(movies)
        print(f"已获取第 {page} 页，共 {len(movies)} 部电影，累计 {len(all_movies)} 部")
        time.sleep(REQUEST_DELAY)
    return all_movies


def enrich_movie_with_details(movie: Dict[str, Any]) -> Dict[str, Any]:
    """为电影补充 genres（中文）等缺失信息"""
    tmdb_id = movie["id"]
    details = fetch_movie_details(tmdb_id)
    if details:
        genres_list = [g["name"] for g in details.get("genres", [])]
        movie["genres"] = "|".join(genres_list) if genres_list else ""
    else:
        movie["genres"] = ""
    return movie


def build_pools(force_rebuild: bool = False):
    """
    构建热门池和冷门池
    调用 db.pools 的写入函数，不再直接操作数据库
    """
    # 确保数据库表存在（作为独立脚本运行时需要）
    init_table()

    # 检查是否需要重建（每天仅自动重建一次）
    if not force_rebuild:
        from db.pools import get_pool_meta
        last_build_str = get_pool_meta('last_build')
        if last_build_str:
            last_build = datetime.fromisoformat(last_build_str)
            if datetime.now() - last_build < timedelta(days=1):
                print(f"池子上次构建于 {last_build_str}，未超过24小时，跳过重建。使用 --force 强制重建。")
                return

    print("🏗️ 开始从 TMDB API 构建热门/冷门池...")

    # 1. 获取热门电影列表（已按 popularity 降序）
    movies = fetch_all_tmdb_movies(max_pages=MAX_PAGES)
    if not movies:
        print("❌ 未获取到任何电影数据")
        return

    print(f"总获取电影数: {len(movies)}")

    # 2. 补充详细信息（genres）
    print("正在补充电影类型信息...")
    for i, movie in enumerate(movies):
        movies[i] = enrich_movie_with_details(movie)
        if (i + 1) % 20 == 0:
            print(f"已处理 {i + 1}/{len(movies)} 部")
        time.sleep(REQUEST_DELAY)

    # 3. 按 popularity 排序（API 已排序，但确保一下）
    movies_sorted = sorted(movies, key=lambda x: x.get("popularity", 0), reverse=True)
    n = len(movies_sorted)

    hot_end = int(n * HOT_RATIO)
    cold_start = int(n * (HOT_RATIO + COLD_RATIO))

    print(f"热门区: 0 ~ {hot_end} (前 {HOT_RATIO * 100:.0f}%)")
    print(f"丢弃区: {hot_end} ~ {cold_start} (中间 {COLD_RATIO * 100:.0f}%)")
    print(f"冷门区: {cold_start} ~ {n} (后 {COLD_RATIO * 100:.0f}%)")

    # 4. 热门候选（前30%）
    hot_candidates = movies_sorted[:hot_end]
    hot_filtered = []
    for m in hot_candidates:
        vote_avg = m.get("vote_average", 0)
        vote_cnt = m.get("vote_count", 0)
        if vote_avg >= MIN_VOTE_AVG and vote_cnt >= MIN_VOTE_COUNT:
            hot_filtered.append(m)
    print(f"热门池候选: {len(hot_candidates)} → 过滤后: {len(hot_filtered)}")

    # 5. 冷门候选（后35%）
    cold_candidates = movies_sorted[cold_start:]
    hot_ids = {m["id"] for m in hot_filtered}
    cold_filtered = []
    for m in cold_candidates:
        vote_avg = m.get("vote_average", 0)
        if vote_avg >= MIN_VOTE_AVG and m["id"] not in hot_ids:
            cold_filtered.append(m)
    print(f"冷门池候选: {len(cold_candidates)} → 过滤后: {len(cold_filtered)}")

    # 6. 写入数据库（使用 db.pools 的写入函数）
    now = datetime.now().isoformat()

    save_hot_pool(hot_filtered)
    save_cold_pool(cold_filtered)
    update_pool_meta('last_build', now)
    update_pool_meta('hot_count', str(len(hot_filtered)))
    update_pool_meta('cold_count', str(len(cold_filtered)))

    print(f"✅ 池子构建完成: 热门池 {len(hot_filtered)} 部, 冷门池 {len(cold_filtered)} 部")
    return len(hot_filtered), len(cold_filtered)


# ========== 命令行入口 ==========
if __name__ == "__main__":
    import sys

    # 初始化表（由 db.pools 负责）
    init_table()

    force = "--force" in sys.argv
    build_pools(force_rebuild=force)