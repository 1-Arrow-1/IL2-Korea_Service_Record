"""Fit the supplied Army of Occupation Medal art to the tracker's formats.

    python tools/make_occupation_art.py <ribbon.png> <medal.png>

Writes

    korea_service_record/static/images/ribbons/601077.png   440x120 bar
    korea_service_record/static/images/medals/601077.png    224x474 drape + pendant

The ribbon is scaled to the 1 3/8 x 3/8 inch bar and made fully opaque.
The medal arrives on a white ground: the ground is removed by flood fill
(the drape's white edge stripes are walled off from it by their selvedge
line), the gaps inside the suspension ring with it, and the drop shadow
under the drape becomes translucent. Then, like every drawn US medal here,
the drape is fitted to the full 224 px width and made to end at row 247,
and the pendant is scaled to fill what is left, centred under it. The drape's maroon is lifted
to the ribbon bar's scarlet so the two match.
"""

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
IMAGES = ROOT / "korea_service_record" / "static" / "images"
TARGET = "601077"


def _label(mask: np.ndarray):
    """4-connected components of a boolean mask: (labels, count)."""
    from collections import deque
    h, w = mask.shape
    lab = np.zeros((h, w), np.int32)
    n = 0
    for y0, x0 in zip(*np.nonzero(mask)):
        if lab[y0, x0]:
            continue
        n += 1
        lab[y0, x0] = n
        q = deque([(y0, x0)])
        while q:
            y, x = q.popleft()
            for yy, xx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= yy < h and 0 <= xx < w and mask[yy, xx] and not lab[yy, xx]:
                    lab[yy, xx] = n
                    q.append((yy, xx))
    return lab, n


def _dilate(mask: np.ndarray, px: int) -> np.ndarray:
    img = Image.fromarray(mask.astype(np.uint8) * 255)
    return np.asarray(img.filter(ImageFilter.MaxFilter(2 * px + 1))) > 0


def make_ribbon(path: Path) -> Image.Image:
    img = Image.open(path).convert("RGB").resize((440, 120), Image.LANCZOS)
    return img.convert("RGBA")


def cut_out(path: Path) -> np.ndarray:
    a = np.asarray(Image.open(path).convert("RGB")).astype(float)
    mn=a.min(2)
    white=mn>=252
    lab,n=_label(white)
    keep={lab[0,0]}
    for i in range(1,n+1):
      ys,xs=np.where(lab==i)
      if ys.min()>440 and len(ys)>3: keep.add(i)
    bg=np.isin(lab,list(keep))
    # Gaps inside the ring are background too; specks are dropped by keeping
    # only the largest foreground piece. Coordinates are the supplied art's.
    # drop specks: keep only the largest foreground component
    fl,fn=_label(~bg)
    sizes=np.bincount(fl.ravel())[1:]
    fg=fl==(1+int(np.argmax(sizes)))
    bg=~fg
    sat=a.max(2)-a.min(2); lum=a.mean(2)
    yy=np.arange(a.shape[0])[:,None]*np.ones(a.shape[1])[None,:]
    near=_dilate(bg,8)&~bg
    soft=((near&(yy>=444))|((yy>=444)&(yy<=456)))&(sat<18)&(lum>110)
    alpha=np.where(bg,0.0,1.0)
    alpha[soft]=np.clip((255-lum[soft])/255*1.4,0,1)
    rgb=a.copy()
    al=np.maximum(alpha[soft,None],1e-3)
    rgb[soft]=np.clip((a[soft]-255*(1-al))/al,0,255)
    return np.dstack([rgb, alpha * 255])


# The supplied drape's red is a dark maroon (about 98,4,4); the ribbon bar,
# like the regulation's scarlet, is about 220,4,4. Lift the drape's red to
# match, keeping its weave and shading - a gain on the red channel only.
RED_GAIN = 2.1
DRAPE_LAST_ROW = 456


def brighten_red(src: np.ndarray) -> np.ndarray:
    out = src.copy()
    r, g, b = out[..., 0], out[..., 1], out[..., 2]
    y = np.arange(out.shape[0])[:, None]
    red = (y <= DRAPE_LAST_ROW) & (r > 30) & (g < 0.35 * r) & (b < 0.35 * r)
    out[..., 0] = np.where(red, np.clip(r * RED_GAIN, 0, 255), r)
    return out


def fit(src: np.ndarray) -> Image.Image:
    H, W = 474, 224
    DRAPE_TOP, DRAPE_BOTTOM, CUT = 19, 444, 456        # cloth, its last row, end of its shadow
    DX0, DX1 = 31, 466                                 # drape selvedges
    r, g, b, a = (src[..., i] for i in range(4))
    bronze = (r - b > 40) & (g > 60)
    y = np.arange(src.shape[0])[:, None]

    drape = src.copy()
    drape[(y > CUT) | ((y > 400) & bronze), 3] = 0
    pend = src.copy()
    pend[((y < DRAPE_BOTTOM + 2) & ~bronze) | (y <= 400), 3] = 0

    f1 = W / (DX1 - DX0)
    cols = np.where((pend[..., 3] > 0).any(0))[0]
    px0, px1 = cols.min(), cols.max() + 1
    rows = np.where((pend[..., 3] > 0).any(1))[0]
    py0, py1 = rows.min(), rows.max() + 1
    # The mod's other drapes end at row 247; matching it lines the pendants up
    # across a row of medals, at the cost of a slightly longer drop.
    DRAPE_ROWS = 247
    fy = DRAPE_ROWS / (DRAPE_BOTTOM - DRAPE_TOP)
    f2 = min(W / (px1 - px0), (H - 2 - DRAPE_ROWS) / (py1 - DRAPE_BOTTOM))

    def layer(arr, x0, y0, x1, y1, f, fv=None):
        im = Image.fromarray(arr[y0:y1, x0:x1].astype(np.uint8), "RGBA")
        return im.resize((max(1, round((x1 - x0) * f)), max(1, round((y1 - y0) * (fv or f)))), Image.LANCZOS)

    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dl = layer(drape, DX0, DRAPE_TOP, DX1, CUT + 1, f1, fy)
    anchor = DRAPE_ROWS           # drape bottom on the canvas
    pl = layer(pend, px0, py0, px1, py1, f2)
    centre_src = (DX0 + DX1) / 2
    px = round(W / 2 - (centre_src - px0) * f2)
    py = round(anchor - (DRAPE_BOTTOM - py0) * f2)
    canvas.alpha_composite(pl, (px, py))
    canvas.alpha_composite(dl, (0, 0))
    return canvas


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    ribbon = make_ribbon(Path(sys.argv[1]))
    medal = fit(brighten_red(cut_out(Path(sys.argv[2]))))
    assert ribbon.size == (440, 120) and medal.size == (224, 474)
    ribbon.save(IMAGES / "ribbons" / f"{TARGET}.png", optimize=True)
    medal.save(IMAGES / "medals" / f"{TARGET}.png", optimize=True)
    print("wrote ribbons/{0}.png and medals/{0}.png".format(TARGET))


if __name__ == "__main__":
    main()
