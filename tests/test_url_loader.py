"""Tests for ascii_player.url_loader (images, webpages, YouTube)."""

import io
import json
import os
import socket

import pytest
from PIL import Image

from ascii_player.url_loader import (
    extract_webpage_image_url,
    extract_youtube_id,
    fetch_url_bytes,
    is_safe_url,
    normalize_url,
    resolve_url,
    resolved_video_source,
)


@pytest.fixture(autouse=True)
def _public_dns(monkeypatch):
    """Resolve example.com-style hosts to a public IP unless a test overrides it."""

    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))
        ]

    monkeypatch.setattr("ascii_player.url_loader.socket.getaddrinfo", fake_getaddrinfo)


def _png_bytes(color=(12, 34, 56)):
    buf = io.BytesIO()
    Image.new("RGB", (16, 12), color).save(buf, format="PNG")
    return buf.getvalue()


def _gif_bytes():
    buf = io.BytesIO()
    frames = [Image.new("RGB", (12, 8), (i * 80, 20, 40)) for i in range(3)]
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:], duration=60, loop=0)
    return buf.getvalue()


class FakeResponse:
    def __init__(self, data: bytes, content_type: str, final_url: str):
        self._data = data
        self.headers = {"Content-Type": content_type}
        self._final_url = final_url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._data

    def geturl(self):
        return self._final_url


def test_normalize_url():
    assert normalize_url("  www.example.com/a.png ") == "https://www.example.com/a.png"
    assert normalize_url("https://example.com") == "https://example.com"


def test_extract_youtube_id():
    assert extract_youtube_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_id("https://youtu.be/dQw4w9WgXcQ?t=10") == "dQw4w9WgXcQ"
    assert extract_youtube_id("https://youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_id("https://example.com/video") is None


def test_extract_webpage_image_url_priority():
    html = """
    <html><head><title>Sample   Page</title>
    <meta property="og:image" content="/hero.png">
    <meta name="twitter:image" content="/tw.png">
    </head><body><img src="/body.jpg"></body></html>
    """
    img_url, title = extract_webpage_image_url(html, "https://example.com/post/1")
    assert img_url == "https://example.com/hero.png"
    assert title == "Sample Page"

    html_img = '<html><body><img data-src="assets/pic.webp"></body></html>'
    img_url2, _ = extract_webpage_image_url(html_img, "https://example.com/page/")
    assert img_url2 == "https://example.com/page/assets/pic.webp"


def test_resolve_url_image_without_extension(monkeypatch, tmp_path):
    raw = _png_bytes((200, 100, 50))
    monkeypatch.setattr(
        "ascii_player.url_loader.urllib.request.urlopen",
        lambda req, timeout=20: FakeResponse(raw, "image/png; charset=binary", req.full_url),
    )
    res = resolve_url("https://example.com/avatar?id=42", cache_dir=str(tmp_path))
    assert res.kind == "image"
    assert res.image is not None
    assert res.saved_path.endswith(".png")
    assert res.is_playable_video is False


def test_resolve_url_animated_gif(monkeypatch, tmp_path):
    raw = _gif_bytes()
    monkeypatch.setattr(
        "ascii_player.url_loader.urllib.request.urlopen",
        lambda req, timeout=20: FakeResponse(raw, "image/gif", req.full_url),
    )
    res = resolve_url("https://example.com/loop", cache_dir=str(tmp_path))
    assert res.kind == "image"
    assert len(res.frames) == 3
    assert res.saved_path.endswith(".gif")


def test_resolve_url_webpage_og_image(monkeypatch, tmp_path):
    html = (
        '<html><head><title>Cool Article</title>'
        '<meta property="og:image" content="https://cdn.example.com/cover.png"></head></html>'
    ).encode("utf-8")
    png = _png_bytes((10, 20, 30))

    def fake_urlopen(req, timeout=20):
        if "cover.png" in req.full_url:
            return FakeResponse(png, "image/png", req.full_url)
        return FakeResponse(html, "text/html; charset=utf-8", req.full_url)

    monkeypatch.setattr("ascii_player.url_loader.urllib.request.urlopen", fake_urlopen)
    res = resolve_url("https://example.com/article", cache_dir=str(tmp_path))
    assert res.kind == "image"
    assert res.title == "Cool Article"
    assert res.resolved_image_url == "https://cdn.example.com/cover.png"


def test_resolve_url_youtube(monkeypatch, tmp_path):
    oembed = json.dumps(
        {
            "title": "Demo Video",
            "thumbnail_url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
        }
    ).encode("utf-8")
    png = _png_bytes((90, 90, 90))

    def fake_urlopen(req, timeout=20):
        if "oembed" in req.full_url:
            return FakeResponse(oembed, "application/json", req.full_url)
        return FakeResponse(png, "image/jpeg", req.full_url)

    monkeypatch.setattr("ascii_player.url_loader.urllib.request.urlopen", fake_urlopen)
    res = resolve_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ", cache_dir=str(tmp_path))
    assert res.kind == "youtube"
    assert res.title == "Demo Video"
    assert res.is_playable_video is True
    assert res.image is not None


def test_resolve_url_rejects_invalid():
    with pytest.raises(ValueError):
        resolve_url("not a valid url")


def test_resolve_url_video_saves_downloadable_file(monkeypatch, tmp_path):
    raw = b"fake mp4 payload"
    monkeypatch.setattr(
        "ascii_player.url_loader.urllib.request.urlopen",
        lambda req, timeout=20: FakeResponse(raw, "video/mp4", req.full_url),
    )
    res = resolve_url("https://example.com/clip.mp4", cache_dir=str(tmp_path))
    assert res.kind == "video"
    assert res.saved_path and os.path.exists(res.saved_path)
    assert resolved_video_source(res) == res.saved_path


def test_resolved_video_source_rejects_non_video_or_missing_file(tmp_path):
    from ascii_player.url_loader import ResolvedURL

    image = ResolvedURL(url="https://example.com/a.png", kind="image", title="a")
    assert resolved_video_source(image) is None
    video = ResolvedURL(
        url="https://example.com/a.mp4",
        kind="video",
        title="a",
        saved_path=str(tmp_path / "missing.mp4"),
    )
    assert resolved_video_source(video) is None
    assert resolved_video_source(None) is None


# --------------------------------------------------------- URL security --


class _ChunkedResponse:
    """urlopen stand-in that honours read(n) so size caps can be exercised."""

    def __init__(self, payload: bytes, final_url: str):
        self._payload = payload
        self._final_url = final_url
        self.headers = {"Content-Type": "image/png"}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size=-1):
        if size is None or size < 0:
            data = self._payload
        else:
            data = self._payload[:size]
        self._payload = self._payload[len(data) :]
        return data

    def geturl(self):
        return self._final_url


