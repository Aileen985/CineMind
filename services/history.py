# services/history.py
"""
历史记录统计算法
"""
import json
from datetime import datetime
from collections import Counter
from db.profiles import get_text_profile
from services.llm import call_llm
from services.tmdb import get_tmdb_movie_info
from components import format_stars
from utils.logger import get_logger

logger = get_logger("history")


def get_history_stats(ratings):
    """计算评分统计"""
    if not ratings:
        return {"total": 0, "avg": 0, "high_count": 0, "top_genre": "无", "top_three": []}
    total = len(ratings)
    avg = sum(r["rating"] for r in ratings) / total
    high_count = sum(1 for r in ratings if r["rating"] > 4)
    genre_freq = {}
    for movie in ratings:
        for g in movie["genres"]:
            genre_freq[g] = genre_freq.get(g, 0) + 1
    sorted_genres = sorted(genre_freq.items(), key=lambda x: x[1], reverse=True)
    return {
        "total": total,
        "avg": round(avg, 2),
        "high_count": high_count,
        "top_genre": sorted_genres[0][0] if sorted_genres else "未知",
        "top_three": sorted_genres[:3]
    }


def prepare_trend_data(ratings):
    """准备月度趋势数据"""
    if not ratings:
        return [], []
    month_map = {}
    for r in ratings:
        month = r["date"][:7]
        if month not in month_map:
            month_map[month] = {"sum": 0, "count": 0}
        month_map[month]["sum"] += r["rating"]
        month_map[month]["count"] += 1
    months = sorted(month_map.keys())
    avg_ratings = [month_map[m]["sum"] / month_map[m]["count"] for m in months]
    return months, avg_ratings


def generate_llm_summary(ratings, stats, username):
    """生成 LLM 观影总结"""
    if not ratings:
        return "暂无评分数据，快去给电影评分吧！"
    recent_titles = [m["title"] for m in ratings[:5]]
    high_rated = [m["title"] for m in ratings if m["rating"] >= 4][:3]
    profile = get_text_profile(username)
    if profile:
        top_tags = profile.get('top_tags', [])
        top_atm = profile.get('top_atm_style', '')
        top_vis = profile.get('top_vis_style', '')
        profile_text = f"标签偏好：{', '.join(top_tags[:3])}。"
        if top_atm:
            profile_text += f" 偏爱 {top_atm} 氛围。"
        if top_vis:
            profile_text += f" 视觉风格倾向 {top_vis}。"
    else:
        profile_text = ""

    prompt = f"""你是一个专业的电影品味分析师。根据以下用户数据，生成一段有个性、有洞察力的观影总结（50-80字）。

数据：
- 总评分：{stats['total']} 部
- 平均分：{stats['avg']} / 5
- 高分电影（≥4分）：{stats['high_count']} 部
- 最喜欢的类型：{stats['top_genre']}
- 最近看过：{', '.join(recent_titles[:3])}
- 高分电影举例：{', '.join(high_rated) if high_rated else '无'}
- 用户画像：{profile_text}

要求：
1. 语气亲切自然，像朋友聊天
2. 分析观影偏好，指出风格倾向
3. 适当夸奖或调侃用户的品味
4. 末尾加一个简短的建议
5. 不要超过80字

请直接输出总结："""
    try:
        result = call_llm(prompt, max_tokens=200, temperature=0.7)
        return result
    except Exception as e:
        logger.error(f"DeepSeek 总结失败: {e}")
        return f"📊 基于你的 {stats['total']} 条评分记录，平均 {stats['avg']} 分，最爱 {stats['top_genre']} 类型。最近看了《{recent_titles[0]}》，值得继续探索！"


def export_ratings_json(ratings):
    """导出评分数据为 JSON"""
    export_data = [{
        "id": m["id"],
        "title": m["title"],
        "year": m["year"],
        "rating": m["rating"],
        "date": m["date"],
        "genres": m["genres"]
    } for m in ratings]
    return json.dumps(export_data, ensure_ascii=False, indent=2)


def get_poster_icon(genres):
    """获取类型对应的图标"""
    icon_map = {
        '科幻': '🚀', '动画': '🎨', '喜剧': '😄', '爱情': '💕', '悬疑': '🔍',
        '惊悚': '😱', '动作': '⚡', '冒险': '🗺️', '奇幻': '✨', '剧情': '📖',
        '恐怖': '👻', '纪录片': '📹'
    }
    for g in genres:
        if g in icon_map:
            return icon_map[g]
    return '🎬'