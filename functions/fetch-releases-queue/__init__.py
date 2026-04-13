import json
import logging
import mimetypes
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from os import environ
from os.path import basename, splitext
from typing import List, Optional
from urllib import request
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

import azure.functions as func
from azure.core.exceptions import ResourceExistsError
from azure.storage.blob import BlobServiceClient, ContentSettings

# ---- Configuration -------------------------------------------------------

REPOS = [
    {"user_name": "Bible-Translation-Tools", "repo_name": "Orature"},
    {"user_name": "Bible-Translation-Tools", "repo_name": "BTT-Writer-Android"},
    {"user_name": "Bible-Translation-Tools", "repo_name": "BTT-Writer-Desktop"},
    {"user_name": "Bible-Translation-Tools", "repo_name": "BTT-Exchanger"},
    {"user_name": "Bible-Translation-Tools", "repo_name": "USFM-Converter"},
]

CONTAINER_NAME = "releases"
APP_DATA_BLOB = "app_data.json"
CONNECTION_STRING = environ["AZURE_STORAGE_CONNECTION_STRING"]
GITHUB_TOKEN = environ.get("GITHUB_TOKEN", "")

HTTP_TIMEOUT = 30  # seconds
ASSET_EXTENSION_RE = re.compile(r"\.(dmg|exe|deb|zip|AppImage|apk|jar)$", re.IGNORECASE)

blob_service_client = BlobServiceClient.from_connection_string(CONNECTION_STRING)


# ---- Entry point ---------------------------------------------------------

def main(msg: func.QueueMessage) -> None:
    """Main script to run the function."""
    logging.info(
        "Python queue trigger function processed a queue item: %s",
        msg.get_body().decode("utf-8"),
    )

    ensure_container()
    app_data, etag = get_local_app_data()

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {
            pool.submit(_process_repo, repo, app_data): repo["repo_name"]
            for repo in REPOS
        }
        for future in as_completed(futures):
            repo_name = futures[future]
            try:
                new_entries = future.result()
            except Exception:
                logging.exception("Failed to process %s", repo_name)
                continue

            if new_entries is None:
                continue

            app_data = remove_old_app(app_data, repo_name, delete_blobs=True)
            app_data.extend(new_entries)

    upload_app_data(app_data, etag)


def _log(msg: str, *args, level: str = "info") -> None:
    """Log via both logging and print so thread output is visible."""
    formatted = msg % args if args else msg
    getattr(logging, level)(formatted)
    print(f"[{level.upper()}] {formatted}", flush=True)


def _process_repo(repo: dict, app_data: list) -> Optional[list]:
    """Fetch latest release for a repo and upload its assets. Returns new entries or None."""
    repo_name = repo["repo_name"]
    url = f"https://api.github.com/repos/{repo['user_name']}/{repo_name}/releases/latest"

    _log("Fetching release info for %s", repo_name)
    release = github_get_json(url)

    app_name = get_common_app_name(repo_name)
    app_version: str | None = release.get("tag_name")
    if not app_version:
        _log("No tag_name on latest release for %s; skipping", repo_name, level="warning")
        return None

    _log("Found %s %s with %d assets", repo_name, app_version, len(release.get("assets", [])))

    if app_exists(app_data, repo_name, app_version):
        _log("%s %s already tracked; skipping", repo_name, app_version)
        return None

    entries = []
    for asset in release.get("assets", []):
        download_url = asset.get("browser_download_url", "")
        if not ASSET_EXTENSION_RE.search(download_url):
            continue

        _log("Downloading: %s", download_url)
        path = urlparse(download_url).path
        file_name = basename(path)

        blob_url = upload_file(download_url, file_name)
        if blob_url is None:
            _log("Skipping %s due to upload failure", file_name, level="warning")
            continue

        entries.append({
            "name": app_name,
            "repo_name": repo_name,
            "version": app_version,
            "size": asset.get("size"),
            "date": asset.get("updated_at"),
            "os": get_os_from_path(path),
            "url": blob_url,
        })

    return entries


# ---- GitHub --------------------------------------------------------------

def _build_github_request(url: str) -> request.Request:
    req = request.Request(url)
    req.add_header("User-Agent", "basic-tools-site")
    req.add_header("Accept", "application/vnd.github+json")
    if GITHUB_TOKEN:
        req.add_header("Authorization", f"token {GITHUB_TOKEN}")
    return req


def github_get_json(url: str, retries: int = 2) -> dict:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = _build_github_request(url)
            with request.urlopen(req, timeout=HTTP_TIMEOUT) as response:
                remaining = response.headers.get("X-RateLimit-Remaining")
                if remaining is not None and remaining.isdigit() and int(remaining) < 10:
                    logging.warning("GitHub rate limit low: %s remaining", remaining)
                return json.loads(response.read())
        except HTTPError as e:
            last_error = e
            if e.code < 500 or attempt == retries:
                raise
            logging.warning("GitHub API returned %s, retrying (%s/%s)", e.code, attempt + 1, retries)
        except URLError as e:
            last_error = e
            if attempt == retries:
                raise
            logging.warning("Network error fetching %s, retrying (%s/%s)", url, attempt + 1, retries)
    raise last_error  # type: ignore[misc]


