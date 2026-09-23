# U.S. Army / U.S. Air Force award display (Korean War, 1950–1953)

Supplied by the project owner 2026-09-22. Governs the USAF coat and the
record panel for Army/AAF-pattern awards. Navy and Marine geometry is in
`docs/NAVY_RACK.md`; device sizes in `docs/DEVICE_RULES.md`. **Never use
Navy layout rules for Army/USAF.**

Viewer convention: wearer's right = viewer's left. The highest-precedence
award of a row begins at the wearer's right, i.e. the viewer's left; rows
read top to bottom.

## Full-size medals
- **USAF: three to a row** is the normal arrangement — not the Navy's
  fixed table. A wider row is **overlapped, never scaled down**: the
  inboard/senior medal stays fully exposed and each medal laps the next
  toward outboard, to **at most about 50 %**.
- Army practice allows three or four to a row according to coat width,
  **without horizontal overlap**; the incomplete top row is centred.
- Rows overlap **vertically** so the upper medallions cover a substantial
  part of the ribbons below — but not so far that the lower medallions
  stop reading. No large vertical gaps; never crop suspension ribbons.
- Implemented as `medals.rows_for()`: three to a row, going to four
  (overlapped) only when three would stack higher than
  `MAX_MEDAL_ROWS_AT_THREE`.

## Service ribbons
- **Preferred three to a row, four allowed, never five.** Four suits a
  large rack that would otherwise be excessively tall or foul the lapel or
  the aeronautical badge. The incomplete top row is centred over the row
  beneath — a lone ribbon on top is normal when the count leaves one over.
  `ribbons.per_row_for()` widens once three would need more than five rows,
  i.e. from sixteen ribbons; the per-service limits are
  `ribbons.MAX_ROWS_AT_THREE` (the Marines hold out to six rows, the Navy
  never widens).
- Period Army practice left about **1/8 inch between rows**; keep it small,
  or compress slightly, never a large gap.

## Unit awards
Army/USAF unit emblems are **not mixed into the personal rack**. Personal
awards on the wearer's left (viewer's right); unit citations — Distinguished
/ Presidential Unit Citation and authorised foreign ones — on the wearer's
right (viewer's left). This is the opposite of the naval service-dress rule,
where unit ribbons join the rack.

## Devices
Oak leaf clusters for repeat awards: bronze one further award, silver for
five bronze; **13/32 in (29.55 % of ribbon width) on a medal, 5/16 in
(22.73 %) on a bar**. Stems point to the wearer's right — the viewer's left.
One to four clusters sit in a centred row on a bar; on a medal, a fourth
cluster goes **centred above** a row of three, never four across.

Campaign/service stars are **3/16 in (13.64 %)**, bronze and silver the same
size, and **point UP** — the opposite of the Korean War Navy/USMC star.

The Bronze Star's Combat **V** is 1/4 in high and sits to the wearer's right
of any clusters (viewer's left). During Korea the V belonged to the Bronze
Star only — not the Air Medal or Commendation Medal, which came later.

The Medal of Honor is a neck decoration: out of the breast count, rendered
at the collar.

## When it does not fit
In this order: change the three-vs-four row arrangement, then the permitted
medal overlap, then the vertical row overlap, then move the whole rack.
**Never** shrink clusters or stars, crop suspension ribbons or squeeze
pendants — device sizes are historical constants.

## Full dress (large medals)
The wearer's left breast carries the **medal rack only**, with the pilot
wings centred above it and the Medal of Honor at the collar. **No unit-ribbon
strip is worn beside large medals** — having moved unit citations into the
ribbon group, the Air Force wears nothing on the opposite breast. The
citations still appear in the ribbon rack in service dress, in the
precedence position below.

## Ribbon rack order
Personal decorations in period precedence (Medal of Honor, DSC, DSM, Silver
Star, Legion of Merit, DFC, Bronze Star, Air Medal, Commendation, Purple
Heart), then **unit citations** — principally the Distinguished Unit
Citation — then service and campaign medals (National Defense Service Medal,
Korean Service Medal and the like), then authorised **foreign awards** after
the U.S. ones. Verified against `ribbons.PRECEDENCE` 2026-09-22.
