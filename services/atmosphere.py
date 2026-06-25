# services/atmosphere.py
"""
氛围分析服务
"""
import os
import json
import requests
# services/atmosphere.py
"""
氛围分析服务（修复视觉风格筛选）
"""
import os
import json
import requests
from datetime import datetime
from services.llm import call_llm
from services.models import generate_blip_description
from db.movie_cache import get_cached_classify, save_classify_to_db, get_cached_atmosphere, save_cached_atmosphere
from services.llm import call_deepseek
from services.tmdb import get_movie_detail
from utils.logger import get_logger

logger = get_logger("atmosphere")

ATM_STYLES = ["奇幻穹宇", "怅然回望", "暗影谜踪", "其他"]


def get_or_analyze_atmosphere(tmdb_id, title, overview):
    """获取或分析氛围风格"""
    cached = get_cached_classify(tmdb_id)
    if cached and cached.get('atmosphere_style'):
        return cached['atmosphere_style']
    from movie_detail import analyze_atmosphere_style
    atmosphere = analyze_atmosphere_style(title, overview)
    if atmosphere:
        save_classify_to_db(tmdb_id, title, "", None, atmosphere, [])
    return atmosphere


def get_or_analyze_visual(tmdb_id, poster_url):
    """获取或分析视觉风格（增加缓存和容错）"""
    cached = get_cached_classify(tmdb_id)
    if cached and cached.get('visual_style'):
        return cached['visual_style']
    if not poster_url:
        return None
    visual = analyze_visual_style(poster_url)
    if visual:
        save_classify_to_db(tmdb_id, "", "", visual, None, [])
    else:
        pass
    return visual


def filter_movies_by_atmosphere(movies, target_atmosphere, top_k=12):
    """按氛围筛选电影"""
    if not movies:
        return []
    results = []
    for movie in movies[:150]:
        if len(results) >= top_k:
            break
        tmdb_id = movie.get('id')
        detail = get_movie_detail(tmdb_id)
        if not detail or detail.get('vote_average', 0) < 3:
            continue
        atmosphere = get_or_analyze_atmosphere(detail['id'], detail['title'], detail['overview'])
        if atmosphere == target_atmosphere:
            detail['atmosphere'] = atmosphere
            results.append(detail)
    return results


# ================== 关键修改：filter_movies_by_style ==================
def filter_movies_by_style(movies, target_style, top_k=12):
    if not movies:
        return []
    results = []
    for movie in movies[:150]:
        if len(results) >= top_k:
            break
        tmdb_id = movie.get('id')
        detail = get_movie_detail(tmdb_id)
        if not detail:
            continue
        if detail.get('vote_average', 0) < 2.5:
            continue
        visual = get_or_analyze_visual(detail['id'], detail['poster_url'])
        if visual is None:
            continue
        if visual == target_style or target_style in visual or visual in target_style:
            detail['visual_style'] = visual
            from services.llm import get_or_generate_reason
            reason = get_or_generate_reason(detail['id'], detail['title'], f"视觉风格：{target_style}")
            detail['reason'] = reason
            results.append(detail)
    return results


# ================== 修改 analyze_visual_style ==================
def analyze_visual_style(poster_url):
    """
    实时分析视觉风格（增强容错与模糊匹配）
    """
    if not poster_url:
        return None

    try:
        # 增加超时和错误处理
        response = requests.get(poster_url, timeout=10)
        response.raise_for_status()
        temp_path = "temp_poster.jpg"
        with open(temp_path, 'wb') as f:
            f.write(response.content)

        visual_desc = generate_blip_description(temp_path)
        if not visual_desc:
            logger.warning(f"BLIP 描述生成失败: {poster_url}")
            return None

        # 增强 prompt，提供更清晰的风格定义
        prompt = f"""根据以下电影海报的视觉描述，判断它属于哪种视觉风格。

视觉描述: {visual_desc}

风格选项（只选一个）:
- 复古影调：怀旧、胶片感、暖色调、颗粒感
- 日常质感：自然光、生活化、真实感、低饱和度
- 清冷静谧：冷色调、蓝色/灰色、空旷、安静
- 柔光梦镜：柔和光线、梦幻、模糊边缘、浪漫
- 风格显影：高对比、鲜艳色彩、明显调色、艺术化

只输出风格名称，不要解释、不要加标点。"""
        result = call_llm(prompt, max_tokens=20)
        if not result:
            return None

        # 清理结果：去空格、去标点
        result = result.strip().replace("。", "").replace("，", "").replace("：", "")
        valid_styles = ["复古影调", "日常质感", "清冷静谧", "柔光梦镜", "风格显影"]

        # 优先精确匹配
        if result in valid_styles:
            return result
        # 否则模糊匹配（包含关系）
        for style in valid_styles:
            if style in result or result in style:
                return style
        # 无法匹配则记录并返回 None
        logger.warning(f"无法匹配的视觉风格: {result}")
        return None
    except Exception as e:
        logger.error(f"视觉风格分析失败: {e}")
        return None



