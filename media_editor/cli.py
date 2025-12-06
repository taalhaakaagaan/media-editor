from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from . import pipeline, stills, templates, video, youtube_automation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="media-editor", description="Media toolkit + YouTube automation helpers")
    subparsers = parser.add_subparsers(dest="command", required=True)

    still_cmd = subparsers.add_parser("still", help="Attach audio to a still image")
    still_cmd.add_argument("--image", required=True)
    still_cmd.add_argument("--audio", required=True)
    still_cmd.add_argument("--output", required=True)
    still_cmd.add_argument("--fps", type=int, default=30)
    still_cmd.add_argument("--bitrate", default="4M")
    still_cmd.add_argument("--audio-bitrate", default="192k")
    still_cmd.add_argument("--width", type=int)
    still_cmd.add_argument("--height", type=int)
    still_cmd.add_argument("--preset", help="Shortcut for width/height/fps/bitrates")
    still_cmd.add_argument("--copy-audio", action="store_true", default=False)
    still_cmd.set_defaults(func=_handle_still)

    slideshow = subparsers.add_parser("slideshow", help="Spread photos evenly across the audio track")
    slideshow.add_argument("--photos", nargs="+", required=True)
    slideshow.add_argument("--audio", required=True)
    slideshow.add_argument("--output", required=True)
    slideshow.add_argument("--fps", type=int, default=30)
    slideshow.add_argument("--bitrate", default="4M")
    slideshow.add_argument("--audio-bitrate", default="192k")
    slideshow.add_argument("--preset", help="Use a named render preset")
    slideshow.set_defaults(func=_handle_slideshow)

    concat = subparsers.add_parser("concat", help="Concatenate multiple videos")
    concat.add_argument("--inputs", nargs="+", required=True)
    concat.add_argument("--output", required=True)
    concat.add_argument("--force-reencode", action="store_true")
    concat.add_argument("--fps", type=float)
    concat.add_argument("--width", type=int)
    concat.add_argument("--height", type=int)
    concat.set_defaults(func=_handle_concat)

    slowmo = subparsers.add_parser("slowmo", help="Build a slow-motion montage")
    slowmo.add_argument("--inputs", nargs="+", required=True)
    slowmo.add_argument("--output", required=True)
    slowmo.add_argument("--slow-factor", type=float, default=0.4)
    slowmo.add_argument("--fps", type=float)
    slowmo.set_defaults(func=_handle_slowmo)

    stretch = subparsers.add_parser("stretch", help="Stretch video duration to match audio")
    stretch.add_argument("--video", required=True)
    stretch.add_argument("--audio", required=True)
    stretch.add_argument("--output", required=True)
    stretch.add_argument("--max-fps", type=float)
    stretch.set_defaults(func=_handle_stretch)

    fill = subparsers.add_parser("fill-frame", help="Fill the frame without black bars")
    fill.add_argument("--video", required=True)
    fill.add_argument("--output", required=True)
    fill.add_argument("--width", type=int, default=1920)
    fill.add_argument("--height", type=int, default=1080)
    fill.add_argument("--preset", help="Apply preset aspect + bitrate choices")
    fill.set_defaults(func=_handle_fill_frame)

    zoom = subparsers.add_parser("zoom-range", help="Zoom a specific time range via FFmpeg")
    zoom.add_argument("--video", required=True)
    zoom.add_argument("--output", required=True)
    zoom.add_argument("--start", type=float, required=True)
    zoom.add_argument("--end", type=float, required=True)
    zoom.add_argument("--factor", type=float, default=1.2)
    zoom.set_defaults(func=_handle_zoom_range)

    meta = subparsers.add_parser("yt-metadata", help="Generate metadata JSON for YouTube uploads")
    meta.add_argument("--title-base", required=True)
    meta.add_argument("--topic", required=True)
    meta.add_argument("--keywords", nargs="*", default=[])
    meta.add_argument("--hashtags", nargs="*", default=[])
    meta.add_argument("--language", default="en")
    meta.add_argument("--cta", default=None)
    meta.add_argument("--chapter", action="append", default=[], help="Add as HH:MM=Title")
    meta.add_argument("--output", required=True)
    meta.set_defaults(func=_handle_metadata)

    package = subparsers.add_parser("yt-package", help="Bundle video + metadata + thumbnail for uploads")
    package.add_argument("--video", required=True)
    package.add_argument("--metadata", required=True, help="Path to metadata JSON")
    package.add_argument("--destination", required=True)
    package.add_argument("--thumbnail")
    package.set_defaults(func=_handle_package)

    upload = subparsers.add_parser("yt-upload", help="Upload using the YouTube Data API")
    upload.add_argument("--video", required=True)
    upload.add_argument("--metadata", required=True, help="Path to metadata JSON")
    upload.add_argument("--client-secrets", required=True)
    upload.add_argument("--token", default="token.json")
    upload.add_argument("--thumbnail")
    upload.add_argument("--privacy", default="private")
    upload.set_defaults(func=_handle_upload)

    preset_list = subparsers.add_parser("preset-list", help="List built-in frame presets")
    preset_list.set_defaults(func=_handle_preset_list)

    pipeline_cmd = subparsers.add_parser("pipeline", help="Execute a declarative pipeline config")
    pipeline_cmd.add_argument("--config", required=True, help="Path to JSON/YAML pipeline file")
    pipeline_cmd.add_argument(
        "--var",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Override/define pipeline variables",
    )
    pipeline_cmd.add_argument("--base-dir", help="Override base directory for relative paths")
    pipeline_cmd.set_defaults(func=_handle_pipeline)

    return parser


