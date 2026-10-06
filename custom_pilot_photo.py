"""Create and install game-ready custom pilot portraits.

The editor in :mod:`career_helper` keeps the UI concerns.  This module owns
the parts that need to be independently testable: local foreground
segmentation, 512 px composition, BC7 DDS conversion and the small restore
record that remembers a career's original ``avatarPath``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

from korea_service_record.assets import default_cache_dir
from korea_service_record.portraitfix import MAX_AVATAR_PATH, short_avatar_path  # noqa: F401


PORTRAIT_SIZE = 512
MODEL_RELATIVE = Path("korea_service_record/models/u2netp.onnx")
BACKGROUND_RELATIVE = Path(
    "korea_service_record/static/images/custom_pilot_photo_background.jpg"
)
STATE_FOLDER = "custom-portraits"


def bundle_root() -> Path:
    """Source tree or PyInstaller's on-disk ``_internal`` directory."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def background_path() -> Path:
    return bundle_root() / BACKGROUND_RELATIVE


def model_path() -> Path:
    return bundle_root() / MODEL_RELATIVE


def find_texconv() -> Optional[Path]:
    """Find the bundled converter first, then a developer installation."""
    candidates = (
        bundle_root() / "texconv.exe",
        Path(__file__).resolve().parent / "vendor/directxtex/texconv.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    found = shutil.which("texconv.exe") or shutil.which("texconv")
    return Path(found) if found else None


def load_photo(path: Path) -> Image.Image:
    """Load a user image with phone-camera orientation applied."""
    with Image.open(path) as opened:
        result = ImageOps.exif_transpose(opened).convert("RGBA")
    # A phone's 48-megapixel original adds memory and latency without adding
    # detail to a 512 px game texture. 2048 still leaves ample room to zoom.
    result.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
    return result


def has_useful_alpha(image: Image.Image) -> bool:
    """True for a transparent cutout, false for an ordinary opaque photo."""
    alpha = image.getchannel("A")
    lo, _hi = alpha.getextrema()
    return lo < 250


def remove_background(image: Image.Image, model: Optional[Path] = None) -> Image.Image:
    """Return an RGBA foreground using the bundled lightweight U-2-Net.

    ONNX Runtime is imported here so the tracker executable never loads it;
    only the Career Helper does so after a user chooses an opaque photo.
    """
    os.environ.setdefault("ORT_DISABLE_TELEMETRY", "1")
    import onnxruntime as ort

    source = image.convert("RGB")
    small = source.resize((320, 320), Image.Resampling.LANCZOS)
    data = np.asarray(small, dtype=np.float32) / 255.0
    data = (data - np.asarray((0.485, 0.456, 0.406), dtype=np.float32))
    data /= np.asarray((0.229, 0.224, 0.225), dtype=np.float32)
    tensor = np.transpose(data, (2, 0, 1))[None, ...]

    network = Path(model) if model else model_path()
    if not network.is_file():
        raise FileNotFoundError(network)
    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    session = ort.InferenceSession(
        str(network), sess_options=options, providers=["CPUExecutionProvider"]
    )
    output = session.run(None, {session.get_inputs()[0].name: tensor})[0]
    prediction = np.squeeze(output[:, 0, :, :])
    low, high = float(prediction.min()), float(prediction.max())
    if high <= low:
        raise ValueError("the background-removal model returned an empty mask")
    prediction = (prediction - low) / (high - low)
    mask = Image.fromarray((prediction * 255).astype(np.uint8), "L")
    mask = mask.resize(source.size, Image.Resampling.LANCZOS)
    result = source.convert("RGBA")
    result.putalpha(mask)
    return result


def clean_alpha(image: Image.Image, cleanup: float = 0) -> Image.Image:
    """Contract the foreground mask by a visible number of output pixels."""
    pixels = max(0, min(12, round(float(cleanup))))
    if not pixels:
        return image
    alpha = image.getchannel("A")
    # MinFilter erodes the light (foreground) area. Doing this after the
    # portrait has been scaled makes one slider unit one pixel in the final
    # 512x512 texture; the old opacity remap changed a hard U-2-Net mask by
    # only a few RGB levels and was effectively invisible.
    alpha = alpha.filter(ImageFilter.MinFilter(pixels * 2 + 1))
    alpha = alpha.point(lambda value: 0 if value < 8 else value)
    alpha = alpha.filter(ImageFilter.GaussianBlur(0.45))
    result = image.copy()
    result.putalpha(alpha)
    return result


def apply_sepia(image: Image.Image, strength: float = 1.0) -> Image.Image:
    """Blend an RGBA image with a sepia-toned version, preserving alpha."""
    amount = max(0.0, min(1.0, float(strength)))
    source = image.convert("RGBA")
    if amount == 0:
        return source

    rgb = np.asarray(source.convert("RGB"), dtype=np.float32)
    # The standard sepia matrix retains more tonal detail than tinting a
    # grayscale image. Clipping before conversion avoids uint8 wraparound.
    matrix = np.asarray(
        ((0.393, 0.769, 0.189),
         (0.349, 0.686, 0.168),
         (0.272, 0.534, 0.131)),
        dtype=np.float32,
    )
    sepia_rgb = np.clip(rgb @ matrix.T, 0, 255)
    blended = np.clip(rgb + (sepia_rgb - rgb) * amount, 0, 255).astype(np.uint8)
    result = Image.fromarray(blended, "RGB").convert("RGBA")
    result.putalpha(source.getchannel("A"))
    return result


def adjust_tone(
    image: Image.Image,
    exposure: float = 0,
    contrast: float = 0,
    saturation: float = 0,
) -> Image.Image:
    """Apply photographic tone controls while preserving transparency.

    Exposure is measured in stops (EV); contrast and saturation are signed
    percentages whose neutral value is zero.
    """
    source = image.convert("RGBA")
    alpha = source.getchannel("A")
    rgb = source.convert("RGB")
    ev = max(-2.0, min(2.0, float(exposure)))
    contrast_pct = max(-100.0, min(100.0, float(contrast)))
    saturation_pct = max(-100.0, min(100.0, float(saturation)))
    if ev:
        rgb = ImageEnhance.Brightness(rgb).enhance(2.0 ** ev)
    if contrast_pct:
        rgb = ImageEnhance.Contrast(rgb).enhance(1.0 + contrast_pct / 100.0)
    if saturation_pct:
        rgb = ImageEnhance.Color(rgb).enhance(1.0 + saturation_pct / 100.0)
    result = rgb.convert("RGBA")
    result.putalpha(alpha)
    return result


def compose_portrait(
    foreground: Image.Image,
    background: Image.Image,
    zoom: float = 1.0,
    center_x: float = PORTRAIT_SIZE / 2,
    center_y: float = PORTRAIT_SIZE / 2,
    cleanup: float = 0,
    exposure: float = 0,
    contrast: float = 0,
    saturation: float = 0,
    sepia_strength: float = 0,
) -> Image.Image:
    """Composite the positioned foreground onto the game's 512 px backdrop."""
    bg = ImageOps.fit(
        background.convert("RGB"),
        (PORTRAIT_SIZE, PORTRAIT_SIZE),
        method=Image.Resampling.LANCZOS,
    ).convert("RGBA")
    fg = foreground.convert("RGBA")
    base = max(PORTRAIT_SIZE / fg.width, PORTRAIT_SIZE / fg.height)
    scale = max(0.05, float(zoom)) * base
    size = (max(1, round(fg.width * scale)), max(1, round(fg.height * scale)))
    fg = fg.resize(size, Image.Resampling.LANCZOS)
    fg = clean_alpha(fg, cleanup)
    fg = adjust_tone(fg, exposure, contrast, saturation)
    fg = apply_sepia(fg, sepia_strength)
    left = round(float(center_x) - fg.width / 2)
    top = round(float(center_y) - fg.height / 2)
    layer = Image.new("RGBA", bg.size, (0, 0, 0, 0))
    layer.alpha_composite(fg, (left, top))
    return Image.alpha_composite(bg, layer).convert("RGB")


def validate_dds(path: Path) -> Dict[str, int]:
    """Validate the exact texture contract known to render in the game."""
    raw = Path(path).read_bytes()
    if len(raw) < 148 or raw[:4] != b"DDS ":
        raise ValueError("texconv did not create a DDS file")
    height = struct.unpack_from("<I", raw, 12)[0]
    width = struct.unpack_from("<I", raw, 16)[0]
    mipmaps = struct.unpack_from("<I", raw, 28)[0]
    fourcc = raw[84:88]
    dxgi_format = struct.unpack_from("<I", raw, 128)[0] if fourcc == b"DX10" else -1
    if (width, height, mipmaps, fourcc, dxgi_format) != (
        PORTRAIT_SIZE, PORTRAIT_SIZE, 3, b"DX10", 98
    ):
        raise ValueError(
            f"unexpected DDS: {width}x{height}, {mipmaps} mips, "
            f"fourCC={fourcc!r}, DXGI={dxgi_format}"
        )
    return {"width": width, "height": height, "mipmaps": mipmaps,
            "dxgi_format": dxgi_format, "bytes": len(raw)}


def convert_to_dds(image: Image.Image, destination: Path,
                   texconv: Optional[Path] = None) -> Path:
    """Encode a portrait as 512x512 BC7_UNORM with three mip levels."""
    converter = Path(texconv) if texconv else find_texconv()
    if converter is None or not converter.is_file():
        raise FileNotFoundError("texconv.exe")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="il2k-portrait-") as raw_tmp:
        work = Path(raw_tmp)
        source = work / "portrait.png"
        image.convert("RGB").save(source, format="PNG")
        command = [
            str(converter), "-nologo", "-y", "-f", "BC7_UNORM",
            "-w", str(PORTRAIT_SIZE), "-h", str(PORTRAIT_SIZE),
            "-m", "3", "-if", "CUBIC", "-o", str(work), str(source),
        ]
        completed = subprocess.run(
            command, capture_output=True, text=True, check=False,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
        made = work / "portrait.dds"
        if completed.returncode or not made.is_file():
            detail = (completed.stderr or completed.stdout or "texconv failed").strip()
            raise RuntimeError(detail)
        validate_dds(made)
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        shutil.copyfile(made, temporary)
        temporary.replace(destination)
    return destination


def career_key(career_path: Path) -> str:
    try:
        identity = str(Path(career_path).resolve()).casefold()
    except OSError:
        identity = str(career_path).casefold()
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]


def custom_avatar_path(career_path: Path, pilot_id: int) -> str:
    # 13 characters. The game copies avatarPath into a 16-byte buffer and aborts
    # on anything longer (see korea_service_record/portraitfix.py) - 2.2.2 used
    # custom/<16 hex>-<id>, 26 characters, and crashed every new day.
    return short_avatar_path(career_path, pilot_id)


def portrait_destination(game_dir: Path, avatar_path: str) -> Path:
    safe = avatar_path.replace("\\", "/").strip("/")
    if not re.fullmatch(r"(custom|cp)/[A-Za-z0-9_-]+", safe):
        raise ValueError("unsafe custom portrait path")
    return Path(game_dir) / "data/NSData/assets/pilotphotos" / f"{safe}.dds"


def state_path(career_path: Path) -> Path:
    return default_cache_dir().parent / STATE_FOLDER / f"{career_key(career_path)}.json"


def load_state(career_path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(state_path(career_path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def save_state(career_path: Path, data: Dict[str, Any]) -> Path:
    target = state_path(career_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    temporary.replace(target)
    return target


def clear_state(career_path: Path) -> None:
    try:
        state_path(career_path).unlink()
    except FileNotFoundError:
        pass
