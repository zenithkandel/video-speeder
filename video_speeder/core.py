"""
Core video processing engine utilizing FFmpeg for accurate video speed scaling and audio tempo filter chaining.
"""

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from .config import (
    DEFAULT_AUDIO_BITRATE,
    DEFAULT_AUDIO_CODEC,
    DEFAULT_CRF,
    DEFAULT_PRESET,
    DEFAULT_VIDEO_CODEC,
)
from .utils import build_atempo_filter


@dataclass
class VideoMetadata:
    """Stores probed metadata for a video file."""
    filepath: Path
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    video_codec: str = "unknown"
    has_audio: bool = False
    audio_codec: Optional[str] = None
    file_size: int = 0


@dataclass
class SpeedJobConfig:
    """Configuration options for a video speed adjustment job."""
    speed: float = 2.0
    video_codec: str = DEFAULT_VIDEO_CODEC
    audio_codec: str = DEFAULT_AUDIO_CODEC
    audio_bitrate: str = DEFAULT_AUDIO_BITRATE
    crf: int = DEFAULT_CRF
    preset: str = DEFAULT_PRESET
    keep_audio: bool = True
    mute_audio: bool = False
    target_fps: Optional[float] = None
    overwrite: bool = True
    hardware_accel: Optional[str] = None  # e.g., 'nvenc', 'qsv', 'amf'
    extra_ffmpeg_args: List[str] = field(default_factory=list)


@dataclass
class SpeedJobResult:
    """Stores the execution outcome and performance metrics of a speed job."""
    input_path: Path
    output_path: Path
    speed: float
    success: bool
    original_duration: float = 0.0
    output_duration: float = 0.0
    original_size: int = 0
    output_size: int = 0
    elapsed_time: float = 0.0
    error_message: Optional[str] = None


