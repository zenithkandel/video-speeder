import argparse
import sys
import time
from pathlib import Path
from typing import List, Optional

# Enforce UTF-8 output on Windows consoles to prevent cp1252 charmap encoding errors
if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.prompt import Confirm, FloatPrompt, Prompt
from rich.table import Table
from rich.text import Text

from .config import (
    APP_NAME,
    APP_TAGLINE,
    APP_VERSION,
    AVAILABLE_CODECS,
    AVAILABLE_PRESETS,
    DEFAULT_CRF,
    DEFAULT_PRESET,
    DEFAULT_VIDEO_CODEC,
    MAX_SPEED_MULTIPLIER,
    MIN_SPEED_MULTIPLIER,
    SUPPORTED_EXTENSIONS,
)
from .core import SpeedJobConfig, SpeedJobResult, VideoSpeeder
from .processor import BatchProcessor, BatchSummary
from .utils import (
    check_ffmpeg_installation,
    format_bytes,
    format_duration,
)

console = Console()


def print_banner():
    """Prints the application banner."""
    banner_text = Text()
    banner_text.append(f"⚡ {APP_NAME} ", style="bold cyan")
    banner_text.append(f"v{APP_VERSION}\n", style="dim cyan")
    banner_text.append(f"{APP_TAGLINE}\n", style="italic white")
    banner_text.append("100% Local • Zero Cloud • Hardware Accelerated FFmpeg Engine", style="dim green")

    panel = Panel(
        banner_text,
        border_style="cyan",
        expand=False,
        padding=(1, 2),
    )
    console.print(panel)


def run_doctor():
    """Performs diagnostic checks on FFmpeg and system dependencies."""
    console.print("\n[bold cyan]🔍 Running System Diagnostics...[/bold cyan]\n")
    diag = check_ffmpeg_installation()

    table = Table(title="Dependency Status", show_header=True, header_style="bold magenta")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Details", style="white")

    if diag["ffmpeg_available"]:
        table.add_row("FFmpeg Binary", "[green]✔ Installed[/green]", diag["ffmpeg_path"] or "In PATH")
    else:
        table.add_row("FFmpeg Binary", "[bold red]✘ Missing[/bold red]", "FFmpeg is not found in your system PATH")

    if diag["ffprobe_available"]:
        table.add_row("FFprobe Binary", "[green]✔ Installed[/green]", diag["ffprobe_path"] or "In PATH")
    else:
        table.add_row("FFprobe Binary", "[bold yellow]! Missing[/bold yellow]", "FFprobe not found (fallback prober will be used)")

    # Encoders
    nvenc_status = "[green]✔ Available[/green]" if diag["nvenc_supported"] else "[dim]Not detected[/dim]"
    qsv_status = "[green]✔ Available[/green]" if diag["qsv_supported"] else "[dim]Not detected[/dim]"
    amf_status = "[green]✔ Available[/green]" if diag["amf_supported"] else "[dim]Not detected[/dim]"

    table.add_row("NVIDIA NVENC (GPU)", nvenc_status, "Hardware acceleration: --hwaccel nvenc")
    table.add_row("Intel QuickSync (QSV)", qsv_status, "Hardware acceleration: --hwaccel qsv")
    table.add_row("AMD AMF (GPU)", amf_status, "Hardware acceleration: --hwaccel amf")

    console.print(table)

    if not diag["ffmpeg_available"]:
        console.print("\n[bold red]⚠️ FFmpeg is required to run Video Speeder.[/bold red]")
        console.print("[yellow]To install FFmpeg on Windows:[/yellow]")
        console.print("  • Run: [bold cyan]winget install Gyan.FFmpeg[/bold cyan] or [bold cyan]choco install ffmpeg[/bold cyan]")
        console.print("[yellow]To install on macOS:[/yellow]")
        console.print("  • Run: [bold cyan]brew install ffmpeg[/bold cyan]")
        console.print("[yellow]To install on Ubuntu/Debian Linux:[/yellow]")
        console.print("  • Run: [bold cyan]sudo apt update && sudo apt install ffmpeg[/bold cyan]\n")
        return False
    else:
        if diag.get("version"):
            console.print(f"\n[dim]FFmpeg Version: {diag['version']}[/dim]\n")
        return True


