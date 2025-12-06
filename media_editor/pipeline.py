from __future__ import annotations

import glob
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, MutableMapping, Sequence, Union

from . import stills, templates, video, youtube_automation

try:  # Optional dependency for YAML configs
    import yaml  # type: ignore
except Exception:  # pragma: no cover - yaml is optional
    yaml = None

PathLike = Union[str, Path]
logger = logging.getLogger(__name__)


class PipelineError(RuntimeError):
    pass


@dataclass
class PipelineContext:
    base_dir: Path
    variables: MutableMapping[str, Any] = field(default_factory=dict)
    artifacts: Dict[str, Any] = field(default_factory=dict)

    def remember(self, name: str, value: Any) -> None:
        if name:
            self.artifacts[name] = value

    def get_artifact(self, name: str) -> Any:
        if name not in self.artifacts:
            raise PipelineError(f"Artifact '{name}' not found. Available: {list(self.artifacts)}")
        return self.artifacts[name]

    def interpolate(self, value: str) -> str:
        try:
            return value.format(**self.variables)
        except KeyError as exc:
            raise PipelineError(f"Missing pipeline variable: {exc.args[0]}") from exc


def load_config(config_path: PathLike) -> dict[str, Any]:
    path = Path(config_path)
    if not path.exists():
        raise PipelineError(f"Config not found: {path}")
    data = path.read_text(encoding="utf-8")
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        if yaml is None:
            raise PipelineError("Install PyYAML to parse non-JSON pipeline configs")
        parsed = yaml.safe_load(data)
        if not isinstance(parsed, dict):
            raise PipelineError("Pipeline config must deserialize into a mapping")
        return parsed


