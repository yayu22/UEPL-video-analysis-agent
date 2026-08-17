"""
URL ingestion — download a remote video to a TEMP file for analysis.

Used by the /api/analyze-url path (Vercel / blob deployments): the browser uploads
the clip to blob storage, sends us only the URL, and we stream it to a temp file,
analyse it, then delete it. Nothing is persisted.

Robust like the AFDD download helper: size cap + a magic-bytes check so an XML/HTML
error page (a common signed-URL failure) is never mistaken for a video.
"""

from __future__ import annotations

import os
import tempfile
import logging
from urllib.parse import urlparse

import requests

log = logging.getLogger("uepl.ingest")


class DownloadError(Exception):
    """Raised when a video URL cannot be fetched into a valid temp file."""


_MIME_BY_EXT = {
    ".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm",
    ".avi": "video/x-msvideo", ".mkv": "video/x-matroska", ".mpeg": "video/mpeg",
    ".mpg": "video/mpeg", ".3gp": "video/3gpp", ".flv": "video/x-flv",
    ".wmv": "video/x-ms-wmv",
}


def _ext(url: str) -> str:
    return os.path.splitext(urlparse(url).path)[1].lower()


def guess_mime(url: str) -> str:
    return _MIME_BY_EXT.get(_ext(url), "video/mp4")


def basename(url: str) -> str:
    return os.path.basename(urlparse(url).path) or "video"


def download_to_temp(url: str, max_bytes: int) -> str:
    """Stream `url` to a temp file and return its path. Raises DownloadError.

    The caller is responsible for os.unlink()-ing the returned path (the API layer
    does this in a finally, so the file is never kept).
    """
    try:
        r = requests.get(url, stream=True, timeout=30)
    except Exception as e:  # noqa: BLE001
        raise DownloadError(f"could not fetch video URL: {e}")
    if r.status_code != 200:
        raise DownloadError(f"video URL returned HTTP {r.status_code}")

    fd, tmp = tempfile.mkstemp(suffix=_ext(url) or ".mp4")
    size = 0
    try:
        with os.fdopen(fd, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if not chunk:
                    continue
                size += len(chunk)
                if size > max_bytes:
                    raise DownloadError(f"video exceeds max size ({max_bytes} bytes)")
                f.write(chunk)
        if size < 1024:
            raise DownloadError("downloaded file is empty or corrupt")
        with open(tmp, "rb") as f:
            head = f.read(64).lower()
        if head[:5] == b"<?xml" or b"<html" in head or b"<error" in head:
            raise DownloadError("URL returned an error page, not a video")
        log.info("Downloaded %.1f MB from %s", size / 1e6, basename(url))
        return tmp
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