def test_is_safe_url_public_and_schemes():
    assert is_safe_url("https://example.com/a.png") is True
    assert is_safe_url("http://example.com/a.png") is True
    assert is_safe_url("file:///etc/passwd") is False
    assert is_safe_url("ftp://example.com/a.png") is False
    assert is_safe_url("not a url") is False


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.1.2.3",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "0.0.0.0",
        "::1",
        "::ffff:127.0.0.1",
        "224.0.0.1",
    ],
)
def test_is_safe_url_rejects_private_literal_ips(address):
    assert is_safe_url(f"http://{address}/secret") is False


def test_is_safe_url_rejects_private_dns_answer(monkeypatch):
    monkeypatch.setattr(
        "ascii_player.url_loader.socket.getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 80))],
    )
    assert is_safe_url("https://internal.example.com/") is False


def test_is_safe_url_fails_closed_on_dns_error(monkeypatch):
    def boom(*args, **kwargs):
        raise socket.gaierror("no such host")

    monkeypatch.setattr("ascii_player.url_loader.socket.getaddrinfo", boom)
    assert is_safe_url("https://example.com/") is False


def test_fetch_url_bytes_rejects_file_scheme():
    with pytest.raises(ValueError, match="Unsafe or invalid URL"):
        fetch_url_bytes("file:///etc/passwd")


def test_fetch_url_bytes_rejects_private_ip(monkeypatch):
    monkeypatch.setattr(
        "ascii_player.url_loader.socket.getaddrinfo",
        lambda *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 80))
        ],
    )
    with pytest.raises(ValueError, match="Unsafe or invalid URL"):
        fetch_url_bytes("http://metadata.example.com/latest/meta-data")


def test_fetch_url_bytes_rejects_oversized_download(monkeypatch):
    payload = b"x" * 5000
    monkeypatch.setattr(
        "ascii_player.url_loader.urllib.request.urlopen",
        lambda req, timeout=15: _ChunkedResponse(payload, req.full_url),
    )
    with pytest.raises(ValueError, match="byte limit"):
        fetch_url_bytes("https://example.com/big.bin", max_bytes=1000)


def test_fetch_url_bytes_success(monkeypatch):
    payload = b"hello world"
    monkeypatch.setattr(
        "ascii_player.url_loader.urllib.request.urlopen",
        lambda req, timeout=15: _ChunkedResponse(payload, req.full_url),
    )
    assert fetch_url_bytes("https://example.com/hello.txt") == payload
