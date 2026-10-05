import hashlib
import sqlite3
from pathlib import Path

from PIL import Image

import custom_pilot_photo as photo
from career_helper import Career


def portrait_career(path: Path) -> Career:
    with sqlite3.connect(path) as con:
        con.executescript(
            """
            CREATE TABLE career (playerId INTEGER);
            CREATE TABLE pilot (
                id INTEGER PRIMARY KEY, name TEXT, lastName TEXT,
                personageId INTEGER, avatarPath TEXT, isPlayer INTEGER
            );
            INSERT INTO career VALUES (2);
            INSERT INTO pilot VALUES (1, 'Old', 'Pilot', 601001, 'usa50a/1', 1);
            INSERT INTO pilot VALUES (2, 'Current', 'Pilot', 601002, 'usa50a/7', 1);
            """
        )
    return Career(path)


def test_player_portrait_updates_only_career_player(tmp_path):
    career = portrait_career(tmp_path / "Portrait Test.db")

    assert career.player_portrait() == {
        "id": 2,
        "name": "Current Pilot",
        "personage_id": 601002,
        "avatar_path": "usa50a/7",
    }
    backup = career.set_player_portrait("custom/example-2")

    assert backup.is_file()
    with sqlite3.connect(career.path) as con:
        assert con.execute(
            "SELECT id, avatarPath FROM pilot ORDER BY id"
        ).fetchall() == [(1, "usa50a/1"), (2, "custom/example-2")]


def test_restore_record_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("KOREA_TRACKER_CACHE", str(tmp_path / "cache/assets"))
    career = tmp_path / "My Career.db"
    saved = {
        "career": str(career), "pilot_id": 42,
        "original_avatar_path": "usa50a/4",
        "custom_avatar_path": "custom/example-42",
    }

    target = photo.save_state(career, saved)
    assert target.parent == tmp_path / "cache" / photo.STATE_FOLDER
    assert photo.load_state(career) == saved

    photo.clear_state(career)
    assert photo.load_state(career) is None


def test_composition_is_game_size_and_uses_position():
    background = Image.new("RGB", (512, 512), "#887766")
    foreground = Image.new("RGBA", (100, 200), (220, 10, 10, 255))

    centered = photo.compose_portrait(foreground, background, zoom=0.5)
    shifted = photo.compose_portrait(
        foreground, background, zoom=0.5, center_x=500, center_y=256
    )

    assert centered.mode == "RGB"
    assert centered.size == (512, 512)
    assert centered.getpixel((256, 256))[0] > 200
    assert shifted.getpixel((256, 256)) == (136, 119, 102)


def test_edge_cleanup_visibly_contracts_the_mask():
    foreground = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    foreground.paste((220, 10, 10, 255), (8, 8, 56, 56))

    original = foreground.getchannel("A").getbbox()
    cleaned = photo.clean_alpha(foreground, 4).getchannel("A").getbbox()

    assert original == (8, 8, 56, 56)
    assert cleaned[0] > original[0] and cleaned[1] > original[1]
    assert cleaned[2] < original[2] and cleaned[3] < original[3]


def test_sepia_strength_blends_portrait_and_preserves_alpha():
    foreground = Image.new("RGBA", (2, 1), (100, 150, 200, 73))

    unchanged = photo.apply_sepia(foreground, 0)
    partial = photo.apply_sepia(foreground, 0.5)
    full = photo.apply_sepia(foreground, 1)

    assert unchanged.getpixel((0, 0)) == (100, 150, 200, 73)
    assert partial.getpixel((0, 0)) == (146, 160, 166, 73)
    assert full.getpixel((0, 0)) == (192, 171, 133, 73)


def test_sepia_changes_only_the_foreground():
    background = Image.new("RGB", (512, 512), (20, 40, 80))
    foreground = Image.new("RGBA", (100, 100), (100, 150, 200, 255))

    result = photo.compose_portrait(
        foreground, background, zoom=0.5, sepia_strength=1,
    )

    assert result.getpixel((0, 0)) == (20, 40, 80)
    assert result.getpixel((256, 256)) == (192, 171, 133)


def test_tone_controls_preserve_alpha_and_have_neutral_defaults():
    foreground = Image.new("RGBA", (1, 1), (100, 150, 200, 73))

    neutral = photo.adjust_tone(foreground)
    exposed = photo.adjust_tone(foreground, exposure=1)
    monochrome = photo.adjust_tone(foreground, saturation=-100)

    assert neutral.getpixel((0, 0)) == (100, 150, 200, 73)
    assert exposed.getpixel((0, 0)) == (200, 255, 255, 73)
    assert monochrome.getpixel((0, 0)) == (141, 141, 141, 73)


def test_contrast_expands_tonal_difference():
    foreground = Image.new("RGBA", (2, 1))
    foreground.putdata(((50, 50, 50, 255), (200, 200, 200, 255)))

    adjusted = photo.adjust_tone(foreground, contrast=50)

    assert adjusted.getpixel((0, 0))[0] < 50
    assert adjusted.getpixel((1, 0))[0] > 200


def test_bundled_model_is_upstream_u2netp():
    model = Path(__file__).parents[1] / "korea_service_record/models/u2netp.onnx"
    assert hashlib.md5(model.read_bytes()).hexdigest() == "8e83ca70e441ab06c318d82300c84806"  # noqa: S324 - upstream identity


def test_texconv_creates_the_game_portrait_contract(tmp_path):
    converter = Path(__file__).parents[1] / "vendor/directxtex/texconv.exe"
    result = photo.convert_to_dds(
        Image.new("RGB", (512, 512), "#a88e68"),
        tmp_path / "pilot.dds", converter,
    )

    assert photo.validate_dds(result) == {
        "width": 512, "height": 512, "mipmaps": 3,
        "dxgi_format": 98, "bytes": 344212,
    }
