# U.S. Navy full-size medal rack layout (Korean War, 1950–1953)

Supplied by the project owner 2026-09-22. Governs the **full-size medal
rack** on the tunic in full dress for the Navy and Marine coats. It does not
govern service ribbons or miniatures; device sizing is in
`docs/DEVICE_RULES.md`. Implemented in `medals.navy_rows`, the
`[data-coat="usnavy"|"usmc"]` blocks of `detail.css`, and `medalRows()` in
`app.js`.

Viewer convention: the wearer faces the camera, so the wearer's left breast
is the viewer's right. **Inboard** (toward the coat's centre line) is the
viewer's left. The highest-precedence medal of each row is inboard.

## What is in the rack
Sort by Navy precedence, then fill the **top row first**. Excluded, and not
counted: the **Medal of Honor** (worn at the neck) and **ribbon-only unit
awards** (right breast). They do not consume a position or change the rows.

## Rows
| medals | rows | medals | rows | medals | rows |
|---|---|---|---|---|---|
| 1–5 | one row | 11 | 3/4/4 | 19 | 4/5/5/5 |
| 6 | 3/3 | 12 | 4/4/4 | 20 | 5/5/5/5 |
| 7 | 3/4 | 13 | 3/5/5 | 21 | 2/4/5/5/5 |
| 8 | 4/4 | 14 | 4/5/5 | 22 | 3/4/5/5/5 |
| 9 | 4/5 | 15 | 5/5/5 | 23 | 3/5/5/5/5 |
| 10 | 5/5 | 16 | 4/4/4/4 | 24 | 4/5/5/5/5 |
|  |  | 17 | 3/4/5/5 | 25 | 5/5/5/5/5 |
|  |  | 18 | 3/5/5/5 |  |  |

Rows read top to bottom; within a row, inboard (viewer's left) to outboard.

## Width and overlap
A row of three, unoverlapped, defines the rack width `R = 3M` (`M` = medal
width). Rows of four or five are fitted **by overlapping, never by
shrinking**: `centreSpacing = (R − M) / (N − 1)`, so the pull is `M/3` for
four and `M/2` for five, and every row ends up `R` wide. The inboard medal
laps **over** its outboard neighbour, so the senior medal is never hidden.
Each row is centred on the same rack centre line.

## Vertical
The **lowest row is the anchor**: its holding bar is centred over the
wearer's left breast pocket and sits about **1/4 inch above the pocket's
top edge**, horizontal. Build upward from it — never position by the top
row or by the medals' bottom edges. The row step is
`medallionHeight + lowerRibbonVisible`, small enough that each row's
medallions cover most of the suspension ribbon of the row below while every
pendant stays clearly visible and no air gap opens. Within a row the medal
bottoms dress in a line.

## Naval aviator wings
Centred above the completed rack (`wingsCentreX = rackCentreX`), with a
small clear space above the top row. Position them only once the rack is
laid out.

## Never
Shorten suspension ribbons, squash or crop medal art, change pendant or
device scale, make a four- or five-medal row narrower than a three-medal
row, or rescale medals because another row was needed. Solve space with
horizontal overlap, vertical overlap and the row table.

## Ribbon rack (service dress and the record panel)

**Three to a row, never more**, whatever the count, with the short row on
top and centred; fill top-first in precedence order:

```
1  [1]          4     [1]        7     [1]        8    [1][2]
2  [1][2]          [2][3][4]        [2][3][4]       [3][4][5]
3  [1][2][3]     5  [1][2]          [5][6][7]       [6][7][8]
                   [3][4][5]
                 6  [1][2][3]
                   [4][5][6]
```

Unlike the medal rack, the **Medal of Honor's ribbon is worn on the rack**;
only the medal itself moves to the neck.

## Marine Blue Dress "A" — where the rack hangs

On the male Marine Blue Dress coat the full-size rack is **not** set by the
pocket. The regulation centres the medals over the left breast pocket with
the **upper edge of the holding bar on the horizontal line midway between
the first and second coat buttons**. With three rows the **middle** row
takes that line, the lower row falling below it and the senior row above.
On the tracker's photograph the buttons sit at 23.5 % and 46.5 % of the
coat, so the line is 35.0 %; `anchorRack()` in `app.js` measures the
laid-out rack after its images load and shifts it onto the line, which
keeps it right for any number of rows.

When large medals are worn, **all** unit citations and other ribbons with no
medal authorised are worn **centred over the right breast pocket** (centre
24.0 % on this photograph — the coat is not symmetric), an **eighth of an
inch** above its flap. This is the Marine rule; the Navy's 1951 rule instead
puts only the senior ribbon-only unit award on the right breast.

The Marine **ribbon** rack is **three per row** until three would need more
than **six rows** — from nineteen ribbons up it goes to four, which
regulations authorise for a large rack. The Navy never widens; the Air
Force widens sooner, past five rows. The thresholds are
`ribbons.MAX_ROWS_AT_THREE`, one per service.
