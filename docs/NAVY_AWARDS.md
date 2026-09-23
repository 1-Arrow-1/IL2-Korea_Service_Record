# Navy and USMC awards — 2026-09-20

The same 602 IDs serve Navy (`Country=602`) and USMC (`Country=603`), as
in the existing configuration. No duplicate 603 definitions were added.
Source artwork: `C:\Users\bleih\Pictures\Navy`, excluding `star_gold.png`.
The missing plain NUC ribbon comes from `static/images/ribbons/602034.png`.
Supplied art is used at native size, with atlas alpha cleanup and BC7 encoding.

## IDs and atlas coordinates

Coordinates are `x,y,width,height` in `awards.xaml`. A star count denotes the
repeat variant pictured in the supplied artwork, not an additional medal.

| ID | Award / variant | Atlas | SourceRect |
|---|---|---|---|
| 602027 | Navy Medal of Honor, existing ID | 6xx3 | 4,804,409,470 |
| 602031 | Navy Distinguished Service Medal | 6xx3 | 452,580,244,484 |
| 602032 | Navy Commendation Medal | 6xx3 | 1060,580,173,357 |
| 602033 | Navy Presidential Unit Citation | 6xx3 | 1412,4,440,120 |
| 602034 | Navy Unit Commendation | 6xx3 | 4,228,440,120 |
| 602035 | Commendation, 1 star | 6xx3 | 1316,580,173,357 |
| 602036 | Commendation, 2 stars | 6xx3 | 708,644,173,357 |
| 602037 | Commendation, 3 stars | 6xx3 | 1572,772,173,357 |
| 602038 | Medal of Honor, 1 star | 6xx3 | 964,1092,409,470 |
| 602039 | Presidential Unit Citation, 1 star | 6xx3 | 4,1284,440,120 |
| 602040 | Presidential Unit Citation, 2 stars | 6xx3 | 4,1412,440,120 |
| 602041 | Presidential Unit Citation, 3 stars | 6xx3 | 452,1508,440,120 |
| 602042 | Silver Star Medal, 3 stars | 6xx3 | 1828,772,204,396 |
| 602043 | Silver Star Medal, 4 stars | 6xx3 | 452,1092,204,396 |
| 602044 | Unit Commendation, 1 star | 6xx2 | 932,1860,448,122 |
| 602045 | Unit Commendation, 2 stars | 6xx3 | 932,4,448,122 |
| 602046 | Unit Commendation, 3 stars | 6xx3 | 1412,1284,448,122 |
| 602047 | Unit Commendation, 4 stars | 6xx3 | 1412,1444,448,122 |
| 602048 | Bronze Star Medal with V | 6xx3 | 900,1572,212,403 |
| 602049 / 602051 | Bronze Star with V, 1 gold star | 6xx3 | 4,1540,213,404 |
| 602050 / 602052 | Bronze Star with V, 2 gold stars | 6xx3 | 228,1540,211,404 |

Navy Cross remains 602021, atlas 6xx2, `1120,904,218,437`.
Both atlases remain 2048x2048 BC7_UNORM/DX10 with four mip levels and
5,570,708 bytes. Only compressed blocks in previously free, 32-aligned cells
were replaced; every existing crop is unchanged at every mip level.

On 2026-09-21 the complete Navy Commendation series was replaced from the four
current 240x450 `Navy_commendation*.png` files. The visible artwork is trimmed
and proportionally fitted into 173x357 crops, matching the USAF Commendation
series. The original top-left positions and reserved cells are retained, so
no unrelated atlas artwork moved.

## Award criteria

These are gameplay proxies, not historical kill or sortie quotas. Engine
inputs and their limitations are documented from decompilation and career
checks in HANDOFF.md. The new naval thresholds have not been flown in game.

| Award | Criteria | Derivation |
|---|---|---|
| Distinguished Service Medal | Commander, rank >= 6, career >= 180 days | Matches USAF 601052 |
| Commendation: base / 1 / 2 / 3 stars | >= 15 / 45 / 75 / 110 completed sorties, `RND<200` | Matches USAF 601054–601057 |
| Medal of Honor, repeat | >= 6 air kills in one sortie, or >= 5 while wounded | Matches existing Navy base and USAF repeat |
| Silver Star, 3 stars | 2 air kills with `RND<500`, or 3 with `RND<700` | Matches USAF 601050 |
| Silver Star, 4 stars | 2 air kills with `RND<400`, or 3 with `RND<600` | Matches USAF 601051 |
| PUC: base / 1 / 2 / 3 stars | Squadron efficiency >= 3; air totals >= 50 / 110 / 180 / 260 OR surface totals >= 600 / 1300 / 2100 / 3000 | Matches DUC ladder 601042/601044–601046 |
| NUC: base / 1 / 2 / 3 / 4 stars | Squadron efficiency >= 2 and successful operations >= 6 / 12 / 18 / 24 / 30 | Sustained operational success, distinct from the combat-output PUC |
| Bronze Star with V / 1 / 2 gold stars | 1 air kill with `RND<300`; 25 ground/building/sea targets with `RND<200`; or wounded, still scoring, with `RND<400`. Ordinary Bronze Star sortie thresholds can advance a V holder. | Adapts the USAF V-device gameplay rules to count naval targets and retain Navy gold-star devices |

