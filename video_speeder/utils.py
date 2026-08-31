"""
Utility functions for file system handling, ffmpeg verification, formatting, and audio filter graph generation.
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .config import (
    ATEMPO_MAX,
    ATEMPO_MIN,
    SUPPORTED_EXTENSIONS,
)


def check_ffmpeg_installation() -> Dict[str, any]:
    """
    Checks if ffmpeg and ffprobe are installed and accessible via PATH.
    Returns details on availability, version, and hardware acceleration support.
    """
    ffmpeg_path = shutil.which("ffmpeg")
    ffprobe_path = shutil.which("ffprobe")

    result = {
        "ffmpeg_available": ffmpeg_path is not None,
        "ffprobe_available": ffprobe_path is not None,
        "ffmpeg_path": ffmpeg_path,
        "ffprobe_path": ffprobe_path,
        "version": None,
        "nvenc_supported": False,
        "qsv_supported": False,
        "amf_supported": False,
    }

    if ffmpeg_path:
        try:
            proc = subprocess.run(
                [ffmpeg_path, "-version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            first_line = proc.stdout.splitlines()[0] if proc.stdout else ""
            result["version"] = first_line

            # Check encoders support
            encoders_proc = subprocess.run(
                [ffmpeg_path, "-encoders"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            encoders_text = encoders_proc.stdout.lower() if encoders_proc.stdout else ""
            result["nvenc_supported"] = "h264_nvenc" in encoders_text
            result["qsv_supported"] = "h264_qsv" in encoders_text
            result["amf_supported"] = "h264_amf" in encoders_text
        except Exception:
            pass

    return result


def build_atempo_filter(speed: float) -> str:
    """
    Constructs a chained FFmpeg atempo filter string for arbitrary speed multipliers.
    FFmpeg atempo filter only supports values between 0.5 and 2.0.
    For speeds outside this range, multiple atempo filters are chained together.
    
    Examples:
        speed = 1.5  -> 'atempo=1.5'
        speed = 3.0  -> 'atempo=2.0,atempo=1.5'
        speed = 4.0  -> 'atempo=2.0,atempo=2.0'
        speed = 0.25 -> 'atempo=0.5,atempo=0.5'
    """
    if abs(speed - 1.0) < 1e-6:
        return "atempo=1.0"

    factors: List[float] = []
    current_speed = speed

    if current_speed > ATEMPO_MAX:
        while current_speed > ATEMPO_MAX:
            factors.append(ATEMPO_MAX)
            current_speed /= ATEMPO_MAX
        if current_speed > 1.0001:
            factors.append(current_speed)
    elif current_speed < ATEMPO_MIN:
        while current_speed < ATEMPO_MIN:
            factors.append(ATEMPO_MIN)
            current_speed /= ATEMPO_MIN
        if current_speed < 0.9999:
            factors.append(current_speed)
    else:
        factors.append(current_speed)

    filter_chains = [f"atempo={factor:.6f}".rstrip("0").rstrip(".") for factor in factors]
    return ",".join(filter_chains)


def format_duration(seconds: float) -> str:
    """
    Formats a duration in seconds into HH:MM:SS or MM:SS format.
    """
    if seconds is None or seconds < 0:
        return "--:--"
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 100)

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}.{millis:02d}"


def format_bytes(size_bytes: int) -> str:
    """
    Formats byte size to human readable string (KB, MB, GB).
    """
    if size_bytes is None or size_bytes < 0:
        return "0 B"
    
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_index = 0
    size = float(size_bytes)
    while size >= 1024.0 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1
    return f"{size:.2f} {units[unit_index]}"


def find_video_files(
    target_path: Path,
    recursive: bool = False,
    custom_extensions: Optional[Set[str]] = None,
) -> List[Path]:
    """
    Finds video files in the specified path (single file or directory).
    """
    valid_exts = custom_extensions if custom_extensions is not None else SUPPORTED_EXTENSIONS
    valid_exts = {ext.lower() for ext in valid_exts}

    target = Path(target_path).resolve()
    if not target.exists():
        raise FileNotFoundError(f"Target path does not exist: {target_path}")

    if target.is_file():
        if target.suffix.lower() in valid_exts:
            return [target]
        else:
            return []

    video_files: List[Path] = []
    if recursive:
        for root, _, files in os.walk(target):
            for file in files:
                p = Path(root) / file
                if p.suffix.lower() in valid_exts:
                    video_files.append(p)
    else:
        for item in target.iterdir():
            if item.is_file() and item.suffix.lower() in valid_exts:
                video_files.append(item)

    return sorted(video_files)


def calculate_output_path(
    input_file: Path,
    base_input_dir: Path,
    output_dir: Optional[Path],
    speed: float,
    preserve_hierarchy: bool = True,
    suffix: Optional[str] = None,
) -> Path:
    """
    Calculates the destination path for the speed-adjusted video.
    """
    speed_tag = suffix if suffix is not None else f"_{speed:g}x"
    output_filename = f"{input_file.stem}{speed_tag}{input_file.suffix}"

    if output_dir is None:
        # Default: save in same directory as input file
        return input_file.parent / output_filename

    output_dir_resolved = Path(output_dir).resolve()

    if base_input_dir.is_file():
        # Single file processing
        return output_dir_resolved / output_filename

    if preserve_hierarchy:
        try:
            rel_parent = input_file.parent.relative_to(base_input_dir.resolve())
            destination_dir = output_dir_resolved / rel_parent
        except ValueError:
            destination_dir = output_dir_resolved
    else:
        destination_dir = output_dir_resolved

    return destination_dir / output_filename