def interactive_wizard() -> tuple[Path, float, Optional[Path], bool, bool, int]:
    """Guides the user through an interactive prompt session."""
    console.print("\n[bold cyan]✨ Interactive Setup Wizard[/bold cyan]")
    console.print("[dim]Enter the required details below to speed up your videos.[/dim]\n")

    # 1. Target Folder or File
    while True:
        target_str = Prompt.ask("[bold yellow]📁 Enter the target folder (or video file path)[/bold yellow]").strip('"').strip("'")
        target_path = Path(target_str).resolve()
        if not target_path.exists():
            console.print(f"[bold red]✘ Path not found:[/bold red] {target_path}. Please try again.")
            continue
        break

    # 2. Speed Multiplier
    while True:
        speed = FloatPrompt.ask(
            f"[bold yellow]⏩ Enter speed multiplier[/bold yellow] (e.g. 1.5, 2.0, 4.0, or 0.5 for slow-mo)",
            default=2.0,
        )
        if speed < MIN_SPEED_MULTIPLIER or speed > MAX_SPEED_MULTIPLIER:
            console.print(f"[bold red]✘ Invalid multiplier.[/bold red] Please enter a value between {MIN_SPEED_MULTIPLIER} and {MAX_SPEED_MULTIPLIER}.")
            continue
        break

    # 3. Output Directory
    default_out = f"speedup_{speed:g}x"
    out_choice = Prompt.ask(
        f"[bold yellow]💾 Output folder[/bold yellow] (leave blank for '[cyan]{default_out}[/cyan]' subfolder or enter custom path)",
        default=default_out,
    ).strip('"').strip("'")

    if out_choice == default_out:
        if target_path.is_file():
            output_dir = target_path.parent / default_out
        else:
            output_dir = target_path / default_out
    elif out_choice:
        output_dir = Path(out_choice).resolve()
    else:
        output_dir = None

    # 4. Recursive search (if target is directory)
    recursive = False
    if target_path.is_dir():
        recursive = Confirm.ask("[bold yellow]🔄 Scan subdirectories recursively?[/bold yellow]", default=False)

    # 5. Audio preference
    keep_audio = Confirm.ask("[bold yellow]🔊 Keep audio (with automatic pitch correction)?[/bold yellow]", default=True)

    # 6. Parallel workers
    workers = 1
    if target_path.is_dir():
        workers_prompt = Prompt.ask("[bold yellow]⚡ Number of parallel workers[/bold yellow] (1 for sequential, 2-4 for fast multi-threading)", default="1")
        try:
            workers = max(1, int(workers_prompt))
        except ValueError:
            workers = 1

    return target_path, speed, output_dir, recursive, not keep_audio, workers