# ---- OS detection --------------------------------------------------------

def get_os_from_path(path: str) -> str:
    file_name = basename(path)
    extension = splitext(path)[1]
    os_name = get_os_from_filename(file_name)
    if os_name == "Unknown":
        os_name = get_os_from_extension(extension)
    return os_name


def get_os_from_filename(file_name: str) -> str:
    if re.search(r"(osx|macos)", file_name, flags=re.I):
        return "Osx"
    if re.search(r"(windows|win)", file_name, flags=re.I):
        if re.search(r"(x|win)64|64[\s._-]?bit", file_name, flags=re.I):
            return "Windows64"
        if re.search(r"(x|win)32|32[\s._-]?bit", file_name, flags=re.I):
            return "Windows32"
        return "Windows"
    if re.search(r"linux", file_name, flags=re.I):
        return "Linux"
    if re.search(r"android", file_name, flags=re.I):
        return "Android"
    return "Unknown"


def get_os_from_extension(ext: str) -> str:
    mapping = {
        ".exe": "Windows",
        ".dmg": "Osx",
        ".appimage": "Linux",
        ".deb": "Linux",
        ".apk": "Android",
        ".zip": "Zip",
    }
    return mapping.get(ext.lower(), "Unknown")


# ---- Blob storage --------------------------------------------------------

def ensure_container() -> None:
    try:
        blob_service_client.create_container(CONTAINER_NAME)
        logging.info("Created container %s", CONTAINER_NAME)
    except ResourceExistsError:
        pass
    except Exception:
        logging.exception("Failed to ensure container %s", CONTAINER_NAME)


def _content_settings_for(file_name: str) -> ContentSettings:
    ctype, _ = mimetypes.guess_type(file_name)
    if not ctype:
        ctype = "application/octet-stream"
    # Force download rather than inline rendering.
    return ContentSettings(
        content_type=ctype,
        content_disposition=f'attachment; filename="{file_name}"',
    )


def upload_file(url: str, file_name: str) -> Optional[str]:
    """Stream a remote file into blob storage without loading it fully into memory."""
    try:
        blob_client = blob_service_client.get_blob_client(
            container=CONTAINER_NAME, blob=file_name
        )
        req = _build_github_request(url)
        with request.urlopen(req, timeout=HTTP_TIMEOUT) as response:
            length = response.headers.get("Content-Length")
            blob_client.upload_blob(
                response,
                length=int(length) if length else None,
                overwrite=True,
                content_settings=_content_settings_for(file_name),
            )
        return blob_client.url
    except (HTTPError, URLError):
        logging.exception("Network error downloading %s", url)
    except Exception:
        logging.exception("Failed to upload %s", file_name)
    return None


def upload_app_data(app_data: List, etag: Optional[str]) -> None:
    """Upload app_data.json; uses an ETag If-Match when available to avoid clobbering
    a concurrent writer."""
    try:
        blob_client = blob_service_client.get_blob_client(
            container=CONTAINER_NAME, blob=APP_DATA_BLOB
        )
        json_data = json.dumps(app_data, indent=4, ensure_ascii=False).encode("utf-8")
        kwargs = {
            "overwrite": True,
            "content_settings": ContentSettings(content_type="application/json"),
        }
        if etag:
            kwargs["if_match"] = etag
        blob_client.upload_blob(json_data, **kwargs)
    except Exception:
        logging.exception("Failed to upload %s", APP_DATA_BLOB)


def get_local_app_data() -> tuple:
    """Read app_data.json plus its ETag (for optimistic concurrency)."""
    try:
        blob_client = blob_service_client.get_blob_client(
            container=CONTAINER_NAME, blob=APP_DATA_BLOB
        )
        downloader = blob_client.download_blob()
        data = json.loads(downloader.readall())
        etag = downloader.properties.etag
        return data, etag
    except Exception:
        logging.info("%s not found or unreadable; starting fresh", APP_DATA_BLOB)
        return [], None


def _delete_blob_quietly(blob_name: str) -> None:
    try:
        blob_service_client.get_blob_client(
            container=CONTAINER_NAME, blob=blob_name
        ).delete_blob()
        logging.info("Deleted old blob %s", blob_name)
    except Exception:
        logging.exception("Failed to delete blob %s", blob_name)


# ---- App-data helpers ----------------------------------------------------

def get_common_app_name(name: str) -> str:
    if name in ("BTT-Writer-Android", "BTT-Writer-Desktop"):
        return "BTT-Writer"
    return name


def app_exists(app_data: list, repo_name: str, version: str) -> bool:
    return any(
        app.get("repo_name") == repo_name and app.get("version") == version
        for app in app_data
    )


def remove_old_app(app_data: list, repo_name: str, delete_blobs: bool = False) -> list:
    """Remove entries for repo_name; optionally delete their backing blobs too."""
    kept, removed = [], []
    for app in app_data:
        if app.get("repo_name") == repo_name:
            removed.append(app)
        else:
            kept.append(app)

    if delete_blobs:
        for app in removed:
            blob_url = app.get("url")
            if not blob_url:
                continue
            blob_name = basename(urlparse(blob_url).path)
            if blob_name:
                _delete_blob_quietly(blob_name)

    return kept