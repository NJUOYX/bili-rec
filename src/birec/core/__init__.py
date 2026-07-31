"""core — recording coordination layer."""

from __future__ import annotations

from .cover_downloader import CoverDownloader, CoverDownloaderListener
from .danmaku_dumper import DanmakuDumper, DanmakuDumperListener
from .danmaku_receiver import DanmakuReceiver, DanmakuReceiverListener
from .metadata_provider import MetadataProvider
from .models import (
    CompletedSegment,
    Danmaku,
    DanmakuMessage,
    Gift,
    GuardBuy,
    StartedSegment,
    StreamEvent,
    SuperChat,
)
from .path_provider import PathProvider, escape_path
from .raw_danmaku_dumper import RawDanmakuDumper, RawDanmakuDumperListener
from .raw_danmaku_receiver import (
    RawDanmakuReceiver,
    RawDanmakuReceiverListener,
)
from .recorder import Recorder
from .statistics import SizedStatistics, Statistics
from .stream_param_holder import StreamParamHolder
from .stream_recorder import StreamRecorder

__all__ = (
    "CompletedSegment",
    "StartedSegment",
    "CoverDownloader",
    "CoverDownloaderListener",
    "Danmaku",
    "DanmakuDumper",
    "DanmakuDumperListener",
    "DanmakuMessage",
    "DanmakuReceiver",
    "DanmakuReceiverListener",
    "Gift",
    "GuardBuy",
    "MetadataProvider",
    "PathProvider",
    "RawDanmakuDumper",
    "RawDanmakuDumperListener",
    "RawDanmakuReceiver",
    "RawDanmakuReceiverListener",
    "Recorder",
    "SizedStatistics",
    "Statistics",
    "StreamEvent",
    "StreamParamHolder",
    "StreamRecorder",
    "SuperChat",
    "escape_path",
)