def print_dry_run_table(jobs: List[tuple[Path, Path]], speed: float, speeder: VideoSpeeder):
    """Displays a planned execution table for dry run mode."""
    table = Table(
        title=f"📋 Dry Run Plan: {len(jobs)} Video(s) at {speed:g}x Speed",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("#", style="dim", justify="right", width=4)
    table.add_column("Input Video", style="white")
    table.add_column("Original Duration", style="yellow", justify="center")
    table.add_column(f"New Duration ({speed:g}x)", style="green", justify="center")
    table.add_column("Output File Path", style="dim cyan")

    total_orig_dur = 0.0
    total_new_dur = 0.0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Probing video durations...", total=len(jobs))

        for idx, (in_file, out_file) in enumerate(jobs, 1):
            try:
                meta = speeder.probe_metadata(in_file)
                orig_dur = meta.duration
                new_dur = orig_dur / speed if speed > 0 else 0.0
                total_orig_dur += orig_dur
                total_new_dur += new_dur
                orig_str = format_duration(orig_dur)
                new_str = format_duration(new_dur)
            except Exception:
                orig_str = "--:--"
                new_str = "--:--"

            table.add_row(
                str(idx),
                in_file.name,
                orig_str,
                new_str,
                str(out_file),
            )
            progress.advance(task)

    console.print(table)
    time_saved = max(0.0, total_orig_dur - total_new_dur)
    console.print(
        f"\n[bold]Total Original Duration:[/bold] [yellow]{format_duration(total_orig_dur)}[/yellow]  |  "
        f"[bold]Estimated New Duration:[/bold] [green]{format_duration(total_new_dur)}[/green]  |  "
        f"[bold]Viewing Time Saved:[/bold] [bold cyan]{format_duration(time_saved)}[/bold cyan]\n"
    )


def print_summary_table(summary: BatchSummary, total_wall_time: float):
    """Prints a styled results table after batch execution."""
    table = Table(
        title="📊 Processing Summary Report",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("File Name", style="white")
    table.add_column("Original", style="yellow", justify="center")
    table.add_column("Output", style="green", justify="center")
    table.add_column("Speed", style="cyan", justify="center")
    table.add_column("Original Size", style="dim", justify="right")
    table.add_column("Output Size", style="dim", justify="right")
    table.add_column("Encode Time", style="blue", justify="right")
    table.add_column("Status", style="bold", justify="center")

    for res in summary.results:
        if res.success:
            if res.error_message == "Skipped (already exists)":
                status_str = "[yellow]SKIPPED[/yellow]"
            else:
                status_str = "[green]SUCCESS[/green]"
        else:
            status_str = "[bold red]FAILED[/bold red]"

        orig_dur_str = format_duration(res.original_duration) if res.original_duration > 0 else "--:--"
        out_dur_str = format_duration(res.output_duration) if res.output_duration > 0 else "--:--"
        orig_sz_str = format_bytes(res.original_size) if res.original_size > 0 else "--"
        out_sz_str = format_bytes(res.output_size) if res.output_size > 0 else "--"
        elapsed_str = f"{res.elapsed_time:.1f}s" if res.elapsed_time > 0 else "--"

        table.add_row(
            res.input_path.name,
            orig_dur_str,
            out_dur_str,
            f"{res.speed:g}x",
            orig_sz_str,
            out_sz_str,
            elapsed_str,
            status_str,
        )

    console.print("\n")
    console.print(table)

    # Overview statistics box
    stats_text = Text()
    stats_text.append(f"📁 Total Files: {summary.total_files}   ", style="bold white")
    stats_text.append(f"✔ Successful: {summary.successful_files}   ", style="bold green")
    if summary.skipped_files > 0:
        stats_text.append(f"⚠️ Skipped: {summary.skipped_files}   ", style="bold yellow")
    if summary.failed_files > 0:
        stats_text.append(f"✘ Failed: {summary.failed_files}   ", style="bold red")
    stats_text.append(f"\n⏱️ Total Encoding Time: {total_wall_time:.2f}s   ", style="bold cyan")
    if summary.total_original_duration > 0:
        saved_dur = max(0.0, summary.total_original_duration - summary.total_output_duration)
        stats_text.append(f"🎬 Watch Time Saved: {format_duration(saved_dur)}", style="bold magenta")

    console.print(Panel(stats_text, border_style="green" if summary.failed_files == 0 else "yellow", padding=(1, 2)))

    # Print error details if any
    failed_results = [r for r in summary.results if not r.success]
    if failed_results:
        console.print("\n[bold red]⚠️ Error Details for Failed Files:[/bold red]")
        for f in failed_results:
            console.print(f"[bold red]• {f.input_path.name}:[/bold red] {f.error_message}")


def build_parser() -> argparse.ArgumentParser:
    """Builds the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="video-speeder",
        description=f"{APP_NAME} v{APP_VERSION} - {APP_TAGLINE}",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help="Target folder containing videos or a single video file path.",
    )

    parser.add_argument(
        "-s", "--speed",
        type=float,
        default=None,
        help="Speed multiplier (e.g. 1.5, 2.0, 4.0, or 0.5 for slow-mo).",
    )

    parser.add_argument(
        "-o", "--output-dir",
        type=str,
        default=None,
        help="Destination directory for sped-up videos. Defaults to a subfolder 'speedup_<Nx>'.",
    )

    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="Recursively scan subfolders for video files.",
    )

    parser.add_argument(
        "-w", "--workers",
        type=int,
        default=1,
        help="Number of concurrent worker threads for parallel video processing.",
    )

    parser.add_argument(
        "--crf",
        type=int,
        default=DEFAULT_CRF,
        help=f"Constant Rate Factor (0-51) for video quality. Lower = better quality. Default: {DEFAULT_CRF}.",
    )

    parser.add_argument(
        "--preset",
        type=str,
        default=DEFAULT_PRESET,
        choices=AVAILABLE_PRESETS,
        help=f"FFmpeg encoding preset. Default: {DEFAULT_PRESET}.",
    )

    parser.add_argument(
        "--codec",
        type=str,
        default=DEFAULT_VIDEO_CODEC,
        choices=AVAILABLE_CODECS,
        help=f"Video codec to use. Default: {DEFAULT_VIDEO_CODEC}.",
    )

    parser.add_argument(
        "--hwaccel",
        type=str,
        choices=["nvenc", "qsv", "amf"],
        default=None,
        help="Enable GPU hardware acceleration (nvenc = NVIDIA, qsv = Intel, amf = AMD).",
    )

    parser.add_argument(
        "--no-audio", "--mute",
        action="store_true",
        dest="no_audio",
        help="Strip / mute audio track from the sped-up videos.",
    )

    parser.add_argument(
        "--fps",
        type=float,
        default=None,
        help="Force a specific output framerate (e.g. 30, 60). Default: keep original.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview files, estimated output paths, and durations without encoding.",
    )

    parser.add_argument(
        "-y", "--overwrite",
        action="store_true",
        default=True,
        help="Overwrite existing output files.",
    )

    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip files that already exist in the output destination.",
    )

    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Launch the interactive wizard to select folder and speed options.",
    )

    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Run system diagnostics to check FFmpeg installation and GPU acceleration.",
    )

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entrypoint."""
    if argv is None:
        argv = sys.argv[1:]

    parser = build_parser()
    args = parser.parse_args(argv)

    print_banner()

    # Doctor mode
    if args.doctor:
        healthy = run_doctor()
        return 0 if healthy else 1

    # Verify FFmpeg first
    diag = check_ffmpeg_installation()
    if not diag["ffmpeg_available"]:
        console.print("[bold red]Error: FFmpeg is not installed or not in system PATH.[/bold red]")
        console.print("Run [bold cyan]python main.py --doctor[/bold cyan] for setup instructions.")
        return 1

    # Interactive mode or missing arguments
    if args.interactive or (args.target is None and args.speed is None):
        target_path, speed, output_dir, recursive, mute_audio, workers = interactive_wizard()
        crf = args.crf
        preset = args.preset
        codec = args.codec
        hwaccel = args.hwaccel
        dry_run = False
        overwrite = not args.skip_existing
        fps = args.fps
    else:
        if args.target is None:
            console.print("[bold red]Error: Missing target video folder or file path.[/bold red]")
            console.print("Usage: [cyan]python main.py <target_folder> -s <multiplier>[/cyan] or use [cyan]--interactive[/cyan]")
            return 1

        target_path = Path(args.target).resolve()
        if not target_path.exists():
            console.print(f"[bold red]Error: Path does not exist:[/bold red] {target_path}")
            return 1

        if args.speed is None:
            console.print("[bold red]Error: Speed multiplier (-s / --speed) is required.[/bold red]")
            console.print("Example: [cyan]python main.py . -s 2.0[/cyan]")
            return 1

        speed = args.speed
        if speed < MIN_SPEED_MULTIPLIER or speed > MAX_SPEED_MULTIPLIER:
            console.print(f"[bold red]Error: Speed multiplier must be between {MIN_SPEED_MULTIPLIER} and {MAX_SPEED_MULTIPLIER}.[/bold red]")
            return 1

        if args.output_dir:
            output_dir = Path(args.output_dir).resolve()
        else:
            default_folder = f"speedup_{speed:g}x"
            if target_path.is_file():
                output_dir = target_path.parent / default_folder
            else:
                output_dir = target_path / default_folder

        recursive = args.recursive
        mute_audio = args.no_audio
        workers = args.workers
        crf = args.crf
        preset = args.preset
        codec = args.codec
        hwaccel = args.hwaccel
        dry_run = args.dry_run
        overwrite = not args.skip_existing
        fps = args.fps

    speeder = VideoSpeeder()
    processor = BatchProcessor(speeder=speeder, max_workers=workers)

    # Discover files
    try:
        jobs = processor.plan_batch(
            target_path=target_path,
            speed=speed,
            output_dir=output_dir,
            recursive=recursive,
        )
    except Exception as ex:
        console.print(f"[bold red]Error scanning directory:[/bold red] {ex}")
        return 1

    if not jobs:
        console.print(f"[bold yellow]No supported video files found in:[/bold yellow] {target_path}")
        console.print(f"[dim]Supported formats: {', '.join(sorted(SUPPORTED_EXTENSIONS))}[/dim]")
        return 0

    # Dry-run mode
    if dry_run:
        print_dry_run_table(jobs, speed, speeder)
        return 0

    # Confirmation & Info Header
    console.print("\n[bold]⚙️  Job Configuration:[/bold]")
    console.print(f"  • [cyan]Target Path:[/cyan]      {target_path} ({'Recursive' if recursive else 'Flat'})")
    console.print(f"  • [cyan]Speed Multiplier:[/cyan] [bold green]{speed:g}x[/bold green]")
    console.print(f"  • [cyan]Output Directory:[/cyan] {output_dir}")
    console.print(f"  • [cyan]Total Videos:[/cyan]     [bold white]{len(jobs)}[/bold white]")
    console.print(f"  • [cyan]Audio Track:[/cyan]      {'[red]Muted / Stripped[/red]' if mute_audio else '[green]Preserved (Pitch Adjusted)[/green]'}")
    console.print(f"  • [cyan]Video Codec:[/cyan]      {codec} (Preset: {preset}, CRF: {crf})")
    if hwaccel:
        console.print(f"  • [cyan]HW Acceleration:[/cyan]  [green]{hwaccel.upper()}[/green]")
    console.print(f"  • [cyan]Workers:[/cyan]          {workers} thread(s)\n")

    config = SpeedJobConfig(
        speed=speed,
        video_codec=codec,
        crf=crf,
        preset=preset,
        keep_audio=not mute_audio,
        mute_audio=mute_audio,
        target_fps=fps,
        overwrite=overwrite,
        hardware_accel=hwaccel,
    )

    # Live Rich Progress Bar Setup
    overall_progress = Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=None),
        TaskProgressColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    )

    file_progress = Progress(
        TextColumn("[bold yellow]{task.description}"),
        BarColumn(bar_width=None),
        TaskProgressColumn(),
        TextColumn("[dim cyan]{task.fields[info]}"),
        console=console,
    )

    progress_group = Panel(
        overall_progress,
        title="[bold cyan]🚀 Acceleration Progress[/bold cyan]",
        border_style="cyan",
    )

    task_map: dict[Path, TaskID] = {}
    active_file_task: Optional[TaskID] = None

    overall_task = overall_progress.add_task("Overall Batch", total=len(jobs))

    def on_job_start(in_p: Path, out_p: Path, total: int):
        pass

    def on_job_progress(in_p: Path, pct: float, sec: float, fps: float):
        info_str = f"{sec:.1f}s | {fps:.0f} fps" if fps > 0 else f"{sec:.1f}s"
        if in_p not in task_map:
            t_id = overall_progress.add_task(f"📹 {in_p.name[:25]}...", total=100.0)
            task_map[in_p] = t_id
        overall_progress.update(task_map[in_p], completed=pct)

    def on_job_finish(res: SpeedJobResult):
        overall_progress.advance(overall_task, 1)
        if res.input_path in task_map:
            overall_progress.remove_task(task_map[res.input_path])

    start_wall_time = time.time()

    with overall_progress:
        summary = processor.execute_batch(
            jobs=jobs,
            config=config,
            on_start=on_job_start,
            on_progress=on_job_progress,
            on_finish=on_job_finish,
        )

    total_wall_time = time.time() - start_wall_time
    print_summary_table(summary, total_wall_time)

    return 0 if summary.failed_files == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
