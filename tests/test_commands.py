"""Tests for ascii_player.tui.commands (omnibox parsing & slash autocomplete)."""

from PIL import Image

from ascii_player.tui.commands import (
    SLASH_COMMANDS,
    canonical_command_name,
    filter_slash_commands,
    find_matching_media_files,
    parse_omnibox_input,
)


def test_slash_commands_registry_populated():
    names = {cmd.name for cmd in SLASH_COMMANDS}
    assert "/prompt" in names
    assert "/webcam" in names
    assert "/preset" in names
    assert "/fx" in names
    assert "/color" in names
    assert "/export" in names


def test_canonical_command_aliases():
    assert canonical_command_name("/cam") == "/webcam"
    assert canonical_command_name("/freeze") == "/snap"
    assert canonical_command_name("/save") == "/export"
    assert canonical_command_name("/files") == "/open"
    assert canonical_command_name("/home") == "/clear"
    assert canonical_command_name("/type") == "/draw"
    assert parse_omnibox_input("/type skull") == ("command", "/draw", "skull")


def test_filter_slash_commands():
    top = filter_slash_commands("/", limit=6)
    assert len(top) == 6
    matches = filter_slash_commands("/pr", limit=8)
    names = [m.name for m in matches]
    assert "/prompt" in names
    assert "/preset" in names
    fx_matches = filter_slash_commands("/f", limit=8)
    assert "/fx" in [m.name for m in fx_matches]
    assert parse_omnibox_input("/fx scanlines") == ("command", "/fx", "scanlines")
    assert filter_slash_commands("/zzznomatch") == []


def test_parse_omnibox_input_variants(tmp_path):
    img = tmp_path / "shot.png"
    Image.new("RGB", (4, 4), (1, 2, 3)).save(img)

    assert parse_omnibox_input("   ") == ("empty", "", "")
    assert parse_omnibox_input("/cam edge") == ("command", "/webcam", "edge")
    assert parse_omnibox_input("/save out.png") == ("command", "/export", "out.png")
    assert parse_omnibox_input("@shot") == ("at_file", "shot", "")
    assert parse_omnibox_input(f'"{img}"') == ("file", str(img), "")
    assert parse_omnibox_input(str(tmp_path)) == ("dir", str(tmp_path), "")
    assert parse_omnibox_input("https://example.com/a.png") == (
        "url",
        "https://example.com/a.png",
        "",
    )
    assert parse_omnibox_input("www.example.com") == ("url", "www.example.com", "")
    assert parse_omnibox_input("cyberpunk samurai cat") == (
        "prompt",
        "cyberpunk samurai cat",
        "",
    )


def test_find_matching_media_files(tmp_path):
    (tmp_path / "cat.png").write_bytes(b"png")
    (tmp_path / "car.jpg").write_bytes(b"jpg")
    (tmp_path / "clip.mp4").write_bytes(b"mp4")
    (tmp_path / "notes.txt").write_text("ignore", encoding="utf-8")
    sub = tmp_path / "assets"
    sub.mkdir()
    (sub / "cat_banner.webp").write_bytes(b"webp")

    all_media = find_matching_media_files(str(tmp_path), "", limit=10)
    rels = [r for r, _full, _k in all_media]
    assert "cat.png" in rels
    assert "clip.mp4" in rels
    assert "notes.txt" not in rels

    cat_hits = find_matching_media_files(str(tmp_path), "cat", limit=10)
    assert cat_hits[0][0] == "cat.png"
    assert any("cat_banner.webp" in r for r, _f, _k in cat_hits)
