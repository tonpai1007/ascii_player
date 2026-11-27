"""Tests for ascii_player.prompt_gen (multi-engine prompt-to-ASCII generator)."""

import io
import json
import socket
import sys
import types

import pytest
from PIL import Image

from ascii_player.prompt_gen import (
    STARTER_PROMPTS,
    available_banner_fonts,
    generate_banner,
    generate_from_prompt,
    generate_gemini_image,
    generate_ollama_ascii,
    generate_openai_image,
    generate_pollinations_image,
    generate_procedural,
    generate_web_image,
)


@pytest.fixture(autouse=True)
def _public_dns(monkeypatch):
    """Web image URLs must resolve to a public IP for the shared fetcher."""

    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    monkeypatch.setattr("ascii_player.url_loader.socket.getaddrinfo", fake_getaddrinfo)


def _png_bytes(color=(30, 120, 220)):
    buf = io.BytesIO()
    Image.new("RGB", (24, 16), color).save(buf, format="PNG")
    return buf.getvalue()


def test_available_banner_fonts_and_starter_prompts():
    fonts = available_banner_fonts()
    assert len(fonts) >= 1
    assert len(STARTER_PROMPTS) >= 4


def test_generate_banner_produces_grid():
    res = generate_banner("ASCII", font="slant", width=80)
    assert res.engine == "banner"
    assert res.grid is not None
    assert res.grid.width >= 5
    assert res.grid.height >= 1


@pytest.mark.parametrize(
    "prompt",
    [
        "mount fuji at sunset",
        "cyberpunk skyline city",
        "ringed planet in deep space",
        "cyberpunk samurai cat",
        "neon retro skull",
        "glowing heart",
        "fractal forest tree",
        "ocean wave storm",
        "futuristic robot mech",
        "cosmic spiral mandala",
        "arbitrary abstract concept",
    ],
)
def test_generate_procedural_motifs(prompt, tmp_path):
    res = generate_procedural(prompt, size=(160, 100), save=True, cache_dir=str(tmp_path))
    assert res.engine == "procedural"
    assert res.image is not None
    assert res.image.size == (160, 100)
    assert res.saved_path is not None
    assert res.saved_path.endswith(".png")


def test_generate_procedural_is_deterministic(tmp_path):
    import numpy as np

    r1 = generate_procedural("neon owl", size=(80, 50), save=False)
    r2 = generate_procedural("neon owl", size=(80, 50), save=False)
    assert np.array_equal(np.asarray(r1.image), np.asarray(r2.image))


def test_generate_ollama_ascii_uses_keep_alive_zero(monkeypatch):
    seen_payloads = []

    class FakeResp:
        def __init__(self, body):
            self._body = body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return self._body

    def fake_urlopen(req, timeout=10):
        if req.full_url.endswith("/api/tags"):
            return FakeResp(json.dumps({"models": [{"name": "llama3.2:3b"}]}).encode())
        if req.full_url.endswith("/api/generate"):
            seen_payloads.append(json.loads(req.data.decode("utf-8")))
            return FakeResp(
                json.dumps({"response": "```\n /\\_/\\\n( o.o )\n > ^ <\n```"}).encode()
            )
        raise AssertionError(f"Unexpected URL: {req.full_url}")

    monkeypatch.setattr("ascii_player.prompt_gen.urllib.request.urlopen", fake_urlopen)
    res = generate_ollama_ascii("cat", width=40)
    assert res.engine == "ollama"
    assert res.grid is not None
    assert seen_payloads and seen_payloads[0]["keep_alive"] == 0
    assert seen_payloads[0]["stream"] is False


def test_generate_pollinations_image_mock(monkeypatch, tmp_path):
    raw = _png_bytes((200, 50, 90))

    class FakeResp:
        headers = {"Content-Type": "image/png"}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return raw

    monkeypatch.setattr(
        "ascii_player.prompt_gen.urllib.request.urlopen", lambda *a, **k: FakeResp()
    )
    res = generate_pollinations_image("neon dragon", cache_dir=str(tmp_path))
    assert res.engine == "pollinations"
    assert res.image is not None
    assert res.saved_path is not None


def test_generate_web_image_mock(monkeypatch, tmp_path):
    raw = _png_bytes((10, 200, 100))

    class FakeDDGS:
        def images(self, query, max_results=6):
            return [{"image": "https://example.com/pic.png"}]

    class FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return raw

    fake_ddgs_mod = types.ModuleType("ddgs")
    fake_ddgs_mod.DDGS = FakeDDGS
    monkeypatch.setitem(sys.modules, "ddgs", fake_ddgs_mod)
    monkeypatch.setattr(
        "ascii_player.prompt_gen.urllib.request.urlopen", lambda *a, **k: FakeResp()
    )
    res = generate_web_image("owl", cache_dir=str(tmp_path))
    assert res.engine == "web"
    assert res.image is not None


def test_generate_gemini_image_mock(monkeypatch, tmp_path):
    raw = _png_bytes((10, 40, 200))

    class FakePart:
        inline_data = types.SimpleNamespace(data=raw)

    class FakeModels:
        def generate_content(self, **kwargs):
            return types.SimpleNamespace(parts=[FakePart()])

    class FakeClient:
        def __init__(self, api_key=None):
            self.models = FakeModels()

    fake_genai_types = types.SimpleNamespace(
        GenerateContentConfig=lambda **kw: kw,
        ImageConfig=lambda **kw: kw,
    )
    fake_genai_mod = types.ModuleType("google.genai")
    fake_genai_mod.Client = FakeClient
    fake_genai_mod.types = fake_genai_types
    fake_google_mod = types.ModuleType("google")
    fake_google_mod.genai = fake_genai_mod

    monkeypatch.setitem(sys.modules, "google", fake_google_mod)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai_mod)
    monkeypatch.setitem(sys.modules, "google.genai.types", fake_genai_types)

    res = generate_gemini_image("astronaut", api_key="test-key", cache_dir=str(tmp_path))
    assert res.engine == "gemini"
    assert res.image is not None


def test_generate_openai_image_mock(monkeypatch, tmp_path):
    import base64

    b64 = base64.b64encode(_png_bytes((220, 180, 20))).decode("ascii")

    class FakeImages:
        def generate(self, **kwargs):
            return types.SimpleNamespace(data=[types.SimpleNamespace(b64_json=b64, url=None)])

    class FakeOpenAI:
        def __init__(self, api_key=None):
            self.images = FakeImages()

    fake_openai = types.ModuleType("openai")
    fake_openai.OpenAI = FakeOpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_openai)

    res = generate_openai_image("lighthouse", api_key="sk-test", cache_dir=str(tmp_path))
    assert res.engine == "openai"
    assert res.image is not None


def test_generate_from_prompt_auto_falls_back_to_procedural(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        "ascii_player.prompt_gen.generate_pollinations_image",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    monkeypatch.setattr(
        "ascii_player.prompt_gen.generate_web_image",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    monkeypatch.setattr(
        "ascii_player.prompt_gen.generate_ollama_ascii",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no ollama")),
    )

    res = generate_from_prompt("samurai cat", engine="auto", cache_dir=str(tmp_path))
    assert res.engine == "procedural"
    assert res.image is not None


def test_generate_from_prompt_rejects_empty():
    with pytest.raises(ValueError):
        generate_from_prompt("   ")
