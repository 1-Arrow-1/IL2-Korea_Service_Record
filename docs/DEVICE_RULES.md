# Korean War U.S. award device placement and scaling rules

Target period 1950–1953. Authoritative for every ribbon bar and full-size
medal the tracker draws for the U.S. Army/USAF and Navy/USMC. Supplied by
the project owner 2026-09-21; `ribbons.py` and `medals.py` must follow it.
Do NOT substitute modern Navy star orientation.

Viewer left/right = looking at the medal. Wearer's right = viewer's LEFT.

## 1. Master ribbon width
W = nominal full ribbon width (1 3/8" = 1.375"). On a tapered suspension
ribbon use the upper rectangular part. devicePx = W * (deviceInches / 1.375).

## 2. Army/USAF oak leaf clusters (OLC)
Bronze = one further award; silver = five bronze.
- Full-size medal: 13/32" = **29.55 % of W**. 1–3 in one centred row;
  **4 = three in a row with the fourth centred above the middle one**, never
  four across.
- Ribbon bar: 5/16" = **22.73 % of W**. 1–4 in one centred row.
- Leaves horizontal, **stem to wearer's right = viewer's left**.

## 3. Army/USAF service/campaign stars
Bronze and silver both 3/16" = **13.64 % of W**, on bar and medal.
**One point UP.** Compact centred row; silver = five bronze.

## 4. Navy/USMC gold/silver repeat-award stars
Gold = one further award; silver = five gold. 5/16" = **22.73 % of W** on
both the medal and the bar. **Point DOWN** (rotate an upright star 180°).
1–4 in ONE centred row; never 3+1.

## 5. Navy/USMC service/campaign stars
Bronze and silver both **3/16" = 13.64 % of W** — the silver stands for five
bronze and is drawn the same size beside them. (Corrected by the owner
2026-09-22: this section first gave the naval silver campaign star 5/16",
and beside 3/16" bronze stars it read wrong. 5/16" belongs to the
repeat-award stars of §4, not to campaign stars.) All **point DOWN**. Silver
at the centre; first extra bronze to viewer's LEFT, second to viewer's
RIGHT, then outward symmetrically.

## 6. Navy silver + gold repeat stars
Same layout as §5: silver centred, first gold viewer's left, second right.
All point down.

## 7. Digital spacing
gap ≈ 0.015 W – 0.025 W, default **0.02 W** (9 px at W = 440). A rendering
standard, not a historical measurement. Centre the device group unless a
required centre device (silver Navy star) fixes the layout.

## 8. Size table (% of W)
| device | Army/USAF | Navy/USMC |
|---|---|---|
| OLC on medal | 29.55 | – |
| OLC on bar | 22.73 | – |
| bronze service star | 13.64 | 13.64 |
| silver service star | 13.64 | 13.64 |
| gold repeat star | – | 22.73 |
| silver repeat star | – | 22.73 |

## 9. Orientation
Army/USAF: OLC stem to viewer's left; service stars point UP.
Navy/USMC (Korean War): every star — gold, silver, bronze — points DOWN.

## 10. Implementation rule
Never size by eye. Measure W, pick the device type, apply the ratio, apply
the orientation, build the group, centre it. **Do not shrink devices to make
several fit** — if three medal OLCs or four Navy stars do not fit, the asset
is oversized or W was measured wrongly. One master asset per physical device
size; derive every instance from W.

## Shared awards, different devices

A medal both services wear — the Korean Service Medal above all — carries
**point-up** Army/USAF service stars on an airman and **point-down** naval
ones on a sailor or Marine, and the naval silver star is 5/16 in where the
Army's is 3/16. The award id is the same, so the picture is asked for by
service: the rack payload carries `svc`, the browser appends `&svc=navy`
to `/api/ribbon/<id>` and `/api/medal/<id>`, and the renderers keep a
separate `navy/` cache. `ribbons.NAVAL_STAR` maps the device names.
