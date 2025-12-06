from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Iterable, Sequence

from imageio_ffmpeg import get_ffmpeg_exe


class FFmpegNotFoundError(RuntimeError):
    """Raised when the FFmpeg binary cannot be located."""


def ffmpeg_path() -> Path:
    path = Path(get_ffmpeg_exe())
    if not path.exists():
        raise FFmpegNotFoundError("FFmpeg binary not found. Install imageio-ffmpeg or FFmpeg.")
    return path


def run_ffmpeg(args: Sequence[str]) -> None:
    cmd = [str(ffmpeg_path()), *args]
    subprocess.run(cmd, check=True)


def concat_via_filelist(files: Sequence[Path], output: Path, *, copy: bool = True) -> None:
    """Concatenate media files using FFmpeg's concat demuxer."""

    if not files:
        raise ValueError("files must contain at least one entry")

    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".txt") as handle:
        for file in files:
            handle.write(f"file '{file.resolve().as_posix().replace("'", "'\\''")}'\n")
        list_path = Path(handle.name)

    try:
        args = [
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
        ]
        if copy:
            args.extend(["-c", "copy"])
        else:
            args.extend(["-c:v", "libx264", "-c:a", "aac"])
        args.append(str(output))
        run_ffmpeg(args)
    finally:
        list_path.unlink(missing_ok=True)


def ensure_even(value: int) -> int:
    return value if value % 2 == 0 else value - 1


def ensure_even_pair(width: int, height: int) -> tuple[int, int]:
    return ensure_even(width), ensure_even(height)
