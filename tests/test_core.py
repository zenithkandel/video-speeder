"""
Unit tests for Video Speeder core modules and utilities.
"""

import unittest
from pathlib import Path

from video_speeder.config import DEFAULT_CRF, DEFAULT_PRESET, DEFAULT_VIDEO_CODEC
from video_speeder.core import SpeedJobConfig, VideoMetadata, VideoSpeeder
from video_speeder.utils import (
    build_atempo_filter,
    calculate_output_path,
    format_bytes,
    format_duration,
)


class TestUtils(unittest.TestCase):
    """Tests for utility and helper functions."""

    def test_build_atempo_filter_standard(self):
        self.assertEqual(build_atempo_filter(1.0), "atempo=1.0")
        self.assertEqual(build_atempo_filter(1.5), "atempo=1.5")
        self.assertEqual(build_atempo_filter(2.0), "atempo=2")

    def test_build_atempo_filter_high_speed(self):
        # 4.0x -> atempo=2,atempo=2
        f4 = build_atempo_filter(4.0)
        self.assertEqual(f4, "atempo=2,atempo=2")

        # 3.0x -> atempo=2,atempo=1.5
        f3 = build_atempo_filter(3.0)
        self.assertEqual(f3, "atempo=2,atempo=1.5")

        # 8.0x -> atempo=2,atempo=2,atempo=2
        f8 = build_atempo_filter(8.0)
        self.assertEqual(f8, "atempo=2,atempo=2,atempo=2")

        # 200.0x extreme speed (2^7 * 1.5625 = 200)
        f200 = build_atempo_filter(200.0)
        self.assertEqual(f200, "atempo=2,atempo=2,atempo=2,atempo=2,atempo=2,atempo=2,atempo=2,atempo=1.5625")

    def test_build_atempo_filter_slow_motion(self):
        # 0.5x -> atempo=0.5
        self.assertEqual(build_atempo_filter(0.5), "atempo=0.5")

        # 0.25x -> atempo=0.5,atempo=0.5
        self.assertEqual(build_atempo_filter(0.25), "atempo=0.5,atempo=0.5")

    def test_format_duration(self):
        self.assertEqual(format_duration(0), "00:00.00")
        self.assertEqual(format_duration(65.5), "01:05.50")
        self.assertEqual(format_duration(3665), "01:01:05")
        self.assertEqual(format_duration(None), "--:--")

    def test_format_bytes(self):
        self.assertEqual(format_bytes(500), "500.00 B")
        self.assertEqual(format_bytes(1024 * 1024), "1.00 MB")
        self.assertEqual(format_bytes(1024 * 1024 * 1024 * 2.5), "2.50 GB")

    def test_calculate_output_path(self):
        base_dir = Path("/tmp/videos").resolve()
        input_file = (base_dir / "tutorial.mp4").resolve()

        # In-place with default suffix
        out1 = calculate_output_path(input_file, base_dir, None, speed=2.0)
        self.assertEqual(out1.name, "tutorial_2x.mp4")
        self.assertEqual(out1.parent, input_file.parent)

        # In custom output folder
        out_dir = Path("/tmp/output").resolve()
        out2 = calculate_output_path(input_file, base_dir, out_dir, speed=1.5)
        self.assertEqual(out2.name, "tutorial_1.5x.mp4")
        self.assertEqual(out2.parent, out_dir)


class TestCore(unittest.TestCase):
    """Tests for FFmpeg command construction and core logic."""

    def setUp(self):
        self.speeder = VideoSpeeder(ffmpeg_path="ffmpeg", ffprobe_path="ffprobe")

    def test_build_ffmpeg_command_basic(self):
        in_p = Path("/tmp/test.mp4")
        out_p = Path("/tmp/test_2x.mp4")
        config = SpeedJobConfig(speed=2.0)
        meta = VideoMetadata(filepath=in_p, duration=10.0, has_audio=True)

        cmd = self.speeder.build_ffmpeg_command(in_p, out_p, config, meta)

        self.assertIn("ffmpeg", cmd[0])
        self.assertIn("-filter:v", cmd)
        idx_vf = cmd.index("-filter:v")
        self.assertIn("setpts=0.50000000*PTS", cmd[idx_vf + 1])

        self.assertIn("-filter:a", cmd)
        idx_af = cmd.index("-filter:a")
        self.assertEqual(cmd[idx_af + 1], "atempo=2")

    def test_build_ffmpeg_command_no_audio(self):
        in_p = Path("/tmp/test.mp4")
        out_p = Path("/tmp/test_2x.mp4")
        config = SpeedJobConfig(speed=2.0, mute_audio=True)
        meta = VideoMetadata(filepath=in_p, duration=10.0, has_audio=True)

        cmd = self.speeder.build_ffmpeg_command(in_p, out_p, config, meta)
        self.assertIn("-an", cmd)
        self.assertNotIn("-filter:a", cmd)

    def test_build_ffmpeg_command_hardware_nvenc(self):
        in_p = Path("/tmp/test.mp4")
        out_p = Path("/tmp/test_2x.mp4")
        config = SpeedJobConfig(speed=2.0, hardware_accel="nvenc")
        meta = VideoMetadata(filepath=in_p, duration=10.0, has_audio=False)

        cmd = self.speeder.build_ffmpeg_command(in_p, out_p, config, meta)
        self.assertIn("h264_nvenc", cmd)
        self.assertIn("-an", cmd)


if __name__ == "__main__":
    unittest.main()
