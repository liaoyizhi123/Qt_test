import logging
import argparse
import functools
import traceback
from pathlib import Path


def initialize_logger_with_file_recording(name, args, log_file_path=None):
    _level = getattr(logging, args.log_level.upper(), logging.INFO)

    # DEBUG、INFO、WARNING、ERROR、CRITICAL
    logger = logging.getLogger(name)

    formatter = logging.Formatter(
        '%(asctime)s - [%(levelname)-7s] - [%(threadName)s] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    if not logger.handlers:
        logger.setLevel(_level)
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(_level)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

        if log_file_path:
            log_dir = Path(log_file_path).parent
            log_dir.mkdir(parents=True, exist_ok=True)  # 确保路径存在
            file_handler = logging.FileHandler(log_file_path, mode='w')  # 使用 'w' 每次重写日志文件
            file_handler.setLevel(_level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
    logger.info(
        f"Logger initialized for {name} with level {_level}. Log file: {log_file_path if log_file_path else 'None'}"
    )
    return logger