def _handle_still(args: argparse.Namespace) -> None:
    if args.preset:
        templates.render_still_from_preset(
            preset_name=args.preset,
            image_path=args.image,
            audio_path=args.audio,
            output_path=args.output,
            copy_audio=args.copy_audio,
        )
        return

    stills.still_with_audio(
        image_path=args.image,
        audio_path=args.audio,
        output_path=args.output,
        fps=args.fps,
        bitrate=args.bitrate,
        audio_bitrate=args.audio_bitrate,
        width=args.width,
        height=args.height,
        copy_audio=args.copy_audio,
    )


def _handle_slideshow(args: argparse.Namespace) -> None:
    if args.preset:
        templates.render_slideshow_from_preset(
            preset_name=args.preset,
            photos=args.photos,
            audio_path=args.audio,
            output_path=args.output,
        )
        return

    stills.slideshow_with_audio(
        photo_paths=args.photos,
        audio_path=args.audio,
        output_path=args.output,
        fps=args.fps,
        bitrate=args.bitrate,
        audio_bitrate=args.audio_bitrate,
    )


def _handle_concat(args: argparse.Namespace) -> None:
    video.concat_videos(
        inputs=args.inputs,
        output=args.output,
        force_reencode=args.force_reencode,
        fps=args.fps,
        width=args.width,
        height=args.height,
    )


def _handle_slowmo(args: argparse.Namespace) -> None:
    video.slowmotion_montage(
        video_paths=args.inputs,
        output_path=args.output,
        slow_factor=args.slow_factor,
        fps=args.fps,
    )


def _handle_stretch(args: argparse.Namespace) -> None:
    video.stretch_video_to_audio(
        video_path=args.video,
        audio_path=args.audio,
        output_path=args.output,
        max_fps=args.max_fps,
    )


def _handle_fill_frame(args: argparse.Namespace) -> None:
    if args.preset:
        templates.fill_video_with_preset(
            preset_name=args.preset,
            video_path=args.video,
            output_path=args.output,
        )
        return

    video.fill_frame(
        video_path=args.video,
        output_path=args.output,
        target_resolution=(args.width, args.height),
    )


def _handle_zoom_range(args: argparse.Namespace) -> None:
    video.zoom_time_range_ffmpeg(
        video_path=args.video,
        output_path=args.output,
        zoom_start=args.start,
        zoom_end=args.end,
        zoom_factor=args.factor,
    )


def _parse_chapters(chapter_args: Sequence[str]) -> list[tuple[str, str]]:
    chapters: list[tuple[str, str]] = []
    for entry in chapter_args:
        if "=" not in entry:
            raise ValueError("Chapters must be formatted as HH:MM=Label")
        stamp, label = entry.split("=", 1)
        chapters.append((stamp.strip(), label.strip()))
    return chapters


def _handle_metadata(args: argparse.Namespace) -> None:
    chapters = _parse_chapters(args.chapter)
    metadata = youtube_automation.generate_metadata(
        title_base=args.title_base,
        topic=args.topic,
        keywords=args.keywords,
        hashtags=args.hashtags,
        language=args.language,
        call_to_action=args.cta,
        chapters=chapters,
    )
    path = youtube_automation.write_metadata(metadata, args.output)
    print(f"Metadata written to {path}")


def _handle_package(args: argparse.Namespace) -> None:
    metadata = youtube_automation.load_metadata(Path(args.metadata))
    package_dir = youtube_automation.prepare_upload_package(
        video_path=args.video,
        metadata=metadata,
        destination=args.destination,
        thumbnail_path=args.thumbnail,
    )
    print(f"Package ready at {package_dir}")


def _handle_upload(args: argparse.Namespace) -> None:
    metadata = youtube_automation.load_metadata(Path(args.metadata))
    video_id = youtube_automation.upload_video(
        video_path=args.video,
        metadata=metadata,
        client_secrets=args.client_secrets,
        token_path=args.token,
        thumbnail_path=args.thumbnail,
        privacy_status=args.privacy,
    )
    print(f"Uploaded video id: {video_id}")


def _handle_preset_list(args: argparse.Namespace) -> None:  # pragma: no cover - passthrough IO
    for preset in templates.list_presets():
        print(templates.describe_preset(preset.name))


def _parse_assignments(pairs: Sequence[str]) -> dict[str, str]:
    assignments: dict[str, str] = {}
    for entry in pairs:
        if "=" not in entry:
            raise ValueError("Variables must be formatted as KEY=VALUE")
        key, value = entry.split("=", 1)
        assignments[key.strip()] = value.strip()
    return assignments


def _handle_pipeline(args: argparse.Namespace) -> None:
    variables = _parse_assignments(args.var)
    base_dir = Path(args.base_dir).resolve() if args.base_dir else None
    artifacts = pipeline.run_pipeline(
        config=Path(args.config),
        variables=variables,
        base_dir=base_dir,
    )
    printable = {key: str(value) for key, value in artifacts.items()}
    print(json.dumps(printable, indent=2))


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except Exception as exc:  # pragma: no cover - CLI guardrail
        parser.exit(1, f"Error: {exc}\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    main()
