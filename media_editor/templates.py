from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Sequence, Union

from . import stills, video

PathLike = Union[str, Path]


@dataclass(frozen=True)
class FramePreset:
    name: str
    width: int
    height: int
    fps: int
    video_bitrate: str = "6M"
    audio_bitrate: str = "192k"
    description: str = ""
    orientation: str = "landscape"


_PRESETS: Dict[str, FramePreset] = {
    "widescreen_1080p": FramePreset(
        name="widescreen_1080p",
        width=1920,
        height=1080,
        fps=30,
        video_bitrate="8M",
        description="Standard 1080p landscape render for long-form YouTube uploads.",
    ),
    "shorts_vertical": FramePreset(
        name="shorts_vertical",
        width=1080,
        height=1920,
        fps=60,
        video_bitrate="12M",
        description="Vertical 9:16 preset optimized for Shorts/Reels.",
        orientation="portrait",
    ),
    "square_social": FramePreset(
        name="square_social",
        width=1080,
        height=1080,
        fps=30,
        video_bitrate="6M",
        description="Square format for Instagram feed or podcast teasers.",
        orientation="square",
    ),
}


def register_preset(preset: FramePreset) -> None:
    """Allow callers to add custom presets at runtime."""

    _PRESETS[preset.name] = preset


def list_presets() -> list[FramePreset]:
    return sorted(_PRESETS.values(), key=lambda preset: preset.name)


def get_preset(name: str) -> FramePreset:
    try:
        return _PRESETS[name]
    except KeyError as exc:  # pragma: no cover - defensive
        raise ValueError(f"Unknown preset: {name}") from exc


def render_still_from_preset(
    *,
    preset_name: str,
    image_path: PathLike,
    audio_path: PathLike,
    output_path: PathLike,
    copy_audio: bool = True,
) -> Path:
    preset = get_preset(preset_name)
    stills.still_with_audio(
        image_path=image_path,
        audio_path=audio_path,
        output_path=output_path,
        fps=preset.fps,
        bitrate=preset.video_bitrate,
        audio_bitrate=preset.audio_bitrate,
        width=preset.width,
        height=preset.height,
        copy_audio=copy_audio,
    )
    return Path(output_path)


def render_slideshow_from_preset(
    *,
    preset_name: str,
    photos: Sequence[PathLike],
    audio_path: PathLike,
    output_path: PathLike,
) -> Path:
    preset = get_preset(preset_name)
    stills.slideshow_with_audio(
        photo_paths=photos,
        audio_path=audio_path,
        output_path=output_path,
        fps=preset.fps,
        bitrate=preset.video_bitrate,
        audio_bitrate=preset.audio_bitrate,
    )
    return Path(output_path)


def fill_video_with_preset(
    *,
    preset_name: str,
    video_path: PathLike,
    output_path: PathLike,
    audio_codec: str = "copy",
) -> Path:
    preset = get_preset(preset_name)
    video.fill_frame(
        video_path=video_path,
        output_path=output_path,
        target_resolution=(preset.width, preset.height),
        audio_codec=audio_codec,
        video_codec="libx264",
        crf=18,
    )
    return Path(output_path)


def describe_preset(name: str) -> str:
    preset = get_preset(name)
    return (
        f"{preset.name}: {preset.width}x{preset.height}@{preset.fps}fps "
        f"({preset.orientation}) - {preset.description}"
    )
