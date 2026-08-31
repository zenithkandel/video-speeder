"""
Configuration constants and defaults for Video Speeder.
"""

from typing import Set

SUPPORTED_EXTENSIONS: Set[str] = {
    ".mp4",
    ".mkv",
    ".mov",
    ".avi",
    ".webm",
    ".flv",
    ".wmv",
    ".m4v",
    ".ts",
    ".mts",
    ".m2ts",
    ".3gp",
    ".ogg",
    ".ogv",
}

# Video Encoding Defaults
DEFAULT_VIDEO_CODEC = "libx264"
DEFAULT_AUDIO_CODEC = "aac"
DEFAULT_AUDIO_BITRATE = "192k"
DEFAULT_CRF = 22
DEFAULT_PRESET = "medium"

AVAILABLE_PRESETS = [
    "ultrafast",
    "superfast",
    "veryfast",
    "faster",
    "fast",
    "medium",
    "slow",
    "slower",
    "veryslow",
]

AVAILABLE_CODECS = [
    "libx264",
    "libx265",
    "h264_nvenc",
    "hevc_nvenc",
    "h264_qsv",
    "hevc_qsv",
    "h264_amf",
    "hevc_amf",
]

# Audio tempo filter boundaries per FFmpeg specification
ATEMPO_MIN = 0.5
ATEMPO_MAX = 2.0

# Speed multiplier valid range (from extreme slow-mo 0.01x to extreme timelapse 10,000x)
MIN_SPEED_MULTIPLIER = 0.01
MAX_SPEED_MULTIPLIER = 10000.0

# Terminal UI configuration
APP_NAME = "Video Speeder CLI"
APP_VERSION = "1.0.0"
APP_TAGLINE = "High-Performance Local Video Speed Acceleration & Slow-Motion Engine"
