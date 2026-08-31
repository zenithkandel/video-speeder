"""
Batch processor handling parallel and sequential video speed transformation jobs.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from .core import SpeedJobConfig, SpeedJobResult, VideoSpeeder
from .utils import calculate_output_path, find_video_files


@dataclass
class BatchSummary:
    """Consolidated summary metrics for a completed batch run."""
    total_files: int
    successful_files: int
    failed_files: int
    skipped_files: int
    total_original_duration: float
    total_output_duration: float
    total_original_size: int
    total_output_size: int
    total_elapsed_time: float
    results: List[SpeedJobResult]


class BatchProcessor:
    """
    Manages discovery, output path resolution, and concurrent execution of video speed jobs.
    """

    def __init__(
        self,
        speeder: Optional[VideoSpeeder] = None,
        max_workers: int = 1,
    ):
        self.speeder = speeder or VideoSpeeder()
        self.max_workers = max(1, max_workers)

    def plan_batch(
        self,
        target_path: Path,
        speed: float,
        output_dir: Optional[Path] = None,
        recursive: bool = False,
        preserve_hierarchy: bool = True,
        suffix: Optional[str] = None,
    ) -> List[tuple[Path, Path]]:
        """
        Scans source files and returns a list of (input_path, output_path) tuples.
        """
        source = Path(target_path).resolve()
        video_files = find_video_files(source, recursive=recursive)

        jobs: List[tuple[Path, Path]] = []
        for vfile in video_files:
            out_file = calculate_output_path(
                input_file=vfile,
                base_input_dir=source,
                output_dir=output_dir,
                speed=speed,
                preserve_hierarchy=preserve_hierarchy,
                suffix=suffix,
            )
            jobs.append((vfile, out_file))

        return jobs

    def execute_batch(
        self,
        jobs: List[tuple[Path, Path]],
        config: SpeedJobConfig,
        on_start: Optional[Callable[[Path, Path, int], None]] = None,
        on_progress: Optional[Callable[[Path, float, float, float], None]] = None,
        on_finish: Optional[Callable[[SpeedJobResult], None]] = None,
    ) -> BatchSummary:
        """
        Executes speed adjustment jobs with configurable concurrency.
        """
        results: List[SpeedJobResult] = []
        total_jobs = len(jobs)

        if total_jobs == 0:
            return BatchSummary(
                total_files=0,
                successful_files=0,
                failed_files=0,
                skipped_files=0,
                total_original_duration=0.0,
                total_output_duration=0.0,
                total_original_size=0,
                total_output_size=0,
                total_elapsed_time=0.0,
                results=[],
            )

        def worker_task(in_path: Path, out_path: Path) -> SpeedJobResult:
            if on_start:
                on_start(in_path, out_path, total_jobs)

            def progress_hook(pct: float, sec: float, fps: float):
                if on_progress:
                    on_progress(in_path, pct, sec, fps)

            res = self.speeder.process_video(
                input_path=in_path,
                output_path=out_path,
                config=config,
                progress_callback=progress_hook,
            )

            if on_finish:
                on_finish(res)

            return res

        # If max_workers == 1, run sequentially for deterministic logging
        if self.max_workers == 1:
            for in_path, out_path in jobs:
                res = worker_task(in_path, out_path)
                results.append(res)
        else:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_map = {
                    executor.submit(worker_task, in_p, out_p): (in_p, out_p)
                    for in_p, out_p in jobs
                }
                for future in as_completed(future_map):
                    try:
                        res = future.result()
                        results.append(res)
                    except Exception as ex:
                        in_p, out_p = future_map[future]
                        err_res = SpeedJobResult(
                            input_path=in_p,
                            output_path=out_path,
                            speed=config.speed,
                            success=False,
                            error_message=str(ex),
                        )
                        results.append(err_res)
                        if on_finish:
                            on_finish(err_res)

        # Aggregate statistics
        successful = sum(1 for r in results if r.success and r.error_message != "Skipped (already exists)")
        skipped = sum(1 for r in results if r.error_message == "Skipped (already exists)")
        failed = sum(1 for r in results if not r.success)
        tot_orig_dur = sum(r.original_duration for r in results if r.success)
        tot_out_dur = sum(r.output_duration for r in results if r.success)
        tot_orig_sz = sum(r.original_size for r in results if r.success)
        tot_out_sz = sum(r.output_size for r in results if r.success)
        tot_elapsed = sum(r.elapsed_time for r in results)

        return BatchSummary(
            total_files=total_jobs,
            successful_files=successful,
            failed_files=failed,
            skipped_files=skipped,
            total_original_duration=tot_orig_dur,
            total_output_duration=tot_out_dur,
            total_original_size=tot_orig_sz,
            total_output_size=tot_out_sz,
            total_elapsed_time=tot_elapsed,
            results=results,
        )
