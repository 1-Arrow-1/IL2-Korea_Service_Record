from PIL import Image

from korea_service_record.icons import strip_baked_shadow


def test_baked_black_shadow_goes_and_the_medal_edge_stays():
    tile = Image.new("RGBA", (4, 1))
    tile.putpixel((0, 0), (0, 0, 0, 120))        # the game's soft shadow
    tile.putpixel((1, 0), (12, 10, 8, 249))      # still shadow, nearly opaque
    tile.putpixel((2, 0), (200, 160, 60, 120))   # the medal's anti-aliased gold rim
    tile.putpixel((3, 0), (0, 0, 0, 255))        # solid black enamel inside the medal
    out = strip_baked_shadow(tile)
    assert out.getpixel((0, 0))[3] == 0
    assert out.getpixel((1, 0))[3] == 0
    assert out.getpixel((2, 0)) == (200, 160, 60, 120)
    assert out.getpixel((3, 0)) == (0, 0, 0, 255)
