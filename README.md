# audio-photo-combiner / media_editor

`media_editor` is a reusable toolkit that wraps the one-off scripts in this repository into a cohesive library and CLI for:

- Combining still images, slideshows, and audio tracks
- Batch video editing (concat, slow motion, stretch-to-audio, zoom, fill-frame)
- Preset-driven renders (widescreen, Shorts, square) for repeatable outputs
- Declarative pipelines that stitch multi-step workflows from JSON/YAML files
- Preparing YouTube-ready metadata packages
- Optional direct uploads through the YouTube Data API

## Installation

```powershell
# Activate your virtualenv first
pip install -r requirements.txt  # if you create one, otherwise install moviepy imageio-ffmpeg
pip install google-api-python-client google-auth google-auth-oauthlib  # optional for yt-upload
# Pipeline configs accept YAML too once PyYAML is installed
pip install pyyaml  # optional for media_editor.pipeline
```

Because everything lives in this repo, you can also install the package in editable mode:

```powershell
pip install -e .
```

## Library layout

| Module | Highlights |
| --- | --- |
| `media_editor.stills` | `still_with_audio`, `slideshow_with_audio` wrappers with FFmpeg-first execution |
| `media_editor.video` | `concat_videos`, `slowmotion_montage`, `stretch_video_to_audio`, `fill_frame`, `zoom_section_moviepy`, `zoom_time_range_ffmpeg` |
| `media_editor.templates` | Named presets (widescreen, shorts, square). Helpers: `render_still_from_preset`, `render_slideshow_from_preset`, `fill_video_with_preset`, `describe_preset` |
| `media_editor.pipeline` | Config-driven automation runner for chaining still/video presets, metadata generation, packaging, and uploads |
| `media_editor.youtube_automation` | Metadata dataclass/helpers, package builder, YouTube Data API uploader with friendly dependency guidance |
| `media_editor.ffmpeg_utils` | Shared FFmpeg path/concat helpers |

Callers can mix and match these primitives to assemble new workflows programmatically.

## CLI usage

Once the workspace venv knows about the package (`pip install -e .`), run the CLI via `python -m media_editor` or the module entry point `media-editor` if you add a console script.

Examples:

```powershell
# Turn a still photo into a video with audio (explicit dimensions)
python -m media_editor still --image cover.png --audio narration.m4a --output intro.mp4 --width 1920 --height 1080

# ...or rely on presets (Shorts vertical video)
python -m media_editor still --image cover.png --audio narration.m4a --output intro_shorts.mp4 --preset shorts_vertical --copy-audio

# Build a slideshow where each image gets an equal slice of the audio
python -m media_editor slideshow --photos img1.png img2.png img3.png --audio podcast.m4a --output slideshow.mp4

# Concatenate clips (lossless when possible)
python -m media_editor concat --inputs part1.mp4 part2.mp4 part3.mp4 --output full.mp4

# Zoom a time range without touching the rest of the video
python -m media_editor zoom-range --video source.mp4 --output punch_in.mp4 --start 12.5 --end 22.0 --factor 1.3

# Generate metadata + package for YouTube
python -m media_editor yt-metadata --title-base "AI News" --topic "Weekly Highlights" --keywords ai news --hashtags shorts --output metadata.json
python -m media_editor yt-package --video punch_in.mp4 --metadata metadata.json --thumbnail thumb.png --destination dist

# Upload (requires OAuth client secrets)
python -m media_editor yt-upload --video punch_in.mp4 --metadata metadata.json --client-secrets client_secret.json --thumbnail thumb.png --privacy unlisted

# Run a whole pipeline config (JSON/YAML)
python -m media_editor pipeline --config workflows/shorts.json --var topic="AI News" --var cta="Join the newsletter"
```

Subcommands currently available:

| Command | Description |
| --- | --- |
| `still` | Loop a still image while playing audio (FFmpeg-first, MoviePy fallback) |
| `slideshow` | Build a slideshow split evenly across the audio duration |
| `concat` | Lossless concat by default, optional re-encode for mismatched sources |
| `slowmo` | Slow down a batch of clips and concatenate |
| `stretch` | Stretch video to match audio duration without re-cutting |
| `fill-frame` | Fill a target resolution without pillarboxing via FFmpeg (`--preset` friendly) |
| `zoom-range` | Punch in on a precise time range using segment re-encoding |
| `yt-metadata` | Create JSON metadata (title, description, tags, chapters) |
| `yt-package` | Copy video + metadata + thumbnail into a ready folder |
| `yt-upload` | Upload through the YouTube Data API (optional dependency) |
| `preset-list` | Inspect every built-in preset and the associated render specs |
| `pipeline` | Execute a declarative workflow (JSON or YAML) with optional `--var KEY=VALUE` overrides |

## Pipeline automation

Pipelines let you describe series of steps (stills, slideshows, concat, metadata, packaging, uploads) in one file. Example:

```jsonc
{
	"preset": "shorts_vertical",
	"variables": {
		"topic": "Daily Motivation"
	},
	"steps": [
		{
			"type": "still",
			"name": "intro",
			"image": "assets/cover.png",
			"audio": "audio/intro.wav",
			"output": "build/intro.mp4"
		},
		{
			"type": "slideshow",
			"name": "slideshow",
			"photos_glob": "assets/slides/*.png",
			"audio": "audio/main.wav",
			"output": "build/slideshow.mp4"
		},
		{
			"type": "concat",
			"inputs": ["@intro", "@slideshow"],
			"output": "build/final.mp4"
		},
		{
			"type": "metadata",
			"title_base": "Motivation",
			"topic": "{topic}",
			"chapters": ["00:00=Intro", "00:30=Highlights"],
			"output": "build/metadata.json"
		},
		{
			"type": "yt-package",
			"video": "@concat",
			"metadata": "@metadata",
			"thumbnail": "assets/thumb.png",
			"destination": "dist"
		}
	]
}
```

Run it via `python -m media_editor pipeline --config workflows/motivation.json`. Pipelines can interpolate `{variables}` and reuse artifacts via the `@name` syntax.

## YouTube automation flow

1. Run `yt-metadata` to generate a JSON payload with title, description, tags, CTA, and optional chapter markers (or let a pipeline step do it for you).
2. Optionally call `yt-package` to gather the rendered video, thumbnail, and metadata into `dist/upload_YYYYMMDD-HHMMSS`.
3. Provide a Google OAuth client secrets JSON (desktop type) and run `yt-upload`. The command stores/refreshes OAuth tokens (`token.json`) and supports thumbnail assignment + privacy flags.

Because each step is idempotent, you can integrate these commands into schedulers (Task Scheduler, GitHub Actions, etc.) for fully automated pipelines.

## Next steps / contributions

- Add watch-folder automation + scheduling helpers.
- Wire up a console script entry in `pyproject.toml` for nicer command names.
- Create automated tests with sample assets/pipeline fixtures.

PRs and workflow ideas welcome!
