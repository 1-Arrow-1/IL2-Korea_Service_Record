"""
Generate the four national flags the Korea careers can carry.

Drawn rather than sourced: a photograph would sit badly against the paper
theme, and these have to read at about 40px wide inside a career tile. The
palette is pulled toward the UI's sepia so the flag looks like it was printed
on the same document, and every flag shares one "worn" filter — a turbulence
displacement that frays the edges plus a mottled overlay for fading — so the
set looks like one artefact rather than four clip-art files.
"""
import math
from pathlib import Path

OUT = (Path(__file__).resolve().parent.parent
       / "korea_service_record" / "static" / "images" / "flags")

W, H = 60.0, 40.0

# Muted against the paper: full-saturation flag colours glare next to sepia.
RED = "#a5382f"
DEEP_RED = "#9c3129"
WHITE = "#f0e7d6"
NAVY = "#2f4364"
GOLD = "#dcb548"
DPRK_BLUE = "#33527d"


def defs(uid: str) -> str:
    """The shared wear: frayed edge, blotchy fading, a soft vertical fold."""
    return f"""  <defs>
    <filter id="fray{uid}" x="-8%" y="-8%" width="116%" height="116%">
      <feTurbulence type="fractalNoise" baseFrequency="0.09 0.16"
                    numOctaves="4" seed="{sum(map(ord, uid))}" result="n"/>
      <feDisplacementMap in="SourceGraphic" in2="n" scale="1.7"
                         xChannelSelector="R" yChannelSelector="G"/>
    </filter>
    <filter id="stain{uid}" x="0%" y="0%" width="100%" height="100%">
      <feTurbulence type="fractalNoise" baseFrequency="0.035"
                    numOctaves="5" seed="{sum(map(ord, uid)) + 7}"/>
      <feColorMatrix type="saturate" values="0"/>
    </filter>
    <linearGradient id="fold{uid}" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%"   stop-color="#000" stop-opacity="0.16"/>
      <stop offset="14%"  stop-color="#000" stop-opacity="0"/>
      <stop offset="46%"  stop-color="#000" stop-opacity="0.10"/>
      <stop offset="62%"  stop-color="#fff" stop-opacity="0.10"/>
      <stop offset="88%"  stop-color="#000" stop-opacity="0"/>
      <stop offset="100%" stop-color="#000" stop-opacity="0.18"/>
    </linearGradient>
    <clipPath id="clip{uid}"><rect width="{W}" height="{H}"/></clipPath>
  </defs>"""


def wrap(uid: str, title: str, body: str) -> str:
    """Flag body under the wear layers, all clipped to the flag rectangle."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:g} {H:g}"
     role="img" aria-label="{title}">
  <title>{title}</title>
{defs(uid)}
  <g filter="url(#fray{uid})">
{body}
  </g>
  <g clip-path="url(#clip{uid})">
    <rect width="{W:g}" height="{H:g}" filter="url(#stain{uid})"
          opacity="0.16" style="mix-blend-mode:multiply"/>
    <rect width="{W:g}" height="{H:g}" fill="url(#fold{uid})"/>
  </g>
</svg>
"""


def star(cx: float, cy: float, r: float, fill: str, rot: float = -90.0) -> str:
    """A five-pointed star, point-up by default."""
    pts = []
    for i in range(10):
        radius = r if i % 2 == 0 else r * 0.382
        a = math.radians(rot + i * 36.0)
        pts.append(f"{cx + radius * math.cos(a):.2f},{cy + radius * math.sin(a):.2f}")
    return f'    <polygon points="{" ".join(pts)}" fill="{fill}"/>'


