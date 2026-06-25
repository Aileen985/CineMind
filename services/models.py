# services/models.py
"""
模型加载和数据集合加载
"""
import pandas as pd
import chromadb
import torch
import os
from PIL import Image
from transformers import BlipProcessor, BlipForConditionalGeneration
from transformers import CLIPProcessor, CLIPModel
from config import (
    DEVICE,
    CLIP_MODEL_PATH,
    TMDB_CSV_PATH,
    CHROMA_RECALL_PATH,
    CHROMA_FEATURE_PATH,
)

# 全局缓存
_tmdb_df = None
_text_collection = None
_image_collection = None
_clip_model = None
_clip_processor = None
_blip_processor = None
_blip_model = None


# ---------- BLIP / CLIP 模型加载 ----------
def _load_blip():
    global _blip_processor, _blip_model
    if _blip_model is None:
        device = DEVICE
        _blip_processor = BlipProcessor.from_pretrained("D:/coding/CineMind/Picture Search/blip-finetuned-poster")
        _blip_model = BlipForConditionalGeneration.from_pretrained("D:/coding/CineMind/Picture Search/blip-finetuned-poster")
        _blip_model.to(device)
        _blip_model.eval()
    return _blip_processor, _blip_model


def _load_clip():
    global _clip_model, _clip_processor
    if _clip_model is None:
        device = DEVICE
        _clip_model = CLIPModel.from_pretrained(CLIP_MODEL_PATH)
        _clip_processor = CLIPProcessor.from_pretrained(CLIP_MODEL_PATH)
        _clip_model.to(device)
        _clip_model.eval()
    return _clip_model, _clip_processor


def generate_blip_description(image_path):
    """生成图片的英文自然语言描述"""
    processor, model = _load_blip()
    device = next(model.parameters()).device
    image = Image.open(image_path).convert("RGB")
    inputs = processor(image, return_tensors="pt").to(device)
    with torch.no_grad():
        out = model.generate(**inputs, max_length=60, num_beams=4, early_stopping=True)
    caption = processor.decode(out[0], skip_special_tokens=True)
    return caption.strip()


# ---------- 数据加载 ----------
def get_tmdb_df():
    global _tmdb_df
    if _tmdb_df is None:
        _tmdb_df = pd.read_csv(TMDB_CSV_PATH)
    return _tmdb_df


def get_text_collection():
    global _text_collection
    if _text_collection is None:
        client = chromadb.PersistentClient(path=CHROMA_RECALL_PATH)
        _text_collection = client.get_collection("movies_bge_m3")
    return _text_collection


def get_image_collection():
    global _image_collection
    if _image_collection is None:
        client = chromadb.PersistentClient(path=CHROMA_FEATURE_PATH)
        try:
            _image_collection = client.get_collection("movie_posters")
        except:
            _image_collection = None
    return _image_collection


def get_clip_model():
    global _clip_model, _clip_processor
    if _clip_model is None:
        _clip_model = CLIPModel.from_pretrained(CLIP_MODEL_PATH)
        _clip_processor = CLIPProcessor.from_pretrained(CLIP_MODEL_PATH)
        _clip_model.to(DEVICE)
        _clip_model.eval()
    return _clip_model, _clip_processor