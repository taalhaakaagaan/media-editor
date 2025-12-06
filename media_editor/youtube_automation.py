from __future__ import annotations

import json
import mimetypes
import shutil
import importlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence, Union

PathLike = Union[str, Path]
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
OPTIONAL_UPLOAD_PACKAGES = (
    "google-api-python-client",
    "google-auth",
    "google-auth-oauthlib",
)
ProgressCallback = Callable[[int], None]


@dataclass
class Metadata:
    title: str
    description: str
    tags: list[str]
    language: str = "en"
    category_id: str = "22"  # People & Blogs
    made_for_kids: bool = False
    license: str = "youtube"

    def as_payload(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "description": self.description,
            "tags": self.tags,
            "language": self.language,
            "categoryId": self.category_id,
            "made_for_kids": self.made_for_kids,
            "license": self.license,
        }


def generate_metadata(
    *,
    title_base: str,
    topic: str,
    keywords: Sequence[str] | None = None,
    language: str = "en",
    call_to_action: str | None = None,
    hashtags: Sequence[str] | None = None,
    description_template: str | None = None,
    chapters: Sequence[tuple[str, str]] | None = None,
    made_for_kids: bool = False,
    category_id: str = "22",
) -> Metadata:
    """Generate YouTube-friendly metadata with optional CTA and chapters."""

    keywords = [keyword.strip() for keyword in (keywords or []) if keyword.strip()]
    hashtags = [tag.lstrip("#").strip() for tag in (hashtags or []) if tag.strip()]

    title = f"{title_base} | {topic}" if topic else title_base
    if keywords:
        title = f"{title} ({keywords[0]})"

    if description_template is None:
        description_template = (
            "{topic}\n\n"
            "Chapters:\n{chapters}\n\n"
            "Stay updated: {cta}\n\n"
            "Hashtags: {hashtags}"
        )

    chapter_lines = []
    for stamp, label in chapters or []:
        chapter_lines.append(f"{stamp} - {label}")
    chapters_block = "\n".join(chapter_lines) if chapter_lines else "00:00 - Intro"

    cta_text = call_to_action or "Subscribe for more walkthroughs"
    hashtag_blob = " ".join(f"#{tag}" for tag in hashtags) if hashtags else ""

    description = description_template.format(
        topic=topic,
        chapters=chapters_block,
        cta=cta_text,
        hashtags=hashtag_blob or "#shorts",
    )

    tags = keywords + hashtags

    return Metadata(
        title=title.strip(),
        description=description.strip(),
        tags=tags,
        language=language,
        category_id=category_id,
        made_for_kids=made_for_kids,
    )


def write_metadata(metadata: Metadata, output_path: PathLike) -> Path:
    """Persist metadata to disk for later uploads."""

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(metadata.as_payload(), indent=2, ensure_ascii=False), encoding="utf-8")
    return output


def load_metadata(path: PathLike) -> Metadata:
    """Load metadata JSON created by :func:`write_metadata`."""

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Metadata file must contain an object: {path}")
    return metadata_from_dict(payload)


def prepare_upload_package(
    *,
    video_path: PathLike,
    metadata: Metadata,
    destination: PathLike,
    thumbnail_path: PathLike | None = None,
) -> Path:
    """Copy assets into a single directory ready for manual or automated upload."""

    video = Path(video_path)
    if not video.exists():
        raise FileNotFoundError(f"Video not found: {video}")

    dest_dir = Path(destination)
    dest_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    package_dir = dest_dir / f"upload_{timestamp}"
    package_dir.mkdir(parents=True, exist_ok=True)

    video_target = package_dir / video.name
    shutil.copy2(video, video_target)

    meta_target = package_dir / "metadata.json"
    write_metadata(metadata, meta_target)

    if thumbnail_path:
        thumb = Path(thumbnail_path)
        if not thumb.exists():
            raise FileNotFoundError(f"Thumbnail not found: {thumb}")
        shutil.copy2(thumb, package_dir / thumb.name)

    return package_dir


