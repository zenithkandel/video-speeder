# ⚡ Video Speeder CLI

> **High-Performance, 100% Local Video Speed Acceleration & Slow-Motion Engine**  
> *CLI-only tool to batch speed up or slow down videos with automatic audio tempo and pitch synchronization.*

---

## 🌟 Highlights

- **100% Offline & Local**: Zero cloud dependencies or subscriptions. All processing is powered natively by FFmpeg on your local machine.
- **Extreme Speed Multipliers (0.01x to 10,000x)**: Smoothly handles everything from ultra slow-motion (`0.25x`, `0.5x`) to standard speedups (`1.5x`, `2.0x`, `4.0x`) and extreme timelapse speeds (`50x`, `200x`, `500x`, `1000x`+).
- **Intelligent Audio Tempo Synchronization**: Automatically decomposes and chains optimal FFmpeg `atempo` filtergraphs (e.g., $200\times \rightarrow 8$ chained filters) to preserve pitch without crashing.
- **Rich Terminal User Interface**: Interactive setup wizard, real-time encoding progress, live per-file status bars, and formatted batch summary reports.
- **High-Throughput Multithreading**: Process entire video folders in parallel utilizing multi-core worker threads.
- **Hardware Acceleration Ready**: Seamlessly toggle NVIDIA NVENC (`--hwaccel nvenc`), Intel QuickSync (`--hwaccel qsv`), or AMD AMF (`--hwaccel amf`).
- **Flexible Batch Management**: Recursive subdirectory scanning, configurable output destinations, dry-run mode, and resume/skip-existing logic.

---

## 📦 Requirements & Prerequisites

### 1. Python
- **Python 3.8+** (Tested on Python 3.11 & 3.12)

### 2. FFmpeg
**Video Speeder** requires [FFmpeg](https://ffmpeg.org/) installed and available in your system's `PATH`.

#### 🪟 Windows Setup:
```powershell
# Using Windows Package Manager (winget)
winget install Gyan.FFmpeg

# Or using Chocolatey
choco install ffmpeg

# Or using Scoop
scoop install ffmpeg
```

#### 🍏 macOS Setup:
```bash
brew install ffmpeg
```

#### 🐧 Linux (Ubuntu / Debian / Arch):
```bash
# Ubuntu / Debian
sudo apt update && sudo apt install ffmpeg

# Arch Linux
sudo pacman -S ffmpeg
```

> 💡 **Self-Diagnostic**: You can verify your FFmpeg setup anytime by running:
> ```bash
> python main.py --doctor
> ```

---

## 🚀 Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/zenithkandel/video-speeder.git
   cd video-speeder
   ```

2. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. *(Optional)* **Install as a global CLI tool:**
   ```bash
   pip install -e .
   ```
   *Once installed, you can use the commands `video-speeder` or `vspeed` from anywhere in your terminal!*

---

## 🎮 Quick Start

### 1. Interactive Mode (No Arguments)
Simply run without arguments or with `--interactive` to launch the guided terminal wizard:
```bash
python main.py
```
```
✨ Interactive Setup Wizard
📁 Enter the target folder (or video file path): C:\Videos\Tutorials
⏩ Enter speed multiplier: 2.0
💾 Output folder [speedup_2x]:
🔄 Scan subdirectories recursively? [y/N]: n
🔊 Keep audio (with automatic pitch correction)? [Y/n]: y
⚡ Number of parallel workers [1]: 2
```

---

### 2. Command Line Usage

#### ⏩ Speed up all videos in a folder by 2x:
```bash
python main.py /path/to/videos -s 2.0
```

#### 🐌 Slow down a video to half-speed (0.5x):
```bash
python main.py /path/to/video.mp4 -s 0.5
```

#### 📁 Recursive directory processing with custom output folder:
```bash
python main.py "D:\Course Videos" -s 1.75 -r -o "D:\Course Videos 1.75x"
```

#### ⚡ Fast parallel batch processing (4 worker threads):
```bash
python main.py ./raw_footage -s 2.0 -w 4 --preset ultrafast
```

#### 🔇 Remove / mute audio track:
```bash
python main.py ./recordings -s 3.0 --no-audio
```

#### 📋 Dry-Run Mode (Preview estimated durations without encoding):
```bash
python main.py ./lectures -s 2.0 --dry-run
```

#### 🚀 GPU Hardware Acceleration (NVIDIA NVENC):
```bash
python main.py ./renders -s 2.0 --hwaccel nvenc
```

---

## ⚙️ Command-Line Options Reference

| Flag / Option | Shorthand | Type | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `target` | Positional | `str` | `None` | Path to target video folder or single video file. |
| `--speed` | `-s` | `float` | `None` | Speed multiplier (e.g. `1.5`, `2.0`, `4.0`, or `0.5`). |
| `--output-dir` | `-o` | `str` | `speedup_<Nx>` | Destination directory for speed-adjusted videos. |
| `--recursive` | `-r` | `flag` | `False` | Recursively scan subfolders for video files. |
| `--workers` | `-w` | `int` | `1` | Number of concurrent workers for parallel encoding. |
| `--dry-run` | | `flag` | `False` | Preview file list, estimated durations, and paths. |
| `--crf` | | `int` | `22` | Constant Rate Factor (0–51). Lower = higher quality. |
| `--preset` | | `choice` | `medium` | FFmpeg preset (`ultrafast`, `fast`, `medium`, `slow`). |
| `--codec` | | `choice` | `libx264` | Video encoder (`libx264`, `libx265`, `h264_nvenc`, etc.). |
| `--hwaccel` | | `choice` | `None` | Hardware acceleration backend (`nvenc`, `qsv`, `amf`). |
| `--no-audio` / `--mute` | | `flag` | `False` | Strip/mute audio from the output video. |
| `--fps` | | `float` | `None` | Force a specific output framerate (e.g. `30`, `60`). |
| `--skip-existing` | | `flag` | `False` | Skip files that already exist in the destination folder. |
| `--interactive` | `-i` | `flag` | `False` | Launch interactive configuration wizard. |
| `--doctor` | | `flag` | `False` | Run diagnostic check on FFmpeg & GPU support. |

---

## 🎥 Supported Formats

Video Speeder automatically detects and processes all major media containers:
- `.mp4`, `.mkv`, `.mov`, `.avi`, `.webm`
- `.flv`, `.wmv`, `.m4v`, `.ts`, `.mts`, `.m2ts`, `.3gp`

---

## 🔬 How It Works

1. **Video Timestamp Scaling**:  
   Modifies Presentation Timestamps (PTS) using FFmpeg's video filter:
   $$\text{setpts} = \left(\frac{1}{\text{speed}}\right) \times \text{PTS}$$

2. **Chained Audio Tempo Synchronization**:  
   FFmpeg's `atempo` audio filter is bounded between `0.5` and `2.0`. Video Speeder mathematically decomposes arbitrary multipliers into a chain of optimal `atempo` filters (e.g., $4.0\times \rightarrow \texttt{atempo=2.0,atempo=2.0}$; $0.25\times \rightarrow \texttt{atempo=0.5,atempo=0.5}$).

3. **Lossless Quality Balancing**:  
   Uses standard H.264 `yuv420p` color space with CRF 22 and `+faststart` moov-atom optimization, ensuring maximum compatibility across mobile players and browsers.

---

## 🧪 Running Unit Tests

Run the automated test suite to verify filter graph construction, duration parsing, and path resolution:

```bash
python -m unittest discover -s tests -v
```

---

## 📄 License

Distributed under the **MIT License**. Free for personal and commercial use.