# --------------------------------------------------------------------- US --
def united_states() -> str:
    stripe = H / 13.0
    body = [f'    <rect width="{W:g}" height="{H:g}" fill="{WHITE}"/>']
    for i in range(0, 13, 2):
        body.append(f'    <rect y="{i * stripe:.3f}" width="{W:g}" '
                    f'height="{stripe:.3f}" fill="{RED}"/>')
    canton_w, canton_h = W * 0.4, stripe * 7
    body.append(f'    <rect width="{canton_w:.3f}" height="{canton_h:.3f}" '
                f'fill="{NAVY}"/>')
    # 50 stars: nine rows alternating six and five.
    for row in range(9):
        count = 6 if row % 2 == 0 else 5
        gap_x = canton_w / 6.0
        y = canton_h * (row + 1) / 10.0
        for col in range(count):
            x = gap_x * (col + (0.5 if row % 2 == 0 else 1.0))
            body.append(star(x, y, 0.78, WHITE))
    return wrap("us", "United States", "\n".join(body))


# ------------------------------------------------------------------- USSR --
def soviet_union() -> str:
    body = [f'    <rect width="{W:g}" height="{H:g}" fill="{DEEP_RED}"/>',
            star(19.4, 4.4, 2.7, GOLD)]
    # Hammer and sickle drawn in a 100-unit box and scaled into the canton.
    # The sickle is the crescent between two arcs, closed by a stubby handle at
    # the lower left. The hammer lies across the crescent's opening on the
    # diagonal, head at the upper right — deliberately short of the blade, since
    # a hammer long enough to touch it merges into one gold blob at tile size.
    emblem = (
        '    <g transform="translate(3.6,5.6) scale(0.132)" fill="COLOUR">\n'
        '      <path d="M10 92 A 66 66 0 0 1 90 12 L 83 31'
        ' A 48 48 0 0 0 28 92 Z"/>\n'
        '      <rect x="3" y="85" width="27" height="13" rx="3"/>\n'
        '      <g transform="rotate(-45 20 90)">\n'
        '        <rect x="20" y="84" width="48" height="13" rx="2"/>\n'
        '        <rect x="62" y="70" width="20" height="40" rx="3"/>\n'
        '      </g>\n'
        '    </g>').replace("COLOUR", GOLD)
    body.append(emblem)
    return wrap("su", "Soviet Union", "\n".join(body))


# ------------------------------------------------------------------ China --
def china() -> str:
    body = [f'    <rect width="{W:g}" height="{H:g}" fill="{DEEP_RED}"/>',
            star(10.0, 10.0, 5.4, GOLD)]
    # Four small stars on an arc, each turned to face the large one.
    for dx, dy in ((7.6, -6.2), (10.4, -2.8), (10.4, 1.6), (7.6, 4.8)):
        cx, cy = 10.0 + dx, 10.0 + dy
        angle = math.degrees(math.atan2(10.0 - cy, 10.0 - cx))
        body.append(star(cx, cy, 1.75, GOLD, rot=angle + 90))
    return wrap("cn", "People's Republic of China", "\n".join(body))


# ------------------------------------------------------------ North Korea --
def north_korea() -> str:
    band = H / 12.0          # 1 : 1 : 8 : 1 : 1 on a 12-part height
    body = [
        f'    <rect width="{W:g}" height="{H:g}" fill="{DPRK_BLUE}"/>',
        f'    <rect y="{band * 1.6:.3f}" width="{W:g}" '
        f'height="{H - band * 3.2:.3f}" fill="{WHITE}"/>',
        f'    <rect y="{band * 2.4:.3f}" width="{W:g}" '
        f'height="{H - band * 4.8:.3f}" fill="{DEEP_RED}"/>',
        f'    <circle cx="{W * 0.31:.2f}" cy="{H / 2:.2f}" r="6.4" fill="{WHITE}"/>',
        star(W * 0.31, H / 2, 4.6, DEEP_RED),
    ]
    return wrap("kp", "Democratic People's Republic of Korea", "\n".join(body))


OUT.mkdir(parents=True, exist_ok=True)
for name, svg in (("us", united_states()), ("ussr", soviet_union()),
                  ("china", china()), ("dprk", north_korea())):
    path = OUT / f"{name}.svg"
    path.write_text(svg, encoding="utf-8", newline="\n")
    print(f"{path.name}: {len(svg)} bytes")
