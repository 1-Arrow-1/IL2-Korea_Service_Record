"""
The USAF promotion certificate: the owner's template filled in by hand.

Template ``static/images/certificates/USAF_promotion_cert_template.jpg``
(1014 x 1317 px at 100 ppi) is the owner's. Every field is set with Photoshop
tracking 65 (65/1000 em), centred on the owner's coordinates - the centre of
the text's ink, so a field grows equally to the left and the right.

The owner designed it in BeneScriptine (20.58 pt). That font is (c) 1990
R. Schenk, "all rights reserved", with no licence to pass it on, so it is
never bundled: it is used where it is installed in Windows, and everyone
else gets UnifrakturMaguntia (SIL Open Font License, shipped beside the
template with its licence), sized to the same width. Maguntia writes "-" as
the old Fraktur double hyphen; its en dash is a single stroke, so dashes
are set with that.

The two signatures sit above their printed titles: the Deputy Chief of Staff,
Personnel on the left and the Secretary of the Air Force on the right, each
the man in office on the date of the commission.
"""

import datetime as _dt
import hashlib
import io
from pathlib import Path
from typing import Dict, Optional, Tuple

STATIC = Path(__file__).resolve().parent / "static" / "images"
TEMPLATE = STATIC / "certificates" / "USAF_promotion_cert_template.jpg"
FALLBACK_FONT = STATIC / "certificates" / "UnifrakturMaguntia-Book.ttf"
OWNER_FONT = "BeneScriptine Regular.ttf"
SIGNATURES = STATIC / "signatures"

PPI = 100
FONT_PT = 20.58
TRACKING = 65 / 1000                     # Photoshop tracking, in em
INK = (34, 30, 28)

# Field centres in template pixels, from the owner's layout.
FIELDS = {
    "name": (506.62, 473.30),
    "rank": (551.97, 510.43),
    "rank_day": (474.29, 633.30),
    "rank_month": (743.20, 633.30),
    "rank_year": (335.26, 665.30),
    "done_day": (583.29, 1056.30),
    "done_month": (836.20, 1056.30),
    "done_year": (723.26, 1085.30),
    "independence": (810.29, 1112.30),
}

# The free space a field may fill (template pixels). "I do appoint him" ends
# at about x 268 and "in the" starts at 843: a long grade - "Lieutenant
# Colonel, United States Air Force" runs 590 px at full size - is set a
# little smaller there rather than run into the printed words.
MAX_WIDTH = {"rank": 560}

# Signatures: centred over their printed titles (measured on the template),
# bottom a few pixels above the title's ink, at a width a little wider than
# the title - a hand, not a stamp.
SIGNATURE_SLOTS = {
    "left": {"centre_x": 212, "bottom": 1222, "width": 210},     # DCS, Personnel
    "right": {"centre_x": 777, "bottom": 1229, "width": 210},    # Secretary of the Air Force
}

_ONES = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
         "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
         "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
_ORDINAL_ONES = ["", "first", "second", "third", "fourth", "fifth", "sixth", "seventh",
                 "eighth", "ninth", "tenth", "eleventh", "twelfth", "thirteenth",
                 "fourteenth", "fifteenth", "sixteenth", "seventeenth", "eighteenth",
                 "nineteenth"]
_ORDINAL_TENS = {20: "twentieth", 30: "thirtieth", 40: "fortieth", 50: "fiftieth",
                 60: "sixtieth", 70: "seventieth", 80: "eightieth", 90: "ninetieth"}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


def words(n: int) -> str:
    """0..99 in words, hyphenated as written: fifty-one, seventy-five."""
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    return _TENS[tens] + ("-" + _ONES[ones] if ones else "")