class VideoSpeeder:
    """
    Main engine for analyzing video files and executing FFmpeg speed scaling.
    """

    def __init__(self, ffmpeg_path: Optional[str] = None, ffprobe_path: Optional[str] = None):
        self.ffmpeg_path = ffmpeg_path or shutil.which("ffmpeg") or "ffmpeg"
        self.ffprobe_path = ffprobe_path or shutil.which("ffprobe") or "ffprobe"

    def probe_metadata(self, filepath: Path) -> VideoMetadata:
        """
        Probes a video file using ffprobe to obtain duration, resolution, fps, codecs, and audio info.
        """
        path = Path(filepath).resolve()
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        file_size = path.stat().st_size
        metadata = VideoMetadata(filepath=path, file_size=file_size)

        cmd = [
            self.ffprobe_path,
            "-v", "error",
            "-show_entries", "format=duration,size:stream=index,codec_type,codec_name,width,height,r_frame_rate,duration",
            "-of", "json",
            str(path),
        ]

        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
            )
            data = json.loads(proc.stdout)
            
            # Extract duration from format
            format_info = data.get("format", {})
            if "duration" in format_info:
                try:
                    metadata.duration = float(format_info["duration"])
                except (ValueError, TypeError):
                    pass

            streams = data.get("streams", [])
            for stream in streams:
                codec_type = stream.get("codec_type")
                if codec_type == "video" and metadata.width == 0:
                    metadata.video_codec = stream.get("codec_name", "unknown")
                    metadata.width = int(stream.get("width", 0) or 0)
                    metadata.height = int(stream.get("height", 0) or 0)

                    # Calculate FPS
                    r_fps = stream.get("r_frame_rate", "0/1")
                    if "/" in r_fps:
                        num, den = r_fps.split("/")
                        try:
                            den_val = float(den)
                            metadata.fps = float(num) / den_val if den_val != 0 else 0.0
                        except ValueError:
                            pass
                    
                    if metadata.duration == 0.0 and "duration" in stream:
                        try:
                            metadata.duration = float(stream["duration"])
                        except (ValueError, TypeError):
                            pass

                elif codec_type == "audio":
                    metadata.has_audio = True
                    metadata.audio_codec = stream.get("codec_name", "unknown")

        except Exception as err:
            # Fallback if ffprobe JSON fails: try parsing ffmpeg output
            metadata = self._fallback_probe(path, file_size)

        return metadata

    def _fallback_probe(self, filepath: Path, file_size: int) -> VideoMetadata:
        """Fallback prober using standard ffmpeg stderr."""
        meta = VideoMetadata(filepath=filepath, file_size=file_size)
        try:
            proc = subprocess.run(
                [self.ffmpeg_path, "-i", str(filepath)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            output = proc.stderr
            dur_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", output)
            if dur_match:
                hours, minutes, seconds = map(float, dur_match.groups())
                meta.duration = hours * 3600 + minutes * 60 + seconds

            if "Audio:" in output:
                meta.has_audio = True
            if "Video:" in output:
                res_match = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", output)
                if res_match:
                    meta.width = int(res_match.group(1))
                    meta.height = int(res_match.group(2))
                fps_match = re.search(r"(\d+(?:\.\d+)?) fps", output)
                if fps_match:
                    meta.fps = float(fps_match.group(1))
        except Exception:
            pass
        return meta

    def build_ffmpeg_command(
        self,
        input_path: Path,
        output_path: Path,
        config: SpeedJobConfig,
        metadata: VideoMetadata,
    ) -> List[str]:
        """
        Constructs the optimal FFmpeg command array for speed scaling.
        """
        speed = config.speed
        if speed <= 0:
            raise ValueError("Speed multiplier must be positive.")

        # Calculate video filter
        # setpts=(1/speed)*PTS
        video_filters = [f"setpts={1.0 / speed:.8f}*PTS"]

        if config.target_fps is not None and config.target_fps > 0:
            video_filters.append(f"fps={config.target_fps}")

        vf_string = ",".join(video_filters)

        cmd = [
            self.ffmpeg_path,
            "-hide_banner",
            "-nostdin",
            "-y" if config.overwrite else "-n",
            "-i", str(input_path.resolve()),
            "-filter:v", vf_string,
        ]

        # Video encoder configuration
        vcodec = config.video_codec
        if config.hardware_accel:
            if config.hardware_accel == "nvenc":
                vcodec = "h264_nvenc"
            elif config.hardware_accel == "qsv":
                vcodec = "h264_qsv"
            elif config.hardware_accel == "amf":
                vcodec = "h264_amf"

        cmd.extend(["-c:v", vcodec])

        # Preset & CRF logic according to encoder
        if "nvenc" in vcodec:
            cmd.extend(["-preset", "p4", "-cq", str(config.crf), "-pix_fmt", "yuv420p"])
        elif "qsv" in vcodec:
            cmd.extend(["-preset", config.preset, "-global_quality", str(config.crf)])
        elif "amf" in vcodec:
            cmd.extend(["-quality", "speed", "-rc", "cbr"])
        elif vcodec in ("libx264", "libx265"):
            cmd.extend([
                "-preset", config.preset,
                "-crf", str(config.crf),
                "-pix_fmt", "yuv420p",
            ])
        else:
            cmd.extend(["-crf", str(config.crf)])

        # Audio handling
        if not metadata.has_audio or config.mute_audio or not config.keep_audio:
            cmd.append("-an")
        else:
            af_string = build_atempo_filter(speed)
            cmd.extend([
                "-filter:a", af_string,
                "-c:a", config.audio_codec,
                "-b:a", config.audio_bitrate,
            ])

        # Extra flags for web streaming optimization and standard mp4 container
        if output_path.suffix.lower() in [".mp4", ".m4v", ".mov"]:
            cmd.extend(["-movflags", "+faststart"])

        # Add any extra user arguments
        if config.extra_ffmpeg_args:
            cmd.extend(config.extra_ffmpeg_args)

        # Progress reporting flag
        cmd.extend(["-progress", "pipe:1", "-nostats", "-loglevel", "error"])

        # Target output file
        cmd.append(str(output_path.resolve()))

        return cmd

    def process_video(
        self,
        input_path: Path,
        output_path: Path,
        config: SpeedJobConfig,
        progress_callback: Optional[Callable[[float, float, float], None]] = None,
    ) -> SpeedJobResult:
        """
        Executes speed scaling on a single video file with real-time progress callbacks.
        
        progress_callback signature:
            callback(percentage: float, processed_seconds: float, fps: float)
        """
        import threading

        input_file = Path(input_path).resolve()
        output_file = Path(output_path).resolve()

        if not input_file.exists():
            return SpeedJobResult(
                input_path=input_file,
                output_path=output_file,
                speed=config.speed,
                success=False,
                error_message=f"Input file not found: {input_file}",
            )

        # Ensure destination directory exists
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Probe metadata
        metadata = self.probe_metadata(input_file)
        orig_duration = metadata.duration
        orig_size = metadata.file_size
        expected_output_duration = orig_duration / config.speed if orig_duration > 0 else 0.0

        if not config.overwrite and output_file.exists():
            return SpeedJobResult(
                input_path=input_file,
                output_path=output_file,
                speed=config.speed,
                success=True,
                original_duration=orig_duration,
                output_duration=expected_output_duration,
                original_size=orig_size,
                output_size=output_file.stat().st_size,
                elapsed_time=0.0,
                error_message="Skipped (already exists)",
            )

        cmd = self.build_ffmpeg_command(input_file, output_file, config, metadata)

        start_time = time.time()
        error_lines: List[str] = []

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            # Continuously drain stderr in background thread to avoid pipe deadlocks
            def drain_stderr():
                if proc.stderr:
                    for err_line in proc.stderr:
                        clean_line = err_line.strip()
                        if clean_line:
                            error_lines.append(clean_line)

            stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
            stderr_thread.start()

            current_out_time_us = 0.0
            current_fps = 0.0

            # Read stdout progress pipe
            if proc.stdout:
                for line in proc.stdout:
                    line = line.strip()
                    if not line:
                        continue
                    
                    if line.startswith("out_time_us="):
                        try:
                            us = float(line.split("=")[1])
                            current_out_time_us = us
                        except (ValueError, IndexError):
                            pass
                    elif line.startswith("out_time_ms="):
                        try:
                            ms = float(line.split("=")[1])
                            current_out_time_us = ms
                        except (ValueError, IndexError):
                            pass
                    elif line.startswith("fps="):
                        try:
                            current_fps = float(line.split("=")[1])
                        except (ValueError, IndexError):
                            pass
                    elif line.startswith("progress="):
                        processed_sec = current_out_time_us / 1_000_000.0
                        pct = 0.0
                        if expected_output_duration > 0:
                            pct = min(100.0, (processed_sec / expected_output_duration) * 100.0)
                        
                        if progress_callback:
                            progress_callback(pct, processed_sec, current_fps)

            proc.wait()
            stderr_thread.join(timeout=2.0)

            elapsed_time = time.time() - start_time

            if proc.returncode != 0:
                err_msg = "\n".join(error_lines) if error_lines else f"FFmpeg exited with code {proc.returncode}"
                return SpeedJobResult(
                    input_path=input_file,
                    output_path=output_file,
                    speed=config.speed,
                    success=False,
                    original_duration=orig_duration,
                    original_size=orig_size,
                    elapsed_time=elapsed_time,
                    error_message=err_msg,
                )

            # Verify output file
            if output_file.exists():
                output_size = output_file.stat().st_size
                # Final probe on output file to verify actual duration
                out_meta = self.probe_metadata(output_file)
                actual_out_dur = out_meta.duration or expected_output_duration

                if progress_callback:
                    progress_callback(100.0, actual_out_dur, current_fps)

                return SpeedJobResult(
                    input_path=input_file,
                    output_path=output_file,
                    speed=config.speed,
                    success=True,
                    original_duration=orig_duration,
                    output_duration=actual_out_dur,
                    original_size=orig_size,
                    output_size=output_size,
                    elapsed_time=elapsed_time,
                )
            else:
                return SpeedJobResult(
                    input_path=input_file,
                    output_path=output_file,
                    speed=config.speed,
                    success=False,
                    original_duration=orig_duration,
                    original_size=orig_size,
                    elapsed_time=elapsed_time,
                    error_message="Output file was not created by FFmpeg.",
                )

        except Exception as ex:
            elapsed_time = time.time() - start_time
            return SpeedJobResult(
                input_path=input_file,
                output_path=output_file,
                speed=config.speed,
                success=False,
                original_duration=orig_duration,
                original_size=orig_size,
                elapsed_time=elapsed_time,
                error_message=str(ex),
            )
