# services/style_deprecated.py.py
"""
风格分析服务
"""
import os
import json
import sqlite3
import numpy as np
import torch
import requests
from PIL import Image
from datetime import datetime
from openai import OpenAI
from transformers import CLIPProcessor, CLIPModel

from services.models import generate_blip_description
from config import TAG_CACHE_DB_PATH, STYLE_VECTOR_PATH, POSTER_DIR, CLIP_MODEL_PATH
# 风格定义
ATM_STYLES = ["奇幻穹宇", "热血史诗", "烟火人间", "暗影谜踪", "怅然回望"]
VIS_STYLES = ["复古影调", "日常质感", "清冷静谧", "柔光梦镜", "风格显影"]


# 全局缓存
_style_vectors_cache = None
_clip_model_for_style = None
_clip_processor_for_style = None


def init_tag_cache():
    """初始化标签缓存数据库"""
    os.makedirs(os.path.dirname(TAG_CACHE_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(TAG_CACHE_DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS movie_tags (
            movie_id INTEGER PRIMARY KEY,
            title TEXT,
            tags TEXT,
            atm_style TEXT,
            vis_style TEXT,
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()
    print("✅ 标签缓存数据库已就绪")


def load_style_vectors():
    """加载风格向量（只加载一次）"""
    global _style_vectors_cache
    if _style_vectors_cache is not None:
        return _style_vectors_cache
    try:
        _style_vectors_cache = {
            'atm_clip': np.load(os.path.join(STYLE_VECTOR_PATH, "/tags1/atm_clip.npy")),
            'atm_bge': np.load(os.path.join(STYLE_VECTOR_PATH, "/tags1/atm_bge.npy")),
            'vis_clip': np.load(os.path.join(STYLE_VECTOR_PATH, "/tags1/vis_clip.npy")),
            'vis_bge': np.load(os.path.join(STYLE_VECTOR_PATH, "/tags1/vis_bge.npy")),
            'atm_neg_clip': np.load(os.path.join(STYLE_VECTOR_PATH, "/tags1/atm_neg_clip.npy")),
            'atm_neg_bge': np.load(os.path.join(STYLE_VECTOR_PATH, "/tags1/atm_neg_bge.npy")),
            'vis_neg_clip': np.load(os.path.join(STYLE_VECTOR_PATH, "/tags1/vis_neg_clip.npy")),
            'vis_neg_bge': np.load(os.path.join(STYLE_VECTOR_PATH, "/tags1/vis_neg_bge.npy")),
        }
        print("✅ 风格向量加载成功")
        return _style_vectors_cache
    except Exception as e:
        print(f"❌ 加载风格向量失败: {e}")
        return None


def get_poster_embedding(poster_path):
    """获取海报的 CLIP 和 BGE 向量（带模型缓存）"""
    global _clip_model_for_style, _clip_processor_for_style

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model_path =  CLIP_MODEL_PATH

    if _clip_model_for_style is None:
        _clip_model_for_style = CLIPModel.from_pretrained(model_path).to(device)
        _clip_processor_for_style = CLIPProcessor.from_pretrained(model_path)
        print("✅ CLIP 模型加载成功（风格分析）")

    try:
        if poster_path.startswith('http'):
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(poster_path, headers=headers, timeout=10)
            response.raise_for_status()
            image = Image.open(response.raw).convert("RGB")
        else:
            if not os.path.exists(poster_path):
                print(f"❌ 本地图片不存在: {poster_path}")
                return None, None
            image = Image.open(poster_path).convert("RGB")
    except Exception as e:
        print(f"❌ 加载图片失败: {e}")
        return None, None

    inputs = _clip_processor_for_style(images=image, return_tensors="pt").to(device)
    with torch.no_grad():
        vision_outputs = _clip_model_for_style.vision_model(pixel_values=inputs['pixel_values'])
        if hasattr(vision_outputs, 'pooler_output') and vision_outputs.pooler_output is not None:
            features = vision_outputs.pooler_output
        else:
            features = vision_outputs.last_hidden_state[:, 0, :]
        image_features = _clip_model_for_style.visual_projection(features)
        image_features = image_features / image_features.norm(dim=-1, keepdim=True)
    clip_vec = image_features[0].cpu().numpy().flatten()

    description = generate_blip_description(poster_path)
    resp = requests.post(
        "http://localhost:11434/api/embeddings",
        json={"model": "bge-m3", "prompt": description},
        timeout=30
    )
    bge_vec = np.array(resp.json()["embedding"], dtype=np.float32)
    bge_vec = bge_vec / np.linalg.norm(bge_vec)
    return clip_vec, bge_vec


def analyze_movie_style(poster_path):
    """分析电影海报的风格（氛围+视觉）"""
    vectors = load_style_vectors()
    if vectors is None:
        return {'atm': None, 'vis': None, 'atm_conf': 0, 'vis_conf': 0}
    try:
        poster_clip, poster_bge = get_poster_embedding(poster_path)
        if poster_clip is None:
            print("❌ 获取海报向量失败，返回 None")
            return {'atm': None, 'vis': None, 'atm_conf': 0, 'vis_conf': 0}
    except Exception as e:
        print(f"获取海报向量失败: {e}")
        return {'atm': None, 'vis': None, 'atm_conf': 0, 'vis_conf': 0}

    atm_scores = []
    for i in range(len(vectors['atm_clip'])):
        clip_sim = np.dot(poster_clip, vectors['atm_clip'][i])
        bge_sim = np.dot(poster_bge, vectors['atm_bge'][i])
        neg_sim = np.dot(poster_bge, vectors['atm_neg_bge'][i])
        score = (clip_sim + bge_sim) * 0.8 - neg_sim * 0.2
        atm_scores.append(score)

    vis_scores = []
    for i in range(len(vectors['vis_clip'])):
        clip_sim = np.dot(poster_clip, vectors['vis_clip'][i])
        bge_sim = np.dot(poster_bge, vectors['vis_bge'][i])
        neg_sim = np.dot(poster_bge, vectors['vis_neg_bge'][i])
        score = (clip_sim + bge_sim) * 0.8 - neg_sim * 0.2
        vis_scores.append(score)

    atm_idx = np.argmax(atm_scores)
    vis_idx = np.argmax(vis_scores)
    return {
        'atm': ATM_STYLES[atm_idx],
        'vis': VIS_STYLES[vis_idx],
        'atm_conf': float(atm_scores[atm_idx]),
        'vis_conf': float(vis_scores[vis_idx])
    }


def generate_movie_tags_deepseek(movie_title, movie_genres, movie_overview):
    """使用 DeepSeek 生成标签"""
    client = OpenAI(
        api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        base_url="https://api.deepseek.com"
    )
    prompt = f"""为电影《{movie_title}》生成6-8个中文标签。

电影信息：
- 类型：{movie_genres if movie_genres else "未知"}
- 简介：{movie_overview[:150] if movie_overview else "无"}

要求：
- 每个标签2-4个字
- 只返回JSON数组，例如：["科幻", "烧脑", "诺兰"]

输出："""
    try:
        response = client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=200
        )
        result = response.choices[0].message.content
        print(f"API返回: {result}")
        result = result.replace("```json", "").replace("```", "").strip()
        tags = json.loads(result)
        return tags[:8]
    except Exception as e:
        print(f"生成标签失败: {e}")
        return ["科幻", "烧脑", "经典"] if "科幻" in movie_genres else ["电影", "推荐"]


def get_movie_tags(movie_id, movie_title, movie_genres, movie_overview, poster_path=None):
    """获取电影标签（带缓存）"""
    init_tag_cache()
    conn = sqlite3.connect(TAG_CACHE_DB_PATH)
    c = conn.cursor()
    c.execute('SELECT tags, atm_style, vis_style FROM movie_tags WHERE movie_id = ?', (movie_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            'tags': json.loads(row[0]),
            'atm_style': row[1],
            'vis_style': row[2]
        }
    tags = generate_movie_tags_deepseek(movie_title, movie_genres, movie_overview)
    atm_style = vis_style = None
    if poster_path:
        try:
            style = analyze_movie_style(poster_path)
            atm_style = style.get('atm')
            vis_style = style.get('vis')
            print(f"🎨 氛围: {atm_style}, 🖼️ 视觉: {vis_style}")
        except Exception as e:
            print(f"风格分析失败: {e}")
    conn = sqlite3.connect(TAG_CACHE_DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO movie_tags (movie_id, title, tags, atm_style, vis_style, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (movie_id, movie_title, json.dumps(tags, ensure_ascii=False),
          atm_style, vis_style, datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return {'tags': tags, 'atm_style': atm_style, 'vis_style': vis_style}