def metadata_from_dict(data: Mapping[str, Any]) -> Metadata:
    """Recreate a Metadata object from a JSON/dict payload."""

    return Metadata(
        title=data["title"],
        description=data["description"],
        tags=list(data.get("tags", [])),
        language=data.get("language", "en"),
        category_id=data.get("categoryId", data.get("category_id", "22")),
        made_for_kids=data.get("made_for_kids", False),
        license=data.get("license", "youtube"),
    )


def upload_video(
    *,
    video_path: PathLike,
    metadata: Mapping[str, Any] | Metadata,
    client_secrets: PathLike,
    token_path: PathLike | None = None,
    thumbnail_path: PathLike | None = None,
    privacy_status: str = "private",
    progress_callback: ProgressCallback | None = None,
) -> str:
    """Upload a video via the YouTube Data API.

    Requires ``google-api-python-client`` and ``google-auth-oauthlib``.
    """

    (
        Credentials,
        build,
        HttpError,
        MediaFileUpload,
        InstalledAppFlow,
        Request,
    ) = _import_google_clients()

    video_file = Path(video_path)
    if not video_file.exists():
        raise FileNotFoundError(f"Video not found: {video_file}")

    secrets_file = Path(client_secrets)
    if not secrets_file.exists():
        raise FileNotFoundError(f"Client secrets not found: {secrets_file}")

    creds: Any | None = None
    token_file = Path(token_path) if token_path else Path("token.json")
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(secrets_file), SCOPES)
            creds = flow.run_console()
        token_file.write_text(creds.to_json(), encoding="utf-8")

    youtube = build("youtube", "v3", credentials=creds)

    payload = metadata.as_payload() if isinstance(metadata, Metadata) else metadata
    snippet = {
        "title": payload.get("title"),
        "description": payload.get("description"),
        "tags": payload.get("tags"),
        "categoryId": payload.get("categoryId", "22"),
        "defaultLanguage": payload.get("language", "en"),
    }
    status = {
        "privacyStatus": privacy_status,
        "selfDeclaredMadeForKids": payload.get("made_for_kids", False),
        "license": payload.get("license", "youtube"),
    }

    media = MediaFileUpload(str(video_file), resumable=True)
    request = youtube.videos().insert(part="snippet,status", body={"snippet": snippet, "status": status}, media_body=media)

    response = None
    try:
        while response is None:
            status, response = request.next_chunk()
            if progress_callback and status:
                progress_callback(int(status.progress() * 100))
    except HttpError as exc:
        raise RuntimeError(f"YouTube upload failed: {exc}") from exc

    video_id = response["id"]

    if thumbnail_path:
        thumb_file = Path(thumbnail_path)
        if not thumb_file.exists():
            raise FileNotFoundError(f"Thumbnail not found: {thumb_file}")
        mime_type, _ = mimetypes.guess_type(str(thumb_file))
        MediaFileUploadThumb = MediaFileUpload  # alias for clarity
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUploadThumb(str(thumb_file), mimetype=mime_type or "image/jpeg"),
        ).execute()

    return video_id


def _import_google_clients():  # pragma: no cover - optional import helper
    try:
        Credentials = importlib.import_module("google.oauth2.credentials").Credentials
        build = importlib.import_module("googleapiclient.discovery").build
        HttpError = importlib.import_module("googleapiclient.errors").HttpError
        MediaFileUpload = importlib.import_module("googleapiclient.http").MediaFileUpload
        InstalledAppFlow = importlib.import_module("google_auth_oauthlib.flow").InstalledAppFlow
        Request = importlib.import_module("google.auth.transport.requests").Request
    except ModuleNotFoundError as exc:
        packages = " ".join(OPTIONAL_UPLOAD_PACKAGES)
        raise RuntimeError(
            "YouTube uploads require optional dependencies. Install them via:"
            f" pip install {packages}"
        ) from exc

    return Credentials, build, HttpError, MediaFileUpload, InstalledAppFlow, Request
