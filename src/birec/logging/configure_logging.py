"""Loguru configuration: console + rotating file sinks with room_id context."""

from __future__ import annotations

import os
import sys
from datetime import datetime

from loguru import logger
from tqdm import tqdm

from birec.logging.typing import LOG_LEVEL

__all__ = ("configure_logger", "TqdmOutputStream", "make_log_file_path")

LOGURU_CONSOLE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level}</level> | "
    "<cyan>{module}</cyan>:<cyan>{line}</cyan> | "
    "<level>{extra[room_id]}</level> - "
    "<level>{message}</level>"
)

LOGURU_FILE_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
    "<level>{level}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
    "<level>{extra[room_id]}</level> - "
    "<level>{message}</level>"
)


class TqdmOutputStream:
    """A stderr-like sink that routes through :func:`tqdm.write`."""

    def write(self, string: str = "") -> None:
        tqdm.write(string, file=sys.stderr, end="")

    def isatty(self) -> bool:
        return sys.stderr.isatty()


_console_handler_id: int | None = None
_file_handler_id: int | None = None

_old_log_dir: str | None = None
_old_console_log_level: LOG_LEVEL | None = None
_old_backup_count: int | None = None


def configure_logger(
    log_dir: str,
    *,
    console_log_level: LOG_LEVEL = "INFO",
    backup_count: int | None = None,
) -> None:
    """Configure console and rotating file sinks idempotently."""
    global _console_handler_id, _file_handler_id
    global _old_log_dir, _old_console_log_level, _old_backup_count

    logger.configure(extra={"room_id": ""})

    if console_log_level != _old_console_log_level:
        if _console_handler_id is not None:
            logger.remove(_console_handler_id)
        else:
            logger.remove()  # remove the default stderr handler

        if bool(os.environ.get("BIREC_PROGRESS")):
            _console_handler_id = logger.add(
                TqdmOutputStream(),
                level=console_log_level,
                format=LOGURU_CONSOLE_FORMAT,
            )
        else:
            _console_handler_id = logger.add(
                sys.stderr, level=console_log_level, format=LOGURU_CONSOLE_FORMAT
            )

        _old_console_log_level = console_log_level

    if log_dir != _old_log_dir or backup_count != _old_backup_count:
        log_file_path = make_log_file_path(log_dir)
        logger.info(f"log file: {log_file_path}")

        file_handler_id = logger.add(
            log_file_path,
            level="TRACE" if bool(os.environ.get("BIREC_TRACE")) else "DEBUG",
            format=LOGURU_FILE_FORMAT,
            enqueue=True,
            rotation="00:00",
            retention=backup_count,
            backtrace=True,
            diagnose=True,
        )

        if _file_handler_id is not None:
            logger.remove(_file_handler_id)

        _file_handler_id = file_handler_id

        _old_log_dir = log_dir
        _old_backup_count = backup_count


def make_log_file_path(log_dir: str) -> str:
    datetime_string = datetime.now().strftime("%Y-%m-%d_%H-%M-%S_%f")
    filename = f"birec_{datetime_string}.log"
    return os.path.abspath(os.path.join(log_dir, filename))
