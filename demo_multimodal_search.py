import sys
import os
import torch
import numpy as np
import pandas as pd
import chromadb
import ollama
from PIL import Image
from transformers import BlipProcessor, BlipForConditionalGeneration
from transformers import CLIPProcessor, CLIPModel
from config import TMDB_CSV_PATH,POSTER_DIR,CHROMA_FEATURE_PATH,CHROMA_RECALL_PATH,CLIP_MODEL_PATH,BLIP_MODEL_PATH

# ---------- 配置 ----------
TMDB_CSV = TMDB_CSV_PATH
POSTER_DIR = POSTER_DIR
CHROMA_PATH = CHROMA_FEATURE_PATH
chroma_path =CHROMA_RECALL_PATH
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# 加载模型
print("Loading CLIP...")
clip_model = CLIPModel.from_pretrained(CLIP_MODEL_PATH)
clip_processor = CLIPProcessor.from_pretrained(CLIP_MODEL_PATH)
clip_model.to(DEVICE)
clip_model.eval()

print("Loading BLIP...")
blip_processor = BlipProcessor.from_pretrained(BLIP_MODEL_PATH)
blip_model = BlipForConditionalGeneration.from_pretrained(BLIP_MODEL_PATH)
blip_model.to(DEVICE)
blip_model.eval()

# ---------- 功能函数 ----------
def get_clip_image_vector(img_path):
    image = Image.open(img_path).convert("RGB")
    inputs = clip_processor(images=image, return_tensors="pt").to(DEVICE)
    with torch.no_grad():
        vision_outputs = clip_model.vision_model(pixel_values=inputs['pixel_values'])
        pooled = vision_outputs.pooler_output
        projected = clip_model.visual_projection(pooled)
    vec = projected[0].cpu().numpy()
    return vec / np.linalg.norm(vec)

def image_search(img_path, top_k=80):
    q_vec = get_clip_image_vector(img_path)
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_collection("movie_posters")
    results = collection.query(query_embeddings=[q_vec.tolist()], n_results=top_k, include=["metadatas", "distances"])
    recs = []
    for meta, dist in zip(results['metadatas'][0], results['distances'][0]):
        recs.append({
            'movieId': int(meta['movieId']),
            'title': meta['title'],
            'genres': meta['genres'],
            'sim': 1 - dist
        })
    return recs

def generate_blip_description(img_path):
    image = Image.open(img_path).convert("RGB")
    inputs = blip_processor(image, return_tensors="pt").to(DEVICE)
    with torch.no_grad():
        out = blip_model.generate(**inputs, max_length=60, num_beams=4, early_stopping=True)
    caption = blip_processor.decode(out[0], skip_special_tokens=True)
    return caption.strip()

def text_search(query, top_k=80):
    resp = ollama.embeddings(model='bge-m3', prompt=query)
    q_vec = np.array(resp['embedding'], dtype=np.float32)
    q_vec = q_vec / np.linalg.norm(q_vec)
    client = chromadb.PersistentClient(path=chroma_path)
    collection = client.get_collection("movies_bge_m3")
    results = collection.query(query_embeddings=[q_vec.tolist()], n_results=top_k, include=["metadatas", "distances"])
    recs = []
    for meta, dist in zip(results['metadatas'][0], results['distances'][0]):
        recs.append({
            'movieId': int(meta['movieId']),
            'title': meta['title'],
            'genres': meta['genres'],
            'sim': 1 - dist
        })
    return recs

def main(img_path):
    if not os.path.exists(img_path):
        print("图片不存在")
        return

    # 1. 视觉检索 Top-1
    vis = image_search(img_path, top_k=1)
    if not vis:
        print("视觉检索失败")
        return
    top_vis = vis[0]
    print(f"\n[1] 视觉检索 Top-1: {top_vis['title']} | {top_vis['genres']} | sim={top_vis['sim']:.4f}")

    # 2. BLIP 描述
    blip_desc = generate_blip_description(img_path)
    print(f"\n[2] BLIP 描述: {blip_desc}")

    # 3. 文本检索 Top-3 示例
    txt_sample = text_search(blip_desc, top_k=3)
    print("\n[3] 文本检索示例:")
    for i, m in enumerate(txt_sample):
        print(f"   {i+1}. {m['title']} | {m['genres']} | sim={m['sim']:.4f}")

    # 4. 扩大候选池并融合
    vis_pool = image_search(img_path, top_k=80)
    txt_pool = text_search(blip_desc, top_k=80)
    alpha = 0.4
    scores = {}
    for idx, m in enumerate(vis_pool):
        scores[m['movieId']] = alpha * (1 - idx/80)
    for idx, m in enumerate(txt_pool):
        mid = m['movieId']
        scores[mid] = scores.get(mid, 0) + (1-alpha) * (1 - idx/80)
    sorted_movies = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:50]

    # 5. 读取 DataFrame
    df = pd.read_csv(TMDB_CSV)
    # 获取视觉第一名的电影及其类型
    top_mid = vis_pool[0]['movieId']
    top_row = df[df['movieId'] == top_mid].iloc[0]
    target_genres = set(top_row['genres'].split('|'))
    print(f"\n[4] 目标电影: {top_row['title']}")
    print(f"    类型: {target_genres}")

    director_bonus = 0.05  # 导演匹配加分（每匹配一次）
    genre_bonus_per_match = 0.01  # 每个匹配类型加分

    final_candidates = []
    for mid, base_score in sorted_movies:
        row = df[df['movieId'] == mid]
        if row.empty:
            continue
        row = row.iloc[0]
        final_score = base_score
        # 导演匹配加分（使用姓氏）
        target_dir = top_row.get('director', '')
        if target_dir and pd.notna(target_dir):
            director_keyword = target_dir.split()[-1]
            if pd.notna(row.get('director')) and director_keyword in str(row['director']):
                final_score += director_bonus
        # 类型匹配加分
        current_genres = set(row['genres'].split('|'))
        overlap = len(target_genres & current_genres)
        final_score += overlap * genre_bonus_per_match
        final_candidates.append({
            'title': row['title'],
            'genres': row['genres'],
            'director': row.get('director', ''),
            'overlap': overlap,
            'score': final_score
        })

    final_candidates.sort(key=lambda x: x['score'], reverse=True)
    final_candidates = final_candidates[:10]

    print(f"\n[5] 最终推荐 (类型匹配加分 +{genre_bonus_per_match}/个，导演加分 +{director_bonus})")
    for i, mov in enumerate(final_candidates):
        print(
            f"{i + 1}. {mov['title']} | {mov['genres']} | 匹配类型数={mov['overlap']} | {mov['director']} | 总分={mov['score']:.4f}")
if __name__ == "__main__":
    main('1.jpg')