def run_pipeline(
    config: Mapping[str, Any] | PathLike,
    *,
    variables: Mapping[str, Any] | None = None,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    if isinstance(config, (str, Path)):
        config_path = Path(config)
        config_data = load_config(config_path)
        base_dir = base_dir or config_path.parent
    else:
        config_data = dict(config)
        base_dir = base_dir or Path.cwd()

    context = PipelineContext(
        base_dir=base_dir,
        variables={**config_data.get("variables", {}), **(variables or {})},
    )

    steps = config_data.get("steps")
    if not isinstance(steps, Sequence):
        raise PipelineError("Pipeline config requires a 'steps' sequence")

    default_preset = config_data.get("preset")

    for idx, step in enumerate(steps, start=1):
        if not isinstance(step, Mapping):
            raise PipelineError(f"Step {idx} must be a mapping")
        _execute_step(step, context, default_preset=default_preset)

    return context.artifacts


StepHandler = Callable[[Mapping[str, Any], PipelineContext, str | None], Any]


def _execute_step(step: Mapping[str, Any], context: PipelineContext, *, default_preset: str | None) -> None:
    step_type = step.get("type")
    if not step_type:
        raise PipelineError("Each step requires a 'type'")

    handler = _STEP_HANDLERS.get(step_type)
    if handler is None:
        raise PipelineError(f"Unsupported step type: {step_type}")

    name = step.get("name", "")
    logger.info("Running step %s (%s)", name or step_type, step_type)
    artifact = handler(step, context, default_preset)
    if name and artifact is not None:
        context.remember(name, artifact)


def _resolve_value(value: Any, context: PipelineContext) -> Any:
    if isinstance(value, str):
        if value.startswith("@"):
            alias = value[1:]
            return context.get_artifact(alias)
        return context.interpolate(value)
    return value


def _resolve_path(value: Any, context: PipelineContext) -> Path:
    resolved = _resolve_value(value, context)
    if isinstance(resolved, Path):
        path = resolved
    else:
        path = Path(resolved)
    if not path.is_absolute():
        path = (context.base_dir / path).resolve()
    return path


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _collect_photos(step: Mapping[str, Any], context: PipelineContext) -> list[Path]:
    if "photos" in step:
        photos = [_resolve_path(photo, context) for photo in step["photos"]]
        if not photos:
            raise PipelineError("'photos' list cannot be empty")
        return photos

    if "photos_glob" in step:
        pattern_value = _resolve_value(step["photos_glob"], context)
        pattern = str(pattern_value)
        if not Path(pattern).is_absolute():
            pattern = str(context.base_dir / pattern)
        matches = sorted(Path(path).resolve() for path in glob.glob(pattern, recursive=True))
        if not matches:
            raise PipelineError(f"No photos matched glob pattern: {pattern_value}")
        return matches

    raise PipelineError("Slideshow step requires 'photos' or 'photos_glob'")


def _with_preset_defaults(step: Mapping[str, Any], preset_name: str | None) -> tuple[int | None, int | None, int | None, str | None, str | None]:
    if not preset_name:
        return (step.get("width"), step.get("height"), step.get("fps"), step.get("video_bitrate"), step.get("audio_bitrate"))
    preset = templates.get_preset(preset_name)
    width = step.get("width") or preset.width
    height = step.get("height") or preset.height
    fps = step.get("fps") or preset.fps
    video_bitrate = step.get("video_bitrate") or preset.video_bitrate
    audio_bitrate = step.get("audio_bitrate") or preset.audio_bitrate
    return width, height, fps, video_bitrate, audio_bitrate


def _handle_still(step: Mapping[str, Any], context: PipelineContext, default_preset: str | None) -> Path:
    image = _resolve_path(step["image"], context)
    audio = _resolve_path(step["audio"], context)
    output = _resolve_path(step["output"], context)
    _ensure_parent(output)

    preset_name = step.get("preset") or default_preset
    width, height, fps, video_bitrate, audio_bitrate = _with_preset_defaults(step, preset_name)

    stills.still_with_audio(
        image_path=image,
        audio_path=audio,
        output_path=output,
        fps=fps or 30,
        bitrate=video_bitrate or "4M",
        audio_bitrate=audio_bitrate or "192k",
        width=width,
        height=height,
        copy_audio=step.get("copy_audio", True),
    )
    return output


def _handle_slideshow(step: Mapping[str, Any], context: PipelineContext, default_preset: str | None) -> Path:
    photos = _collect_photos(step, context)
    audio = _resolve_path(step["audio"], context)
    output = _resolve_path(step["output"], context)
    _ensure_parent(output)

    preset_name = step.get("preset") or default_preset
    _, _, fps, video_bitrate, audio_bitrate = _with_preset_defaults(step, preset_name)

    stills.slideshow_with_audio(
        photo_paths=photos,
        audio_path=audio,
        output_path=output,
        fps=fps or 30,
        bitrate=video_bitrate or "4M",
        audio_bitrate=audio_bitrate or "192k",
    )
    return output


def _handle_concat(step: Mapping[str, Any], context: PipelineContext, default_preset: str | None) -> Path:
    inputs = [_resolve_path(path, context) for path in step["inputs"]]
    output = _resolve_path(step["output"], context)
    _ensure_parent(output)
    video.concat_videos(
        inputs=inputs,
        output=output,
        force_reencode=step.get("force_reencode", False),
        fps=step.get("fps"),
        width=step.get("width"),
        height=step.get("height"),
    )
    return output


def _handle_slowmo(step: Mapping[str, Any], context: PipelineContext, default_preset: str | None) -> Path:
    inputs = [_resolve_path(path, context) for path in step["inputs"]]
    output = _resolve_path(step["output"], context)
    _ensure_parent(output)
    video.slowmotion_montage(
        video_paths=inputs,
        output_path=output,
        slow_factor=float(step.get("slow_factor", 0.4)),
        fps=step.get("fps"),
    )
    return output


def _handle_stretch(step: Mapping[str, Any], context: PipelineContext, default_preset: str | None) -> Path:
    video_path = _resolve_path(step["video"], context)
    audio = _resolve_path(step["audio"], context)
    output = _resolve_path(step["output"], context)
    _ensure_parent(output)
    video.stretch_video_to_audio(
        video_path=video_path,
        audio_path=audio,
        output_path=output,
        max_fps=step.get("max_fps"),
    )
    return output


def _handle_fill(step: Mapping[str, Any], context: PipelineContext, default_preset: str | None) -> Path:
    video_path = _resolve_path(step["video"], context)
    output = _resolve_path(step["output"], context)
    _ensure_parent(output)

    preset_name = step.get("preset") or default_preset
    width, height, _, _, _ = _with_preset_defaults(step, preset_name)
    video.fill_frame(
        video_path=video_path,
        output_path=output,
        target_resolution=(width or 1920, height or 1080),
        audio_codec=step.get("audio_codec", "copy"),
        video_codec=step.get("video_codec", "libx264"),
        crf=step.get("crf", 18),
        preset=step.get("preset_name", "medium"),
    )
    return output


def _handle_zoom(step: Mapping[str, Any], context: PipelineContext, default_preset: str | None) -> Path:
    video_path = _resolve_path(step["video"], context)
    output = _resolve_path(step["output"], context)
    _ensure_parent(output)
    video.zoom_time_range_ffmpeg(
        video_path=video_path,
        output_path=output,
        zoom_start=float(step["start"]),
        zoom_end=float(step["end"]),
        zoom_factor=float(step.get("factor", 1.2)),
    )
    return output


def _handle_metadata(step: Mapping[str, Any], context: PipelineContext, default_preset: str | None) -> Path:
    output = _resolve_path(step.get("output") or "metadata.json", context)
    _ensure_parent(output)
    raw_chapters = step.get("chapters") or []
    chapters: list[tuple[str, str]] = []
    if isinstance(raw_chapters, Mapping):
        raw_iterable: Iterable[tuple[Any, Any]] = raw_chapters.items()
    elif isinstance(raw_chapters, str):
        raw_iterable = [raw_chapters]
    else:
        raw_iterable = raw_chapters  # type: ignore[assignment]

    for chapter in raw_iterable:
        if isinstance(chapter, Mapping):
            chapters.append((str(chapter["stamp"]), str(chapter["title"])) )
        else:
            stamp, _, title = str(chapter).partition("=")
            chapters.append((stamp.strip(), title.strip() or stamp.strip()))
    metadata = youtube_automation.generate_metadata(
        title_base=step["title_base"],
        topic=step.get("topic", context.variables.get("topic", "")),
        keywords=step.get("keywords"),
        language=step.get("language", "en"),
        call_to_action=step.get("cta"),
        hashtags=step.get("hashtags"),
        chapters=chapters,
        made_for_kids=bool(step.get("made_for_kids", False)),
        category_id=step.get("category_id", "22"),
    )
    youtube_automation.write_metadata(metadata, output)
    return output


def _handle_package(step: Mapping[str, Any], context: PipelineContext, default_preset: str | None) -> Path:
    video_path = _resolve_path(step["video"], context)
    metadata_path = _resolve_path(step["metadata"], context)
    destination = _resolve_path(step["destination"], context)
    thumbnail = step.get("thumbnail")
    package_dir = youtube_automation.prepare_upload_package(
        video_path=video_path,
        metadata=youtube_automation.load_metadata(metadata_path),
        destination=destination,
        thumbnail_path=_resolve_path(thumbnail, context) if thumbnail else None,
    )
    return package_dir


def _handle_upload(step: Mapping[str, Any], context: PipelineContext, default_preset: str | None) -> str:
    video_id = youtube_automation.upload_video(
        video_path=_resolve_path(step["video"], context),
        metadata=youtube_automation.load_metadata(_resolve_path(step["metadata"], context)),
        client_secrets=_resolve_path(step["client_secrets"], context),
        token_path=_resolve_path(step.get("token", "token.json"), context),
        thumbnail_path=_resolve_path(step["thumbnail"], context) if step.get("thumbnail") else None,
        privacy_status=step.get("privacy", "private"),
    )
    return video_id


_STEP_HANDLERS: Dict[str, StepHandler] = {
    "still": _handle_still,
    "slideshow": _handle_slideshow,
    "concat": _handle_concat,
    "slowmo": _handle_slowmo,
    "stretch": _handle_stretch,
    "fill-frame": _handle_fill,
    "zoom-range": _handle_zoom,
    "metadata": _handle_metadata,
    "yt-package": _handle_package,
    "yt-upload": _handle_upload,
}
