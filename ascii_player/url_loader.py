"""Universal URL resolver for ASCII Player (images, webpages, and YouTube)."""

from __future__ import annotations

import hashlib
import io
import ipaddress
import json
import os
import re
import socket
import tempfile
import urllib.request
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from PIL import Image

from .youtube import is_youtube_url

_USER_AGENT = "Mozilla/5.0 (compatible; ascii-player/1.0)"

# Shared safety limits for every network fetch performed by the player.
MAX_DOWNLOAD_BYTES = 32 * 1024 * 1024  # 32 MiB default budget per download
URL_CHUNK_SIZE = 64 * 1024
URL_TIMEOUT = 15

_YOUTUBE_ID_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?.*?v=|shorts/|embed/)|youtu\.be/)([A-Za-z0-9_-]{11})"
)
_META_OG_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_IMG_SRC_RE = re.compile(r'<img[^>]+(?:data-src|src)=["\']([^"\']+)["\']', re.IGNORECASE)


@dataclass
class ResolvedURL:
    """Result of resolving any URL into renderable ASCII media."""

    url: str
    kind: str  # "image" | "youtube" | "video"
    title: str
    image: Optional[Image.Image] = None
    frames: List[Tuple[Image.Image, float]] = field(default_factory=list)
    saved_path: Optional[str] = None
    is_playable_video: bool = False
    resolved_image_url: Optional[str] = None


def resolved_video_source(resolved: Optional[ResolvedURL]) -> Optional[str]:
    """Return a usable local video path from a resolved URL result, if any."""
    if resolved is None or resolved.kind != "video":
        return None
    path = resolved.saved_path
    return path if path and os.path.exists(path) else None


def normalize_url(url: str) -> str:
    """Strip whitespace and normalize bare www. URLs to https://."""
    cleaned = str(url or "").strip()
    if cleaned.lower().startswith("www."):
        cleaned = "https://" + cleaned
    return cleaned


def extract_youtube_id(url: str) -> Optional[str]:
    """Extract an 11-char YouTube video ID from common watch/short/share URLs."""
    match = _YOUTUBE_ID_RE.search(str(url or ""))
    return match.group(1) if match else None


def extract_webpage_image_url(html_text: str, base_url: str) -> Tuple[Optional[str], str]:
    """Extract the most representative image URL and title from an HTML document."""
    title = ""
    candidate: Optional[str] = None

    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html_text, "html.parser")
        if soup.title and soup.title.string:
            title = " ".join(soup.title.string.split())

        for attr, key in (
            ("property", "og:image"),
            ("property", "og:image:url"),
            ("name", "twitter:image"),
            ("name", "twitter:image:src"),
        ):
            tag = soup.find("meta", attrs={attr: re.compile(f"^{re.escape(key)}$", re.I)})
            if tag and tag.get("content"):
                candidate = str(tag["content"]).strip()
                break

        if not candidate:
            link_tag = soup.find("link", attrs={"rel": lambda v: v and "image_src" in v})
            if link_tag and link_tag.get("href"):
                candidate = str(link_tag["href"]).strip()

        if not candidate:
            for img in soup.find_all("img"):
                src = str(img.get("data-src") or img.get("src") or "").strip()
                if not src or src.startswith("data:"):
                    continue
                lower = src.lower()
                if lower.endswith(".svg") or "pixel" in lower or "spacer" in lower:
                    continue
                candidate = src
                break
    except Exception:
        title_match = _TITLE_RE.search(html_text)
        if title_match:
            title = " ".join(title_match.group(1).split())
        meta_match = _META_OG_RE.search(html_text)
        if meta_match:
            candidate = meta_match.group(1).strip()
        else:
            for img_match in _IMG_SRC_RE.finditer(html_text):
                src = img_match.group(1).strip()
                if src and not src.startswith("data:") and not src.lower().endswith(".svg"):
                    candidate = src
                    break

    resolved = urljoin(base_url, candidate) if candidate else None
    return resolved, title


