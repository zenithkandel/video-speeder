"""
Video Speeder - Professional CLI tool for fast local video speed adjustments.
"""

__version__ = "1.0.0"
__author__ = "Zenith Kandel"

from .core import VideoSpeeder, VideoMetadata, SpeedJobResult
from .processor import BatchProcessor
from .config import SUPPORTED_EXTENSIONS, DEFAULT_CRF, DEFAULT_PRESET

__all__ = [
    "VideoSpeeder",
    "VideoMetadata",
    "SpeedJobResult",
    "BatchProcessor",
    "SUPPORTED_EXTENSIONS",
    "DEFAULT_CRF",
    "DEFAULT_PRESET",
]