Surface totals mean `GrObj+BldObj+SeaObj`. All unit awards have
`IsSquadron=1` and use squadron-level values; sortie counters and pilot rank
are zero in this evaluation path. NUC uses `OpSuccess`, the number of campaign
operations recorded as successfully ended for the squadron. `OpTotal` would
also include failed operations, but is not part of the award criterion.
Operations still underway do not count. The six-operation cadence gives each
additional NUC another distinct block of sustained successful operations.

The NUC and PUC can be granted on the same rollover if both cumulative sets of
criteria happen to mature together. The engine does not expose historical
citation periods or a per-award baseline, so it cannot prove that cumulative
statistics represent different acts or periods of service. Their criteria are
nevertheless distinct: NUC measures successful operations, PUC combat output.

Each repeat requires its preceding award to have been received, and retires
all lower variants through `AwardRemove`; the database history remains.
The DSM and Commendation also use their cumulative rules for `AwardByDef`,
matching their USAF counterparts. All other new awards use `RND<0` there.
`RND<200` is roughly 20% per evaluation, not once per career; `RND` is rerolled
on each read. The stock promotion option ends at rank 5, so the DSM is
normally reachable only with the extended promotion option, like USAF DSM.

Two existing defects were corrected as dependencies: 602020 now retires
602019 (formerly the mistyped 60219), and base Navy Cross 602021 now allows
USMC as well as Navy, matching its existing repeat awards. Other existing
Navy award probabilities and automatic-grant rules are unchanged.

The three visible Bronze Star V variants use five technical IDs. The game can
only test prior holdings through `RequiredAward`, and one definition cannot
apply different conditions to alternative prerequisites. IDs 602049/602051
therefore share the one-star tile and name, while 602050/602052 share the
two-star tile and name. These parallel routes merge merit-first and V-first
careers, retire all lower ordinary/V variants, and leave one visible medal.

## Text, historical basis and packaging

All added IDs have names and description files in `eng ger spa fra rus chs`.
Repeat descriptions redirect to their base awards, including stock 602018
and 602027. `tools/stage_release.py` explicitly lists all 102 new description
files; the installer's existing `6*.locale=*.txt` rule installs them.
The stock-promotion config is derived from the extended config after refresh.

The 1953 Navy and Marine Corps Awards Manual distinguishes personal
meritorious-service awards from unit awards. PUC and NUC are ribbon-only;
NUC recognizes a lower degree of combat distinction or outstanding noncombat
support. It prohibits both unit awards for the same service. See
[Part I](https://www.ibiblio.org/hyperwar/USN/ref/Awards/Awards-I.html) and
[Part II](https://www.ibiblio.org/hyperwar/USN/ref/Awards/Awards-II.html).
The Commendation description explains its period name, Commendation Ribbon
with Metal Pendant. Artwork is the user's supplied set; its star colours
and sizes are not being certified as the 1953 wear standard (the period
manual describes bronze 3/16-inch devices on the unit awards). The separate
ROK PUC correction remains intact: repeat ROK citations always look plain.

The 1953 manual identifies the bronze letter V as the Combat Distinguishing
Device for direct participation in combat operations, permits only one V per
ribbon, and places gold or silver repeat-award stars symmetrically around it.
The first gold star is to the wearer's right of the V and the second to the
left. The supplied artwork follows that layout.

The tracker now registers every Navy award ID through 602052 for both Navy
and Marine pilots. Unit awards join the service-dress ribbon rack and move
to the right breast in full dress; personal medals, Naval Aviator badge and
gold repeat-award stars are placed on the appropriate dress view. Navy and
Marine tunics each use their own rank overlays and Medal of Honor collar
art. The older master extract predates the existing mod's unit-award
expansion; it was compared and left intact. The live mod and installer
staging are the current deployable copies.

## Tracker certificates

All personal and unit awards in 602002–602052 now open a certificate from the
record, as do the shared Korean Service Medal, UN Service Medal and ROK PUC.
The supplied `Navy_Cross`, `Navy_MoH`, `Navy_commendation`, `Navy_puc` and
`Navy_unit_commendation` sheets are used directly. Reused U.S. landscape
forms keep their award artwork and receive
`Navy_seal_overlay_landscape.png`; the foreign UN and ROK sheets retain their
own seals.

The typed document follows the pilot's country: United States Navy for 602,
United States Marine Corps for 603, with the corresponding rank title and
Chief of Naval Operations or Commandant of the Marine Corps. The Secretary of
the Navy signs Department of the Navy awards. Signatories are selected by the
award's received date. Period wording retains the 1953 name “Commendation
Ribbon with Metal Pendant.” Repeat personal decorations name gold stars;
Commendation Ribbon, PUC and NUC name the period-correct bronze stars; KSM
uses service stars and repeat ROK PUCs authorize no device.

The dates for the Korean War Secretaries of the Navy and Chiefs of Naval
Operations follow the Naval History and Heritage Command's
[1950–1975 officer table](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/b/by-sea-air-land-marolda/secretaries-of-the-navy-and-key-united-states-naval-officers-1950-1975.html).
Commandant dates follow the Marine Corps History Division's records for
[Clifton B. Cates](https://www.usmcu.edu/Research/Marine-Corps-History-Division/People/Whos-Who-in-Marine-Corps-History/Abrell-Cushman/General-Clifton-B-Cates/)
and the official 1952–1955 tenure of Lemuel C. Shepherd Jr. Award names and
repeat-device wording follow the
[1953 Navy and Marine Corps Awards Manual](https://www.history.navy.mil/research/library/online-reading-room/title-list-alphabetically/n/navy-mc-awards-manual-rev1953/pt1-personal-decorations.html).
