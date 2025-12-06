from __future__ import annotations

import math
import tempfile
from pathlib import Path
from typing import List, Sequence, Tuple, Union

from moviepy.editor import AudioFileClip, VideoFileClip, concatenate_videoclips, vfx
from moviepy.video.fx.all import crop

from .ffmpeg_utils import concat_via_filelist, ensure_even_pair, run_ffmpeg

PathLike = Union[str, Path]


def _ensure_paths(paths: Sequence[PathLike], kind: str) -> list[Path]:
    resolved = [Path(path) for path in paths]
    if not resolved:
        raise ValueError(f"{kind} must contain at least one entry")
    for idx, path in enumerate(resolved, start=1):
        if not path.exists():
            raise FileNotFoundError(f"{kind} entry {idx} not found: {path}")
    return resolved


def concat_videos(
    inputs: Sequence[PathLike],
    output: PathLike,
    *,
    force_reencode: bool = False,
    video_codec: str = "libx264",
    audio_codec: str = "aac",
    video_bitrate: str = "6M",
    audio_bitrate: str = "192k",
    fps: float | None = None,
    width: int | None = None,
    height: int | None = None,
) -> None:
    """Concatenate multiple videos, optionally re-encoding to align parameters."""

    clips = _ensure_paths(inputs, "inputs")
    if len(clips) < 2:
        raise ValueError("Need at least two clips to concatenate")

    destination = Path(output)

    if not force_reencode:
        concat_via_filelist(clips, destination)
        return

    merged: VideoFileClip | None = None
    handles: list[VideoFileClip] = []

    try:
        for clip_path in clips:
            clip = VideoFileClip(str(clip_path))
            if width and height:
                clip = clip.resize(newsize=(width, height))
            if fps:
                clip = clip.set_fps(fps)
            handles.append(clip)
        merged = concatenate_videoclips(handles, method="compose")
        merged.write_videofile(
            str(destination),
            codec=video_codec,
            audio_codec=audio_codec,
            bitrate=video_bitrate,
            audio_bitrate=audio_bitrate,
            fps=fps or handles[0].fps,
        )
    finally:
        if merged is not None:
            merged.close()
        for clip in handles:
            clip.close()


def slowmotion_montage(
    video_paths: Sequence[PathLike],
    output_path: PathLike,
    *,
    slow_factor: float = 0.4,
    fps: float | None = None,
    video_bitrate: str = "6M",
    codec: str = "libx264",
) -> None:
    """Mute, slow down, and concatenate clips for highlight reels."""

    if slow_factor <= 0:
        raise ValueError("slow_factor must be positive")

    clips = _ensure_paths(video_paths, "video_paths")
    handles: list[VideoFileClip] = []
    merged: VideoFileClip | None = None

    try:
        for clip_path in clips:
            clip = VideoFileClip(str(clip_path)).without_audio()
            slowed = clip.fx(vfx.speedx, factor=slow_factor)
            if fps:
                slowed = slowed.set_fps(fps)
            handles.append(slowed)
        merged = concatenate_videoclips(handles, method="compose")
        merged.write_videofile(
            str(output_path),
            codec=codec,
            audio=False,
            fps=fps or handles[0].fps,
            bitrate=video_bitrate,
        )
    finally:
        if merged is not None:
            merged.close()
        for clip in handles:
            clip.close()


def stretch_video_to_audio(
    video_path: PathLike,
    audio_path: PathLike,
    output_path: PathLike,
    *,
    max_fps: float | None = None,
    video_bitrate: str = "6M",
    codec: str = "libx264",
    audio_codec: str = "aac",
) -> None:
    """Stretch video speed so its duration matches the provided audio."""

    video_file = Path(video_path)
    audio_file = Path(audio_path)
    if not video_file.exists():
        raise FileNotFoundError(f"Video not found: {video_file}")
    if not audio_file.exists():
        raise FileNotFoundError(f"Audio not found: {audio_file}")

    with VideoFileClip(str(video_file)) as video_clip, AudioFileClip(str(audio_file)) as audio_clip:
        if video_clip.duration == 0:
            raise ValueError("Video duration cannot be zero")

        target_duration = audio_clip.duration
        scale_factor = target_duration / video_clip.duration
        stretched = video_clip.fx(vfx.speedx, factor=scale_factor).set_audio(audio_clip)

        if max_fps is not None and video_clip.fps > max_fps:
            stretched = stretched.set_fps(max_fps)
        else:
            stretched = stretched.set_fps(video_clip.fps)

        try:
            stretched.write_videofile(
                str(output_path),
                codec=codec,
                audio_codec=audio_codec,
                bitrate=video_bitrate,
            )
        finally:
            stretched.close()