def analyze_atmosphere_with_cache(tmdb_id, title, overview, genres_list):
    """分析并缓存氛围风格（home.py 用）"""
    genres_str = '、'.join(genres_list) if genres_list else '未提供'
    overview_text = overview[:300] if overview else '无简介'
    prompt = f"""电影《{title}》
类型：{genres_str}
简介：{overview_text}

请判断这部电影最符合以下哪种氛围风格（只输出一个词）：
- 奇幻穹宇（奇幻、科幻、魔法、冒险、宇宙、动画）
- 怅然回望（伤感、怀旧、回忆、人生、悲剧）
- 暗影谜踪（悬疑、黑暗、神秘、犯罪、恐怖、惊悚）
- 其他（如果都不符合）

输出："""
    result = call_deepseek(prompt, max_tokens=20)
    if "奇幻穹宇" in result:
        atmosphere = "奇幻穹宇"
    elif "怅然回望" in result:
        atmosphere = "怅然回望"
    elif "暗影谜踪" in result:
        atmosphere = "暗影谜踪"
    else:
        atmosphere = "其他"
    save_cached_atmosphere(tmdb_id, atmosphere)
    return atmosphere


def get_or_analyze_atmosphere_with_cache(tmdb_id, title, overview, genres_list):
    """获取或分析氛围（带独立缓存表，home.py 用）"""
    cached = get_cached_atmosphere(tmdb_id)
    if cached:
        return cached
    return analyze_atmosphere_with_cache(tmdb_id, title, overview, genres_list)


def analyze_atmosphere_style(title, overview):
    """实时分析氛围风格"""
    if not overview:
        return None

    prompt = f"""电影《{title}》
简介：{overview[:300]}

判断属于哪种氛围风格（只输出一个词）：
- 奇幻穹宇:故事发生在一个被巨大空间笼罩的奇幻世界中，这个空间可能是魔法笼罩的天空、神话中的异次元、巨龙翱翔的云海、或是精灵栖息的星辰之间，世界观本身充满了非现实的奇观，让人抬头仰望时感到自身渺小，对未知的魔法与神秘充满惊叹与向往。如《阿凡达》《天空之城》《指环王》（精灵故乡瑞文戴尔的穹顶感）《沙丘》（异星神秘主义）。
- 热血史诗:人物处于向前冲刺的行动之中，目标明确、阻碍重重，叙事节奏紧凑有力，最终迎来胜利的狂喜或悲壮的牺牲，让人攥紧拳头、心潮澎湃，感受到燃烧般的激昂与抗争的力量。如《勇敢的心》《摔跤吧！爸爸》《复仇者联盟4》《爆裂鼓手》。
- 烟火人间:场景是日常生活的街巷与屋檐下，人物是身边的普通人，情节是柴米油盐中的温暖与真实，不追求戏剧性的跌宕起伏，而是在平淡中酿出滋味，让人会心一笑或心头一暖，看到自己的生活。如《饮食男女》《海街日记》《绿皮书》《小偷家族》。
- 暗影谜踪:故事发生在暗处、黑夜或密闭空间中，光线被剥夺、信息被隐藏、真相需要追寻，观众与角色一同在阴影中摸索，体验解谜、追踪或逃生的紧张与压迫感，直到光明出现或谜底揭晓。如《七宗罪》《沉默的羔羊》《盗梦空间》《看不见的客人》。
- 怅然回望:以回忆或时光流逝为核心驱动力，情绪基调是怀念、遗憾或感伤，影片往往以回望的姿态展开，让人回头看去，心中泛起"如果当初"的叹息，在时间的长河中品味失去与留恋。如《情书》《泰坦尼克号》《花样年华》《少年时代》。
- 荒诞冷眼:以一种抽离、冷静甚至荒谬的视角观察世界，导演与事件保持距离、不煽情不介入，让人感到荒唐可笑或细思极恐，在冷眼旁观中品味命运的讽刺、社会的荒诞或存在的虚无。如《让子弹飞》《大佛普拉斯》《寄生虫》《疯狂的石头》。    
输出："""

    result = call_llm(prompt, max_tokens=20)
    valid = ["奇幻穹宇", "热血史诗", "烟火人间", "暗影谜踪", "怅然回望", "荒诞冷眼"]
    return result if result in valid else None


def generate_movie_tags(title, genres, overview):
    """实时生成标签（原样）"""
    prompt = f"""为电影《{title}》生成6-8个中文标签。

类型：{genres}
简介：{overview[:200] if overview else '无'}

要求：
- 每个标签2-4个字
- 覆盖类型、风格、情感
- 只返回JSON数组

输出："""

    try:
        result = call_llm(prompt, max_tokens=200)
        result = result.replace("```json", "").replace("```", "").strip()
        tags = json.loads(result)
        return tags[:8]
    except Exception as e:
        logger.error(f"标签生成失败: {e}")
        return ["电影", "推荐", "佳作"]

# ==================== 缓存版分析（与 db.movie_cache 集成） ====================

def get_or_analyze_atmosphere_with_cache(tmdb_id, title, overview, genres_list):
    """获取或分析氛围（带独立缓存表）"""
    cached = get_cached_atmosphere(tmdb_id)
    if cached:
        return cached
    atmosphere = analyze_atmosphere_style(title, overview)
    if atmosphere:
        save_cached_atmosphere(tmdb_id, atmosphere)
    return atmosphere


def get_or_analyze_visual_with_cache(tmdb_id, poster_url):
    """获取或分析视觉风格（带 movie_classify 缓存）"""
    cached = get_cached_classify(tmdb_id)
    if cached and cached.get('visual_style'):
        return cached['visual_style']
    if not poster_url:
        return None
    visual = analyze_visual_style(poster_url)
    if visual:
        save_classify_to_db(tmdb_id, "", "", visual, None, [])
    return visual