def ordinal(n: int) -> str:
    """1..99 as a written ordinal: first, twentieth, seventy-fifth."""
    if n < 20:
        return _ORDINAL_ONES[n]
    if n % 10 == 0:
        return _ORDINAL_TENS[n]
    return _TENS[n // 10] + "-" + _ORDINAL_ONES[n % 10]


def signing_date(name: str, date: Tuple[int, int, int]) -> Tuple[int, int, int]:
    """
    The day the commission was signed in Washington: a few days after the
    date of rank, as on a real commission - 3 to 12, fixed for this man and
    this promotion so the certificate reads the same every time it is shown.
    """
    seed = hashlib.sha256(f"{name}|{date}".encode("utf-8")).digest()[0]
    signed = _dt.date(*date) + _dt.timedelta(days=3 + seed % 10)
    return (signed.year, signed.month, signed.day)


def independence_year(year: int, month: int, day: int) -> int:
    """The year of American Independence, which turns over on 4 July."""
    return year - 1776 + (1 if (month, day) >= (7, 4) else 0)


def fields_for(name: str, rank: str, date: Tuple[int, int, int],
               done: Optional[Tuple[int, int, int]] = None) -> Dict[str, str]:
    """
    The written-out text of every field. ``date`` is the commission (rank
    from), ``done`` the day it was signed - a few days later
    (signing_date) unless given.
    Years are written as on the form, after "nineteen hundred and". The
    year of Independence is an ordinal counted from 4 July 1776, as on a
    real commission: 23 June 1951 is in the one hundred and seventy-fifth,
    4 July 1951 begins the seventy-sixth.
    """
    y, m, d = date
    dy, dm, dd = done or signing_date(name, date)
    return {
        "name": name,
        "rank": f"{rank}, United States Air Force",
        "rank_day": ordinal(d),
        "rank_month": MONTHS[m - 1],
        "rank_year": words(y - 1900),
        "done_day": ordinal(dd),
        "done_month": MONTHS[dm - 1],
        "done_year": words(dy - 1900),
        "independence": ordinal(independence_year(dy, dm, dd) - 100),
    }


def font_choice() -> Tuple[Path, int, Dict[str, str]]:
    """
    (font file, pixel size, character substitutions): BeneScriptine where
    Windows has it installed, otherwise the bundled UnifrakturMaguntia at
    the size that sets a name as wide (27 px against BeneScriptine's 29).
    """
    import os
    for folder in (Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts",
                   Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"):
        candidate = folder / OWNER_FONT
        if candidate.is_file():
            return candidate, round(FONT_PT * PPI / 72), {}
    return FALLBACK_FONT, 27, {"-": "–"}           # en dash: a single stroke


def _font(size: Optional[int] = None):
    from PIL import ImageFont
    path, default, _ = font_choice()
    return ImageFont.truetype(str(path), size or default)


def _ink_width(text: str, font) -> float:
    track = TRACKING * font.size
    return font.getlength(text) + max(0, len(text) - 1) * track


def _fitting(text: str, max_width: Optional[float]):
    """The field's font, made smaller only if the text would not fit."""
    font = _font()
    if max_width:
        size = font.size
        while size > 10 and _ink_width(text, font) > max_width:
            size -= 1
            font = _font(size)
    return font


def _draw_centred(image, text: str, centre: Tuple[float, float], font) -> None:
    """Draw ``text`` with tracking so that its ink is centred on ``centre``."""
    from PIL import Image, ImageDraw
    track = TRACKING * font.size
    # each character where the whole string's own advance puts it, plus the
    # tracking - keeps the font's kerning, which drawing glyph by glyph loses
    xs = [font.getlength(text[:i]) + i * track for i in range(len(text))]
    width = int((xs[-1] if xs else 0) + font.getlength(text[-1:] or " ") + 4 * font.size)
    height = int(font.size * 3)
    layer = Image.new("L", (width, height), 0)
    pen = ImageDraw.Draw(layer)
    origin = (2 * font.size, font.size)
    for x, ch in zip(xs, text):
        pen.text((origin[0] + x, origin[1]), ch, font=font, fill=255)
    box = layer.getbbox()
    if box is None:
        return
    ink = layer.crop(box)
    left = round(centre[0] - ink.width / 2)
    top = round(centre[1] - ink.height / 2)
    image.paste(Image.new("RGB", ink.size, INK), (left, top), ink)


def _signature(image, file: Path, slot: Dict[str, int]) -> None:
    from PIL import Image
    if not file.is_file():
        return
    with Image.open(file) as sig:
        sig = sig.convert("RGBA")
        box = sig.getbbox()
        if box:
            sig = sig.crop(box)
        h = round(sig.height * slot["width"] / sig.width)
        sig = sig.resize((slot["width"], h), Image.LANCZOS)
    image.paste(sig, (round(slot["centre_x"] - sig.width / 2), slot["bottom"] - sig.height), sig)


def signers(date: Tuple[int, int, int]) -> Tuple[Optional[str], Optional[str]]:
    """
    The signature stems for a commission signed on ``date``: the Deputy Chief
    of Staff, Personnel (left) and the Secretary of the Air Force (right) in
    office that day, from the signer table the award certificates use
    (locales/citations/eng.json, certificate.signers). The Edwards -> Kuter
    hand-over in mid-1951 is approximate.
    """
    import json
    table = json.loads((Path(__file__).resolve().parent / "locales" / "citations" /
                        "eng.json").read_text(encoding="utf-8"))["certificate"]["signers"]
    day = "%04d.%02d.%02d" % date

    def pick(office):
        rows = table.get(office) or []
        row = next((r for r in rows if day <= r[0]), rows[-1] if rows else None)
        return row[3] if row and len(row) > 3 else None
    return pick("personnel"), pick("secretary")


def render(name: str, rank: str, date: Tuple[int, int, int],
           left_signature: Optional[str] = None, right_signature: Optional[str] = None,
           done: Optional[Tuple[int, int, int]] = None) -> bytes:
    """The filled-in certificate as JPEG bytes. Signatures are file stems in
    static/images/signatures, by default the men in office on the signing
    date; a missing image leaves its line empty."""
    from PIL import Image
    signed = done or signing_date(name, date)
    if left_signature is None and right_signature is None:
        left_signature, right_signature = signers(signed)
    with Image.open(TEMPLATE) as template:
        image = template.convert("RGB")
    substitutions = font_choice()[2]
    for key, text in fields_for(name, rank, date, signed).items():
        for plain, glyph in substitutions.items():
            text = text.replace(plain, glyph)
        _draw_centred(image, text, FIELDS[key], _fitting(text, MAX_WIDTH.get(key)))
    if left_signature:
        _signature(image, SIGNATURES / f"{left_signature}.png", SIGNATURE_SLOTS["left"])
    if right_signature:
        _signature(image, SIGNATURES / f"{right_signature}.png", SIGNATURE_SLOTS["right"])
    out = io.BytesIO()
    image.save(out, "JPEG", quality=92)
    return out.getvalue()
