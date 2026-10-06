# Biography booklet artwork

Create one reusable open-book spread. The application places the biography as live text and reuses the same spread for pages 1–2, 3–4, 5–6, and so on. An open book should therefore show **two pages**, not three. If the final page count is odd, the unused right page remains blank.

## File

- Name: `open_book.png`
- Canvas: **2400 × 1500 px** (8:5 landscape)
- Colour: sRGB, 8-bit RGBA PNG
- View: almost straight overhead, with little or no perspective distortion
- Transparency: preferred outside the book, so the application can supply the desk background

## Geometry

The companion `biography-booklet-guide.svg` is an exact-size overlay.

- Whole book: x **100–2300**, y **100–1400**
- Left paper: x **170–1168**, y **145–1350**
- Right paper: x **1232–2230**, y **145–1350**
- Left text safe area: x **290–1050**, y **260–1240**
- Right text safe area: x **1350–2110**, y **260–1240**
- Keep the centre shadow mainly inside x **1120–1280**

The page edges may curve, but the two text areas must remain visually flat and rectangular. The browser cannot bend live text to match strong perspective or page curl.

## Appearance

A 1940s–1950s military personal-record booklet will fit the Service Record better than a private diary. Suggested treatment:

- dark brown, burgundy, olive, or faded blue cloth/leather cover visible around the paper;
- warm ivory pages with light age, fibre, and handling marks;
- restrained centre-gutter shadow and slightly darker outer corners;
- a few subtle creases or stains outside the text safe areas;
- even lighting across both writing areas.

Leave the pages completely blank: no title, handwriting, rules, page numbers, insignia, stamps, photographs, or baked-in text. The application supplies the title, pilot name, biography, page numbers, and controls. Avoid strong stains or shadows behind the live text.

The surrounding scene can remain the current dark desk, or the transparent PNG can later be paired with a period map, pencil, identity card, or folded flight gloves in CSS. Keeping those objects outside the book makes one artwork usable at every screen size and in every language.
