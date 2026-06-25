# config.py
"""
统一配置管理
所有配置项集中在此，支持从环境变量读取
"""
import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# ==================== 项目根目录 ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ==================== 数据目录 ====================
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "Data"))
os.makedirs(DATA_DIR, exist_ok=True)

# ==================== 数据库路径 ====================
USER_DB_PATH = os.getenv("USER_DB_PATH", os.path.join(DATA_DIR, "users.db"))
RATING_DB_PATH = os.getenv("RATING_DB_PATH", os.path.join(DATA_DIR, "user_ratings.db"))
POOL_DB_PATH = os.getenv("POOL_DB_PATH", os.path.join(DATA_DIR, "movie_pools.db"))
PROFILE_DB_PATH = os.getenv("PROFILE_DB_PATH", os.path.join(DATA_DIR, "user_profiles.db"))
CLASSIFY_DB_PATH = os.getenv("CLASSIFY_DB_PATH", os.path.join(DATA_DIR, "movie_classify_all.db"))
TAG_CACHE_DB_PATH = os.getenv("TAG_CACHE_DB_PATH", os.path.join(DATA_DIR, "movie_tags_cache.db"))
CHAT_HISTORY_DB = os.getenv("CHAT_HISTORY_DB", os.path.join(DATA_DIR, "chat_history.db"))
HOT_MOVIES_SNAPSHOTS = os.getenv("HOT_MOVIES_SNAPSHOTS", os.path.join(DATA_DIR, "hot_movies_snapshots.db"))
# ==================== 数据文件路径 ====================
TMDB_CSV_PATH = os.getenv("TMDB_CSV_PATH", os.path.join(DATA_DIR, "tmdb_movies_cleaned.csv"))
RATINGS_CSV_PATH = os.getenv("RATINGS_CSV_PATH", os.path.join(DATA_DIR, "ml-latest-small", "ratings.csv"))

# ==================== ChromaDB 路径 ====================
CHROMA_RECALL_PATH = os.getenv("CHROMA_RECALL_PATH", os.path.join(BASE_DIR, "Recall/chroma_db"))
CHROMA_FEATURE_PATH = os.getenv("CHROMA_FEATURE_PATH", os.path.join(BASE_DIR, "Feature-engineering/chroma_db"))

# ==================== 模型路径 ====================
CLIP_MODEL_PATH = os.getenv("CLIP_MODEL_PATH", os.path.join(BASE_DIR, "models/clip-vit-base-patch32"))

BLIP_MODEL_PATH = os.getenv("BLIP_MODEL_PATH", os.path.join(BASE_DIR, "Picture Search/blip-finetuned-poster"))
BLIP_MODEL_base_PATH = os.getenv("BLIP_MODEL_PATH", os.path.join(BASE_DIR, "models/blip-image-captioning-base"))

# ==================== 风格向量路径 ====================
STYLE_VECTOR_PATH = os.getenv("STYLE_VECTOR_PATH", os.path.join(BASE_DIR, "Web/"))

# ==================== 海报目录 ====================
POSTER_DIR = os.getenv("POSTER_DIR", os.path.join(BASE_DIR, "Feature-engineering/posters"))
os.makedirs(POSTER_DIR, exist_ok=True)

# ==================== 日志目录 ====================
LOG_DIR = os.getenv("LOG_DIR", os.path.join(DATA_DIR, "logs"))
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.getenv("LOG_FILE", os.path.join(LOG_DIR, "cinemind.log"))
ERROR_LOG_FILE = os.getenv("ERROR_LOG_FILE", os.path.join(LOG_DIR, "cinemind_error.log"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ==================== API Keys ====================
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")

# ==================== TMDB 配置 ====================
TMDB_IMAGE_BASE = os.getenv("TMDB_IMAGE_BASE", "https://image.tmdb.org/t/p/w300")
TMDB_IMAGE_BASE_W500 = os.getenv("TMDB_IMAGE_BASE_W500", "https://image.tmdb.org/t/p/w500")
TMDB_BASE_URL = os.getenv("TMDB_BASE_URL", "https://api.themoviedb.org/3")

# ==================== 设备配置 ====================
DEVICE = os.getenv("DEVICE", "cuda" if __import__('torch').cuda.is_available() else "cpu")

# ==================== 其他配置 ====================
# 缓存过期时间（秒）
CACHE_TTL_SHORT = int(os.getenv("CACHE_TTL_SHORT", "3600"))
CACHE_TTL_MEDIUM = int(os.getenv("CACHE_TTL_MEDIUM", "86400"))
CACHE_TTL_LONG = int(os.getenv("CACHE_TTL_LONG", "604800"))

# 池子构建参数
HOT_RATIO = float(os.getenv("HOT_RATIO", "0.30"))
COLD_RATIO = float(os.getenv("COLD_RATIO", "0.35"))
MIN_VOTE_AVG = float(os.getenv("MIN_VOTE_AVG", "6.0"))
MIN_VOTE_COUNT = int(os.getenv("MIN_VOTE_COUNT", "50"))
MAX_PAGES = int(os.getenv("MAX_PAGES", "50"))


# ==================== 环境检测 ====================
def is_production() -> bool:
    """检查是否为生产环境"""
    return os.getenv("ENV", "development").lower() == "production"

def is_development() -> bool:
    """检查是否为开发环境"""
    return not is_production()