def _ip_is_unsafe(value: Any) -> bool:
    """True for loopback/private/link-local/reserved/unspecified/mapped IPs."""
    try:
        ip = ipaddress.ip_address(str(value).split("%", 1)[0])
    except (ValueError, TypeError):
        return True
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        # e.g. ::ffff:127.0.0.1 must be judged by its mapped IPv4 address.
        ip = ip.ipv4_mapped
    return (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def is_safe_url(url: Any) -> bool:
    """Reject non-http(s) URLs and any host resolving to a non-public IP.

    Checks literal IPs, then every address returned by ``getaddrinfo``. This
    blocks SSRF targets such as 127.0.0.0/8, 169.254.169.254 (metadata),
    10/8, 172.16/12, 192.168/16, ::1 and IPv4-mapped IPv6 forms. DNS failure
    fails closed rather than letting urlopen decide.
    """
    try:
        text = str(url or "").strip()
        parsed = urlparse(text)
    except (ValueError, TypeError):
        return False

    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        return False  # file://, ftp://, data:, etc. are never allowed
    try:
        host = parsed.hostname
        port = parsed.port or (443 if scheme == "https" else 80)
    except ValueError:
        return False
    if not host:
        return False
    host = host.lower().rstrip(".")

    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass  # a hostname: rely on DNS resolution below
    else:
        if _ip_is_unsafe(host):
            return False

    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (OSError, ValueError):
        return False
    if not infos:
        return False
    for info in infos:
        try:
            address = info[4][0]
        except (IndexError, TypeError):
            return False
        if _ip_is_unsafe(address):
            return False
    return True


def _fetch_stream(
    url: str,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
    timeout: int = URL_TIMEOUT,
) -> Tuple[bytes, str, str]:
    """Fetch a URL into memory with scheme/IP checks and a hard byte budget."""
    if not is_safe_url(url):
        raise ValueError(
            f"Unsafe or invalid URL (only public http/https URLs are allowed): {url!r}"
        )
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1:
        raise ValueError(f"Invalid download size limit: {max_bytes!r}")

    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        try:
            final_url = str(getattr(response, "geturl", lambda: url)() or url)
        except Exception:
            final_url = url
        if final_url != url and not is_safe_url(final_url):
            raise ValueError(f"URL redirected to an unsafe address: {final_url!r}")

        headers = getattr(response, "headers", None)
        content_type = ""
        if headers is not None:
            content_type = str(headers.get("Content-Type", "")).split(";")[0].strip().lower()

        chunks: List[bytes] = []
        total = 0
        while total <= max_bytes:
            wanted = min(URL_CHUNK_SIZE, max_bytes - total + 1)
            try:
                chunk = response.read(wanted)
            except TypeError:
                # Some response-like objects only implement read() with no
                # size argument; the byte budget below still applies.
                chunk = response.read()
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise ValueError(
                    f"Download exceeds the {max_bytes} byte limit: {url!r}"
                )
            chunks.append(bytes(chunk))
            if len(chunk) < URL_CHUNK_SIZE:
                break

    return b"".join(chunks), content_type, final_url


def fetch_url_bytes(
    url: str,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
    timeout: int = URL_TIMEOUT,
) -> bytes:
    """Shared, size-capped, SSRF-safe byte fetch used by all image downloaders."""
    raw, _, _ = _fetch_stream(url, max_bytes=max_bytes, timeout=timeout)
    return raw


def _fetch_bytes(
    url: str, timeout: int = 20, max_bytes: int = MAX_DOWNLOAD_BYTES
) -> Tuple[bytes, str, str]:
    """Fetch URL bytes plus content type and final (post-redirect) URL."""
    return _fetch_stream(url, max_bytes=max_bytes, timeout=timeout)


def _cache_directory(cache_dir: Optional[str] = None) -> str:
    directory = cache_dir or os.path.join(tempfile.gettempdir(), "ascii_player_url_cache")
    os.makedirs(directory, exist_ok=True)
    return directory


def _save_cached_bytes(raw: bytes, key: str, ext: str, cache_dir: Optional[str] = None) -> str:
    directory = _cache_directory(cache_dir)
    digest = hashlib.sha256(key.encode("utf-8", "replace")).hexdigest()[:16]
    path = os.path.join(directory, f"url_{digest}{ext}")
    with open(path, "wb") as handle:
        handle.write(raw)
    return path


def _save_cached_png(image: Image.Image, key: str, cache_dir: Optional[str] = None) -> str:
    directory = _cache_directory(cache_dir)
    digest = hashlib.sha256(key.encode("utf-8", "replace")).hexdigest()[:16]
    path = os.path.join(directory, f"url_{digest}.png")
    image.convert("RGB").save(path, format="PNG")
    return path


def _decode_image_payload(
    raw: bytes, source_url: str, cache_dir: Optional[str] = None
) -> Tuple[Image.Image, List[Tuple[Image.Image, float]], str]:
    opened = Image.open(io.BytesIO(raw))
    total = int(getattr(opened, "n_frames", 1) or 1)
    frames: List[Tuple[Image.Image, float]] = []
    if total > 1:
        for index in range(total):
            try:
                opened.seek(index)
            except EOFError:
                break
            duration = opened.info.get("duration", 100) or 100
            try:
                seconds = max(0.02, float(duration) / 1000.0)
            except (TypeError, ValueError):
                seconds = 0.1
            frames.append((opened.convert("RGB").copy(), seconds))
        ext = ".webp" if (opened.format or "").upper() == "WEBP" else ".gif"
        saved_path = _save_cached_bytes(raw, source_url, ext, cache_dir=cache_dir)
        first = frames[0][0]
    else:
        opened.seek(0)
        first = opened.convert("RGB")
        saved_path = _save_cached_png(first, source_url, cache_dir=cache_dir)
    return first, frames, saved_path


def resolve_url(url: str, timeout: int = 20, cache_dir: Optional[str] = None) -> ResolvedURL:
    """Resolve an image URL, webpage URL, or YouTube/video URL for ASCII rendering."""
    normalized = normalize_url(url)
    parsed = urlparse(normalized)
    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"Unsupported or invalid URL: {url}")

    if is_youtube_url(normalized):
        video_id = extract_youtube_id(normalized)
        title = f"YouTube ({video_id})" if video_id else "YouTube Video"
        thumb_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id else None

        try:
            oembed_url = f"https://www.youtube.com/oembed?url={normalized}&format=json"
            raw_meta, _, _ = _fetch_bytes(oembed_url, timeout=min(8, timeout))
            meta = json.loads(raw_meta.decode("utf-8", "replace"))
            if meta.get("title"):
                title = str(meta["title"]).strip()
            if meta.get("thumbnail_url"):
                thumb_url = str(meta["thumbnail_url"]).strip()
        except Exception:
            pass

        if not thumb_url:
            raise ValueError("Could not determine YouTube thumbnail URL")

        raw_thumb, _, _ = _fetch_bytes(thumb_url, timeout=timeout)
        first, frames, saved = _decode_image_payload(raw_thumb, thumb_url, cache_dir=cache_dir)
        return ResolvedURL(
            url=normalized,
            kind="youtube",
            title=title,
            image=first,
            frames=frames,
            saved_path=saved,
            is_playable_video=True,
            resolved_image_url=thumb_url,
        )

    raw, content_type, final_url = _fetch_bytes(normalized, timeout=timeout)

    if content_type.startswith("image/"):
        first, frames, saved = _decode_image_payload(raw, final_url, cache_dir=cache_dir)
        title = os.path.basename(urlparse(final_url).path) or urlparse(final_url).netloc
        return ResolvedURL(
            url=normalized,
            kind="image",
            title=title,
            image=first,
            frames=frames,
            saved_path=saved,
            is_playable_video=False,
            resolved_image_url=final_url,
        )

    if content_type.startswith("video/"):
        title = os.path.basename(urlparse(final_url).path) or final_url
        ext = os.path.splitext(urlparse(final_url).path)[1].lower()
        if ext not in (".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v"):
            ext = ".mp4"
        saved = _save_cached_bytes(raw, final_url, ext, cache_dir=cache_dir)
        return ResolvedURL(
            url=normalized,
            kind="video",
            title=title,
            image=None,
            frames=[],
            saved_path=saved,
            is_playable_video=True,
            resolved_image_url=None,
        )

    looks_like_html = "html" in content_type or raw.lstrip()[:20].lower().startswith(
        (b"<!doctype", b"<html", b"<head", b"<meta")
    )
    if looks_like_html:
        html_text = raw.decode("utf-8", "replace")
        img_url, page_title = extract_webpage_image_url(html_text, final_url)
        if not img_url:
            raise ValueError("No usable image found on webpage")
        img_raw, _, resolved_img_url = _fetch_bytes(img_url, timeout=timeout)
        first, frames, saved = _decode_image_payload(
            img_raw, resolved_img_url, cache_dir=cache_dir
        )
        title = page_title or os.path.basename(urlparse(resolved_img_url).path) or final_url
        return ResolvedURL(
            url=normalized,
            kind="image",
            title=title,
            image=first,
            frames=frames,
            saved_path=saved,
            is_playable_video=False,
            resolved_image_url=resolved_img_url,
        )

    # Fallback: servers sometimes label PNG/JPG bytes as application/octet-stream.
    try:
        first, frames, saved = _decode_image_payload(raw, final_url, cache_dir=cache_dir)
        title = os.path.basename(urlparse(final_url).path) or urlparse(final_url).netloc
        return ResolvedURL(
            url=normalized,
            kind="image",
            title=title,
            image=first,
            frames=frames,
            saved_path=saved,
            is_playable_video=False,
            resolved_image_url=final_url,
        )
    except Exception as exc:
        raise ValueError(f"URL did not return a supported image or webpage: {exc}") from exc