def fill_frame(
    video_path: PathLike,
    output_path: PathLike,
    *,
    target_resolution: Tuple[int, int] = (1920, 1080),
    video_codec: str = "libx264",
    audio_codec: str = "copy",
    crf: int = 18,
    preset: str = "medium",
) -> None:
    """Scale and crop to fill the target frame without pillarboxing."""

    source = Path(video_path)
    if not source.exists():
        raise FileNotFoundError(f"Video not found: {source}")

    destination = Path(output_path)
    width, height = ensure_even_pair(*target_resolution)
    filter_chain = (
        f"scale=w={width}:h={height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height}"
    )

    args = [
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-vf",
        filter_chain,
        "-c:v",
        video_codec,
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-c:a",
        audio_codec,
        "-movflags",
        "+faststart",
        str(destination),
    ]
    run_ffmpeg(args)


def zoom_section_moviepy(
    video_path: PathLike,
    output_path: PathLike,
    *,
    zoom_start: float,
    zoom_end: float | None = None,
    zoom_factor: float = 1.2,
    target_resolution: Tuple[int, int] | None = None,
    codec: str = "libx264",
    audio_codec: str = "aac",
    bitrate: str = "6M",
    fps: float | None = None,
) -> None:
    """Apply a zoom effect between timestamps via MoviePy for quick previews."""

    source = Path(video_path)
    if not source.exists():
        raise FileNotFoundError(f"Video not found: {source}")

    if zoom_start < 0:
        raise ValueError("zoom_start must be >= 0")

    destination = Path(output_path)

    with VideoFileClip(str(source)) as clip:
        zoom_stop = zoom_end if zoom_end is not None else clip.duration
        zoom_stop = min(max(zoom_start, zoom_stop), clip.duration)

        segments: List[VideoFileClip] = []

        if zoom_start > 0:
            pre = clip.subclip(0, zoom_start)
            if fps:
                pre = pre.set_fps(fps)
            segments.append(pre)

        zoom_clip = clip.subclip(zoom_start, zoom_stop).fx(vfx.resize, zoom_factor)
        target_w, target_h = target_resolution or (clip.w, clip.h)
        zoom_clip = crop(zoom_clip, width=target_w, height=target_h)
        if fps:
            zoom_clip = zoom_clip.set_fps(fps)
        segments.append(zoom_clip)

        if zoom_stop < clip.duration:
            post = clip.subclip(zoom_stop, clip.duration)
            if fps:
                post = post.set_fps(fps)
            segments.append(post)

        final_clip = concatenate_videoclips(segments, method="compose")
        try:
            final_clip.write_videofile(
                str(destination),
                codec=codec,
                audio_codec=audio_codec,
                bitrate=bitrate,
                fps=fps or clip.fps,
            )
        finally:
            final_clip.close()
            for segment in segments:
                segment.close()


def zoom_time_range_ffmpeg(
    video_path: PathLike,
    output_path: PathLike,
    *,
    zoom_start: float,
    zoom_end: float,
    zoom_factor: float = 1.2,
    video_codec: str = "libx264",
    audio_codec: str = "aac",
    video_bitrate: str = "6M",
    crf: int = 18,
    preset: str = "medium",
) -> None:
    """Use FFmpeg to zoom a precise time range without re-encoding unaffected parts."""

    source = Path(video_path)
    if not source.exists():
        raise FileNotFoundError(f"Video not found: {source}")

    with VideoFileClip(str(source)) as clip:
        duration = clip.duration
        base_width, base_height = ensure_even_pair(clip.w, clip.h)

    if not (0 <= zoom_start < zoom_end <= duration):
        raise ValueError("zoom_start and zoom_end must live inside the clip duration")

    zoom_w = math.ceil(base_width * zoom_factor / 2) * 2
    zoom_h = math.ceil(base_height * zoom_factor / 2) * 2
    zoom_filter = f"scale={zoom_w}:{zoom_h},crop={base_width}:{base_height}"

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        segments: list[Path] = []

        def _transcode_segment(start: float, duration_sec: float, name: str, filter_arg: str | None) -> Path:
            segment_path = tmp_path / name
            args = [
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                f"{start}",
                "-i",
                str(source),
                "-t",
                f"{duration_sec}",
            ]
            if filter_arg:
                args.extend(["-vf", filter_arg])
            args.extend(
                [
                    "-c:v",
                    video_codec,
                    "-b:v",
                    video_bitrate,
                    "-preset",
                    preset,
                    "-crf",
                    str(crf),
                    "-c:a",
                    audio_codec,
                    "-movflags",
                    "+faststart",
                    str(segment_path),
                ]
            )
            run_ffmpeg(args)
            return segment_path

        if zoom_start > 0:
            segments.append(_transcode_segment(0, zoom_start, "segment_pre.mp4", None))

        segments.append(
            _transcode_segment(zoom_start, zoom_end - zoom_start, "segment_zoom.mp4", zoom_filter)
        )

        if zoom_end < duration:
            segments.append(
                _transcode_segment(zoom_end, duration - zoom_end, "segment_post.mp4", None)
            )

        concat_list = tmp_path / "concat_list.txt"
        with concat_list.open("w", encoding="utf-8") as handle:
            for segment in segments:
                handle.write(f"file '{segment.as_posix()}'\n")

        args_concat = [
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c",
            "copy",
            str(output_path),
        ]
        run_ffmpeg(args_concat)
