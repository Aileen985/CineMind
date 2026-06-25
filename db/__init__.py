# db/__init__.py
"""
数据库层统一导出（不含任何旧兼容代码）
"""

# 用户模块
from .users import init_table as init_users, register_user, login_user

# 评分模块
from .ratings import (
    init_table as init_ratings,
    save_rating,
    get_user_ratings,
    get_rating_stats,
    get_my_rating,
)

# 偏好模块
from .preferences import (
    init_table as init_preferences,
    save_preference,
    get_my_preference,
    get_user_liked_movies,
    get_user_disliked_movies,
    get_user_preference_summary,
)

# 评语模块
from .comments import (
    init_table as init_comments,
    save_comment,
    get_my_comment,
)

# 电影缓存模块
from .movie_cache import (
    init_table as init_movie_cache,
    get_cached_classify,
    save_classify_to_db,
    get_cached_atmosphere,
    save_cached_atmosphere,
    get_tmdb_cache,
    save_tmdb_cache,
)

# 池子模块
from .pools import (
    init_table as init_pools,
    get_hot_pool,
    get_cold_pool,
    save_hot_pool,
    save_cold_pool,
    update_pool_meta,
)

# 画像模块
from .profiles import (
    init_table as init_profiles,
    get_text_profile,      # 直接暴露新名字，不叫 get_user_text_profile
    save_text_profile,
    get_visual_profile,    # 直接暴露新名字，不叫 get_user_visual_profile
    save_visual_profile,
)