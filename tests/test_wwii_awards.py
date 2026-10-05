from io import BytesIO

from PIL import Image

from korea_service_record import medals, ribbons, wwii_awards


def test_biography_awards_cover_the_four_medal_maximum():
    assert wwii_awards.for_biography("601003") == (
        601064, 601066, 601072, 601076)
    assert wwii_awards.for_biography("601006") == (601076,)
    assert wwii_awards.for_biography("601014") == ()
    assert wwii_awards.for_biography("601003", country=602) == ()


def test_soviet_biography_awards_follow_explicit_campaign_service():
    assert wwii_awards.for_biography("501002", country=501) == (
        501050, 501053, 501054)
    assert wwii_awards.for_biography("501011", country=501) == (
        501052, 501053, 501054)
    assert wwii_awards.for_biography("501014", country=501) == (501054,)
    assert wwii_awards.for_biography("501003", country=501) == (501053,)
    assert wwii_awards.DEFENSE_MOSCOW not in {
        award_id
        for biography in range(1, 15)
        for award_id in wwii_awards.for_biography(f"501{biography:03d}", country=501)
    }


def test_existing_career_description_backfills_prior_service_awards():
    # This is the exact persisted format in an already-running career; the
    # awards need no database row or career restart to become wearable.
    assert wwii_awards.for_career_description(
        "biographyId=601003&birthDate=1920%2e02%2e23", country=601
    ) == (601064, 601066, 601072, 601076)
    assert wwii_awards.for_career_description(
        "birthDate=1908%2e07%2e20&biographyId=501014", country=501
    ) == (501054,)
    assert wwii_awards.for_career_description("birthDate=1920%2e02%2e23") == ()


def test_campaign_ladders_replace_five_bronze_stars_with_silver():
    assert ribbons.RIBBONS[601074].devices == ["star_silver"]
    assert ribbons.RIBBONS[601075].devices == ["star_bronze", "star_silver"]
    assert ribbons.RIBBONS[601068].devices == ["star_bronze"] * 3


def test_plain_art_composes_campaign_devices(tmp_path):
    ribbon_renderer = ribbons.RibbonRenderer(tmp_path)
    medal_renderer = medals.MedalRenderer(tmp_path, ribbon_renderer)
    ribbon = Image.open(BytesIO(ribbon_renderer.png(601075))).convert("RGBA")
    medal = Image.open(BytesIO(medal_renderer.png(601075))).convert("RGBA")
    assert ribbon.size == ribbons.CANVAS
    assert medal.size == medals.DRAPE
    assert ribbon.getbbox()
    assert medal.getbbox()


def test_soviet_loose_medals_share_the_mounted_canvas(tmp_path):
    ribbon_renderer = ribbons.RibbonRenderer(tmp_path)
    medal_renderer = medals.MedalRenderer(tmp_path, ribbon_renderer)
    for award_id in medals.SOVIET_WWII:
        ribbon = Image.open(BytesIO(ribbon_renderer.png(award_id))).convert("RGBA")
        medal = Image.open(BytesIO(medal_renderer.png(award_id))).convert("RGBA")
        assert ribbon.size == (460, 180)
        assert medal.size == medals.SOVIET_MOUNT_CANVAS
        assert ribbon.getbbox()
        assert medal.getbbox()
