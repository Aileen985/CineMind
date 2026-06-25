# utils/logger.py
"""
统一日志管理
"""
import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler

# ==================== 日志配置 ====================
from config import LOG_DIR, LOG_FILE, ERROR_LOG_FILE, LOG_LEVEL, LOG_FORMAT, LOG_DATE_FORMAT

os.makedirs(LOG_DIR, exist_ok=True)



# ==================== 获取日志器 ====================
def get_logger(name: str, level: str = None) -> logging.Logger:
    """
    获取配置好的日志器

    Args:
        name: 日志器名称（通常使用 __name__）
        level: 日志级别（可选，默认使用全局配置）

    Returns:
        配置好的 Logger 实例
    """
    logger = logging.getLogger(name)

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    # 设置级别
    log_level = getattr(logging, (level or LOG_LEVEL).upper(), logging.INFO)
    logger.setLevel(log_level)

    # 格式化器
    formatter = logging.Formatter(LOG_FORMAT,LOG_DATE_FORMAT)

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件处理器（所有日志）
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # 错误日志专用文件处理器
    error_handler = RotatingFileHandler(
        ERROR_LOG_FILE,
        maxBytes=10 * 1024 * 1024,
        backupCount=3,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)

    return logger


# ==================== 便捷函数 ====================
def info(msg: str, *args, **kwargs):
    """记录 INFO 级别日志"""
    logger = get_logger("cinemind")
    logger.info(msg, *args, **kwargs)


def warning(msg: str, *args, **kwargs):
    """记录 WARNING 级别日志"""
    logger = get_logger("cinemind")
    logger.warning(msg, *args, **kwargs)


def error(msg: str, *args, **kwargs):
    """记录 ERROR 级别日志"""
    logger = get_logger("cinemind")
    logger.error(msg, *args, **kwargs)


def debug(msg: str, *args, **kwargs):
    """记录 DEBUG 级别日志"""
    logger = get_logger("cinemind")
    logger.debug(msg, *args, **kwargs)


# ==================== 默认日志器 ====================
_default_logger = None


def get_default_logger() -> logging.Logger:
    """获取默认日志器"""
    global _default_logger
    if _default_logger is None:
        _default_logger = get_logger("cinemind")
    return _default_logger