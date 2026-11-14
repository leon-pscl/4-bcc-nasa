# Frontend tasks: what the UI looks like and how it behaves

Read this file together with `instructions.md` (the plan for the coding agent). This file says
**what each UI element looks like and does**, and in what order to build them.

**Which file wins when they disagree**

- **Layout, look and UI behavior:** this file wins over `instructions.md` Stage 6. Every
  difference is listed in section 1.3.
- **Contracts (C6 API shapes), approved dependencies, the working agreement and tests:**
  `instructions.md` wins.
- **Fonts and colors:** come from `docs/ui_settings.md`, applied as described in section 2.

**Visual reference:** the canvas "Burning Calendar app – UI draft"
(<https://claude.ai/artifact/2bfbnrv3VrXYomdpM15es3>; private to the repo owner). It uses
placeholder fonts and synthetic numbers. Everything needed to build the UI is written here,
so the link is optional.

**Starting point:** branch `pascual`, commit `82a4528`.

---

## Contents

1. Context
2. Visual style
3. Screen layout
4. State and data flow
5. Component specs
6. Task list (one sub-stage per session)
7. Backend fixes the UI depends on
8. Definition of done

---

## 1. Context

### 1.1 What the screen is for

An emergency manager selects an area and a date range. They then see:

- the **burning calendar** (hotspots per month and year)
- how **this month compares with the median**
- **anomalies**

They can also download the **hotspot CSV**, the calendar and the charts.

### 1.2 What exists on `pascual` today

`App.tsx` renders four things:

- an `<h1>` "Fire Calendar"
- `AreaSelector`: a Leaflet map, N/S/E/W inputs and a rectangle
- `DateRange`: two date inputs
- `BurningCalendar`: a plain table

Fix these problems as you go; don't build on top of them:

1. **The area and date inputs aren't connected to anything.** `api/client.ts` hard-codes
   `bbox=-64,-18,-60,-14&start=2003-01-01&end=2024-01-31`. `AreaSelector` defaults to a box in
   Luzon, so the map and the calendar show different places.
2. **Typing a minus sign crashes the app.** `Number(ev.target.value)` turns `-` into `NaN`,
   Leaflet throws `Invalid LatLng`, and the whole page goes blank. Clearing a field turns it
   into `0`.
3. **`npm run dev` can't reach the API.** `vite.config.ts` has no proxy, so `/api/*` returns
   `index.html` and JSON parsing fails.
4. **API handling is incomplete.** `client.ts` never checks `res.ok`. The zod schema covers 4
   of the 16 calendar fields, and the other endpoints have no schemas.
5. **The starter styling is still there.** `src/index.css` is the Vite template (purple accent,
   centered text, a 1126 px root, automatic dark mode). `src/App.css` isn't used.
6. **The calendar isn't readable yet.** It shows raw floats (`13.128285834595946`), month
   numbers instead of names, the oldest year first, and no colors.
7. **TypeScript isn't strict.** `tsconfig.app.json` has no `"strict": true`.
8. **The linter differs from the plan.** The branch uses oxlint; `instructions.md` asks for
   ESLint with `jsx-a11y` (see task 6a).
9. **There's one test,** which checks that the title renders.

### 1.3 Differences from `instructions.md` Stage 6

| `instructions.md` says | This file says | Why |
|---|---|---|
| A left control panel beside a central map; KPI cards and charts below them | A **map card** (map, with the area and date fields under it) and a **side panel with three tabs** on the right. The calendar runs full width below. The KPI card and charts move into the **Comparisons** tab. | Matches the team's draft: map plus side panel |
| 6b: after a search, the selector collapses to a summary chip | The fields **stay visible**, and the calendar subtitle repeats the area | Fewer states; responders can adjust and re-run |
| 6e: a row of 4 KPI cards | One "this month vs. median" card plus a 3-stat row, inside Comparisons | Same information, in the side panel |
| 6g: chart PNGs in the Downloads bar | Each chart has its own **PNG** button | Charts unmount when the tab changes, so the bar can't reach them |
| 6h: Methods panel last, or in a drawer | Methods is a **side-panel tab** | |
| (none) | **New: a Watchlist tab** (task 6i) | Replaces the "Notifications" idea from the first draft |
| (no styling rules) | Section 2, from `docs/ui_settings.md` | |

---

## 2. Visual style (from `docs/ui_settings.md`)

### 2.1 Tokens

Replace the contents of `src/index.css` with these tokens and the base rules in 2.2. Delete
`src/App.css`. Components use CSS Modules and read the variables.

```css
:root {
  --ink: #0f0f0f;      /* text, primary buttons, selected states, focus ring */
  --paper: #fafafa;    /* page background */
  --surface: #ffffff;  /* cards, panels, inputs */
  --line: #959596;     /* borders, dividers, chart axes. NEVER text (only 2.9:1 on white) */
  --muted: #6b6b6d;    /* secondary text: 5.1:1 on --paper, 4.7:1 on --fill. Added because --line fails for text */
  --fill: #f0f0f0;     /* neutral fills: zero cells, median row, bar tracks, info boxes */
  --danger: #b2182b;   /* validation error text only (6.8:1 on white) */

  --font-mono: 'IBM Plex Mono', ui-monospace, monospace;  /* titles, labels, big numbers */
  --font-sans: 'IBM Plex Sans', system-ui, sans-serif;    /* body, controls, tables */

  --r-control: 4px;
  --r-card: 6px;
  --s1: 4px; --s2: 8px; --s3: 12px; --s4: 16px; --s5: 24px; --s6: 32px;
}
```

**Fonts:** load them in `index.html` with a Google Fonts `<link>` (IBM Plex Mono 500 and 600;
IBM Plex Sans 400, 500 and 600). That needs no npm package. Also set
`<title>Burning Calendar</title>`.

### 2.2 Rules

- **Monochrome interface; color only for data.** Saturated color appears only in:
  - the data ramps in 2.3
  - the red chart line (#e31a1c)
  - the badge tints
  - `--danger`
- **No shadows and no gradients.** Separate surfaces with 1px `--line` borders. The one
  exception: controls on top of the map get a 1px `--ink` border so they stand out over
  satellite imagery.
- **No dark mode for now.** Remove `color-scheme: light dark`.
- **Type scale:**

  | Use | Font | Size / weight |
  |---|---|---|
  | App title | mono | 20 / 600 |
  | Calendar title | mono | 22 / 600 |
  | Section and tab headings | mono | 16 / 600 |
  | Big numbers (KPI) | mono | 40 / 600 |
  | Small caps labels (AREA, DATES, table headers) | mono | 11 / 600, uppercase, letter-spacing 0.08em, `--muted` |
  | Body, controls | sans | 14 / 400 or 500 |
  | Helper text, footnotes, legends | sans | 12 / 400, `--muted` |
  | Calendar cells, tables | sans | 12 or 13, `font-variant-numeric: tabular-nums` |

- **Numbers:**
  - Use `en-US` thousands separators.
  - Use the real minus sign (U+2212) in displayed values.
  - Dates display as `12 Nov 2026`, except in date inputs and URLs.
- **Controls:**
  - At least 44 px tall.
  - **Segmented controls:** joined rectangular buttons with radius `--r-control` on the outer
    corners. Selected: `--ink` background, white text. Unselected: `--surface` background,
    `--ink` text, 1px `--line` border. Use `aria-pressed` (or ARIA tabs for the side panel).
  - **Primary button:** `--ink` background, white text.
  - **Secondary button:** `--surface` background, 1px `--ink` border.
  - **Text button:** underlined, `--ink`.
- **Focus:** add `:focus-visible { outline: 2px solid var(--ink); outline-offset: 2px; }` to
  everything interactive. Never remove it.
- **Icons:** use one set. The suggestion is Lucide (`lucide-react`, 18 px, stroke 2), but it
  is **not on the approved dependency list, so ask first**. Until it's approved, inline these
  eight icons as SVG:
  - dashed square (Draw area)
  - plus and minus (zoom; Watch area)
  - link (Copy link)
  - download
  - arrow-right (Analyze)
  - alert-triangle (warnings)
  - x (Stop watching)
- **Motion:** none is needed. Use CSS transitions of 150 ms or less on hover and press only,
  and turn them off under `prefers-reduced-motion`. Don't add the animation libraries listed in
  `ui_settings.md` (GSAP, Three.js and so on) without asking.

### 2.3 Data colors (`lib/colors.ts`)

- **Count ramp:** ColorBrewer YlOrRd, exactly as `instructions.md` section 8:
  `#ffffb2 #fed976 #feb24c #fd8d3c #fc4e2a #e31a1c #b10026`.
  - Bins: 7 log-spaced bins from the 5th percentile to the maximum of the non-zero monthly values in the current calendar response, rounded to 2 significant figures.
  - Zero gets `--fill` with `--ink` text.
  - The legend shows each bin as a range.
- **Anomaly ramp:** ColorBrewer RdBu, red above the median. Symmetric bins, in percent:

  | % vs median | Color | Legend label |
  |---|---|---|
  | below −75 | `#2166ac` | below −75% |
  | −75 to −40 | `#67a9cf` | −75 to −40% |
  | −40 to −10 | `#d1e5f0` | −40 to −10% |
  | −10 to +10 | `#f7f7f7` | within ±10% |
  | +10 to +40 | `#fddbc7` | +10 to +40% |
  | +40 to +75 | `#ef8a62` | +40 to +75% |
  | above +75 | `#b2182b` | above +75% |

  Where the median is 0 (`anomaly_pct` is null), use `--fill` and show `n/a`.
- **Text on colored cells:** `textOn(bg)` returns `--ink` or white, whichever has the higher
  WCAG contrast. Unit-test it: white on `#e31a1c`, `#b10026`, `#b2182b` and `#2166ac`; `--ink`
  on every other ramp color.
- **Charts:**
  - median line: `--ink`, 2 px
  - middle-half band (25th to 75th percentile): `--ink` at 12% opacity
  - current or focused year: `#e31a1c`, 2.5 px, with circle markers (so it isn't told apart by
    color alone)
  - yearly bars: `--muted`; peak complete year: `--ink`; partial years: hatched (`--muted`
    stripes on `--fill`)
  - Methods chart: VIIRS `--ink` solid; MODIS × k `#e31a1c` dashed
  - gridlines `--fill`; axes `--line`; tick labels 11 px `--muted`
- **Map:**
  - hotspot cells: YlOrRd at 0.85 opacity, no stroke
  - selected area: 2 px dashed `--ink` (white on satellite)
  - coverage regions: 1 px dashed `--muted`
- **Badges** (Comparisons and Watchlist):
  - above the median: background `#fddbc7`, text `--ink`, starts with ▲
  - below the median: background `#d1e5f0`, text `--ink`, starts with ▼
  - rounds to 0%: `--fill`, text "At the median"

---

## 3. Screen layout

The wireframe is at 1440 px wide. Numbers are examples.

```
HEADER ─────────────────────────────────────────────────────────────────────────────
 [ramp mark] Burning Calendar                         Data through 12 Nov 2026  [Copy link]
             Harmonized MODIS + VIIRS fire hotspots, 2003 to today
SYNTHETIC BANNER (only when synthetic) ─────────────────────────────────────────────
 SYNTHETIC DATA  Example values for development. These are not real fire counts.

MAP CARD (flex 999 1 640px) ───────────────────┐  SIDE PANEL (flex 1 1 360px, max 420px)
 [Draw area] then drag on the map  [Map|Satellite] │  [Comparisons][Watchlist][Methods]
                                                │
   14°S   ┌ East Bolivia · 190,127 km² ┐        │   active tab content
          ┆  hotspot cells (YlOrRd)    ┆        │   (scrolls inside the panel)
   16°S   ┆                            ┆        │
          └┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┘  [+]   │
     66°W     64°W     62°W     60°W     [−]   │
 ─ map footer ──────────────────────────────────│
 Map shows the full record, 2003–2026 · Hotspots per cell ■■■■■■■ fewer to more
 ─ query bar (a <form>) ────────────────────────│
 AREA  [Box|Point + radius]  North edge  South edge  East edge  West edge   Size
                             [-14.0   ]  [-18.0   ]  [-60.0   ]  [-64.0   ] 190,127 km²
 Decimal degrees, with minus for south and west (18°S = −18). Drawing on the map fills these in.
 DATES  Start [2003-01-01] End [2026-11-12]  [Last 30 days|This year|Last 5 years|Full record]
                                                              [ Analyze this area → ]
────────────────────────────────────────────────┘

BURNING CALENDAR (full width) ──────────────────────────────────────────────────────
 Burning calendar                                              [Count|Anomaly vs median]
 Hotspots (harmonized) per month · East Bolivia · 18.0°S–14.0°S, 64.0°W–60.0°W · 190,127 km²
 Hotspots per month  ■0 ■1–4 ■5–9 ■10–25 ■26–80 ■81–300 ■301–900 ■over 900
 YEAR          JAN  FEB  MAR  …   AUG    SEP    OCT   NOV             DEC   YEAR TOTAL
 2026 PARTIAL   12    8    4  … 1,240  2,105    870  ┊115 SO FAR┊      –    [▓▓▓░░] 5,310
 2025            9   15    6  …   980  1,760    640   210             95   [▓▓▓▓░] 4,420
 …  newest year first, down to 2003
 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 MEDIAN 2003–2025 10  11    5  … 1,050  1,800    700   190             80          4,210
 footnote

HOTSPOT TABLE ──────────────────────────────────────────────────────────────────────
DOWNLOADS ──────────────────────────────────────────────────────────────────────────
```

**Page:**
- max-width 1440 px, centered
- padding 24 px 32 px (16 px below 720 px wide)
- 24 px between cards; background `--paper`

**Cards:** `--surface`, 1 px `--line` border, radius `--r-card`.

**DOM order is the visual order:** AppHeader → SyntheticBanner → [MapCard, SidePanel] →
BurningCalendar → HotspotTable → Downloads.

**Breakpoints:**
- **1100 px and wider:** the map card and side panel sit side by side. The side panel is as
  tall as the map card, and its content scrolls.
- **Below 1100 px:** the side panel moves under the map card at full width, and its height is
  no longer capped.
- **Below 720 px:**
  - The query-bar fields wrap, and "Analyze this area" becomes full width.
  - The calendar scrolls sideways inside its card: the table is at least 960 px wide, and the
    Year column stays fixed on the left.

---

## 4. State and data flow

- **The URL hash holds the applied query** (`state/urlState.ts`, wrapped by `useAppState`):
  - `bbox=W,S,E,N`, or `point=LAT,LON&radius_km=R`
  - `start=YYYY-MM-DD&end=YYYY-MM-DD`
  - `view=count|anomaly`
  - `focus=YYYY-MM` (optional)
  - `tab=comparisons|watchlist|methods`

  Defaults when the hash is empty:
  - area: the first region in `/api/coverage`
  - dates: from that region's `start` to `latest_date`
  - `view=count`, `tab=comparisons`
- **Fields edit a draft; nothing is fetched while typing.** The area and date fields keep a
  draft in component state. "Analyze this area" (or Enter in any field) checks the draft and
  then writes it to the hash. Drawing a box only fills the draft.
- **Queries key on the applied state.** Every react-query key includes the applied area and
  dates, plus `month` for `/api/map` and `page` and `all_sensors` for `/api/hotspots`.
- **Hooks** (`api/hooks.ts`): `useCoverage`, `useCalendar`, `useSummary`, `useMap(month?)`,
  `useHotspots(page, allSensors)`, `useMethods`. Components never call `fetch`.
- **"Today" comes from the data, not the browser.** Use `coverage.latest_date` for date
  presets and default end dates, not the browser clock. A browser in Manila (UTC+8) can be a
  day ahead of a UTC server, and the API rejects `end` later than the server's date (see B3).
- **Errors:**
  - API 400 `{error, field}`: show the message under the matching field and set
    `aria-invalid`.
  - API 422: "No data for this area yet. Covered areas: East Bolivia, Luzon example." (names
    from `/api/coverage`)
  - Network failure: "Couldn't reach the server." with a **Retry** button.
- **Screen readers:** one `aria-live="polite"` region near the top of `<main>` announces
  loading, errors, "Link copied" and Watchlist changes.
- **Area names:** if the applied bbox equals a coverage region, use its `name`, formatted
  (`bolivia_east` → "Bolivia east", or a display label if one is added). Otherwise use
  "Selected area".

---

## 5. Component specs

Each component lives in its own folder (`Component.tsx`, `.module.css`, `.test.tsx`), as
`instructions.md` requires. New folders: `AppHeader/`, `SidePanel/`, `ComparisonsPanel/`,
`Watchlist/`.

### 5.1 AppHeader (new)

- **Bar:** `--surface` background, 1 px bottom border `--line`, padding 12 px 32 px. Content
  wraps on narrow screens.
- **Left side:**
  - **Mark:** 7 vertical bars in the YlOrRd colors, 5 px wide, heights from 8 to 30 px,
    `aria-hidden`.
  - **Title:** "Burning Calendar" (mono 20/600). The branch says "Fire Calendar"; keep the name
    in one constant so the owner can choose.
  - **Subtitle:** "Harmonized MODIS + VIIRS fire hotspots, 2003 to today" (12 px `--muted`).
- **Right side:**
  - "Data through **12 Nov 2026**", from `coverage.latest_date`.
  - Secondary button with the link icon: "Copy link to this view". It copies `location.href`
    and announces "Link copied".

**Tests:** the date renders from the mock; clicking copy calls the clipboard and announces.

### 5.2 SyntheticBanner

- **Bar:** full width under the header, `--ink` background, white text, 13 px, padding 9 px
  32 px, `role="status"`.
- **Text:** "**SYNTHETIC DATA**" (mono 600, letter-spacing 0.08em), then "Example values for
  development. These are not real fire counts."
- **When:** shown whenever any response has `synthetic: true`.

### 5.3 MapCard (`AreaSelector` + `ResultsMap` + `DateRange` + Analyze)

One card, overflow hidden, with three parts stacked top to bottom.

**(a) The map**
- **Size:** `aspect-ratio: 2 / 1`, at least 280 px tall.
- **Basemaps:**
  - Street: OpenStreetMap.
  - Satellite: Esri World Imagery
    (`https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}`).
  - Both show their attribution.
- **Map options:**
  - `worldCopyJump={false}`, `maxBounds` = the world, `maxBoundsViscosity={1}`.
  - Always wrap longitudes into −180 to 180 (bboxfinder showed −251; that must never reach
    the API).
- **Overlay controls:** 44 px tall, `--surface` background, 1 px `--ink` border.
  - **Top-left, "Draw area"** (dashed-square icon). It's a toggle with `aria-pressed`.
    - In draw mode: map dragging is off, the cursor is a crosshair, and a hint chip shows
      "Drag on the map · Esc to cancel".
    - Pressing and dragging draws the rectangle live. Releasing fills North/South/East/West
      (rounded to 4 decimals) and leaves draw mode.
    - Write the drag handler yourself; don't use Leaflet.draw (as `instructions.md` 6b says).
  - **Top-right:** segmented "Map | Satellite".
  - **Top-left stack:** zoom + and - now live in the top-left toolbar (with Draw/Delete), not bottom-right.
- **Layers, bottom to top:**
  1. **Coverage regions** from `/api/coverage`: 1 px dashed `--muted`, with the region name as
     a tooltip.
  2. **Hotspot cells** from `/api/map`: rectangles `grid_deg` wide.
     - Fill: YlOrRd, using 7 log-spaced bins from the 5th percentile to the maximum of the non-zero cell values, rounded to 2 significant figures.
     - Clicking a cell opens a popup: "12 hotspots · 16.025°S, 61.975°W".
     - When `month` is set, show only that month.
  3. **Draft area:** 2 px dashed `--ink` (white on satellite). It's a rectangle in Box mode and
     a circle in Point mode.
     - A label chip sits above the area's top-left corner: "East Bolivia · 190,127 km²"
       (`--surface`, 12 px 600).
- **After Analyze:** `fitBounds` to the area, with padding.
- **No sensor categories** anywhere on the map.

**(b) Map footer strip** (at least 44 px tall, 1 px top border, 12 px text)
- "Map shows **the full record, 2003–2026**". When a month is focused:
  "Map shows **August 2010 (1,234 hotspots)**", followed by a text button "Show full record".
- **Legend:** "Hotspots per cell", 7 swatches (18×10 px), then "fewer to more".
- **Right-aligned, only when `aggregated_to` is set:** "Shown on a coarser 0.25° grid to keep
  the map fast."

**(c) Query bar** (a `<form>`; padding 16 px 20 px 20 px; 1 px top border)

- **Row 1: AREA**
  - Label "AREA" (small caps), then segmented **"Box | Point + radius"**.
  - **Box mode:** four labeled text inputs, 104 px wide, 44 px tall, `inputmode="decimal"`,
    in this order: **North edge, South edge, East edge, West edge**. Keep the values as
    strings while typing; parse them only to validate.
  - **Point mode:** **Latitude**, **Longitude**, **Radius (km)**.
  - **Size readout:** label "Size" (12 px `--muted`), value mono 20/600: "190,127 km²". It
    updates live from the draft (`lib/geo.ts`) and shows "—" when the draft is invalid.
- **Helper line** under row 1 (12 px `--muted`): "Decimal degrees, with minus for south and
  west (18°S = −18). Drawing on the map fills these in."
  - When there's a problem, it's replaced by the error in `--danger`.
  - Connect it to the inputs with `aria-describedby`.
- **Validation messages** (same rules as `firecal/analytics/area.py`):
  - "Enter all four edges in decimal degrees."
  - "North and South must be between −90 and 90."
  - "East and West must be between −180 and 180."
  - "The South edge must be below the North edge."
  - "The West edge must be left of the East edge (areas can't cross the 180° line)."
  - "Enter a latitude, a longitude and a radius."
  - "The radius must be between 1 and 500 km."
  - "Larger than the 500,000 km² limit. Draw a smaller area."
- **Row 2: DATES**
  - Label "DATES", then **Start** and **End** date inputs (150 px). `min` and `max` come from
    the coverage `start` and `latest_date`.
  - Segmented presets: **Last 30 days**, **This year**, **Last 5 years**, **Full record**
    (the default). A preset is `aria-pressed` when the draft matches it. Presets end on
    `coverage.latest_date`.
  - On the right: the primary submit button **"Analyze this area →"** (48 px tall).
    - Disabled while the draft is invalid.
    - The reason is in the helper or error text, linked with `aria-describedby`.
- **Date errors:**
  - "Choose a start date and an end date."
  - "The start date must be before the end date."
  - "Data covers 1 Jan 2003 to 12 Nov 2026." (built from coverage)

**Tests (6b and 6c):**
- The fields and the drawn box stay in sync both ways.
- Typing `-`, `''` or `abc` never throws.
- An area over 500,000 km² disables Analyze and shows the message.
- An antimeridian box is rejected.
- Presets produce the right range for a fixed `latest_date`.
- Enter submits.
- No request is made until Analyze.

### 5.4 SidePanel (new)

- **Card:** same as the other cards.
- **Tab strip:** padding 10 px, `--paper` background, 1 px bottom border. Three equal tabs:
  **Comparisons**, **Watchlist**, **Methods**, each 44 px tall. Selected: `--ink` with white
  text. The others: white with `--ink` text and a 1 px `--line` border.
- **ARIA tabs:** `role="tablist"`, `tab` and `tabpanel`, with `aria-selected` and
  `aria-controls`. Left and right arrow keys move between tabs. The selected tab is stored in
  the hash as `tab=`.
- **Panel:** padding 20 px 22 px 28 px; 24 px between sections. Scrolls when it's taller than
  the map card.

### 5.5 Comparisons tab (`ComparisonsPanel` with `KpiCards`, `MonthlyPatternChart`, `YearlyChart`)

There are three sections. Each heading (mono 16/600) is the question the section answers.

**1. "How does this month compare?"** A bordered card, radius 6, padding 16:
- **Label:** "November 2026, days 1–12" (12 px `--muted`), from `summary.current_month`
  (`year`, `month`, `through_day`).
- **Big number:** `current_month.value` (mono 40/600), followed by "hotspots (harmonized)"
  (13 px `--muted`).
- **Badge** (section 2.3), 14 px 600: "▲ 40% above the median", "▼ 12% below the median" or
  "At the median". Uses `pct_vs_median`.
- **Two horizontal bars:** 12 px tall on a `--fill` track. "This year" in `#e31a1c` and
  "Median" in `--ink`, with values right-aligned. The pair has `role="img"` and an
  `aria-label` such as "This year 115 hotspots, median 82 for the same days".
- **Footnote** (12 px `--muted`): "Median of the same days (Nov 1–12) in 2003–2025. Whole
  months would make a month in progress look low."
- **When `current_month` is null:** "The selected dates don't include the current month. Pick
  a range that ends on the latest data date to compare."

Under the card, a **3-stat row** (labels in 11 px small caps, values in mono 18/600):
- **Total in range:** `summary.total`
- **Peak year:** `peak_year` (complete years only)
- **Peak month:** `peak_month`, shown as "Aug 2017"

**2. "When in the year does it burn?"** `MonthlyPatternChart`, a Chart.js line chart about
180 px tall at panel width:
- x axis: Jan to Dec
- shaded band between `monthly_p25` and `monthly_p75` (two datasets, `fill: '-1'`)
- `monthly_median` line
- the focused year's line, or the current year's if nothing is focused. The current year
  stops at the last complete month.
- **HTML legend below the chart** (not the Chart.js legend): "Median", "Middle half of years",
  "2026 (Jan–Oct)".
- **Sentence:** "Busiest months: **Aug, Sep, Jul**" (the top 3 by median).
- **PNG text button** at the top-right of the chart. It calls `toBase64Image()` and downloads
  `monthly_pattern_<W>_<S>_<E>_<N>_<start>_<end>.png`.

**3. "Which years burned most?"** `YearlyChart`, a Chart.js bar chart 120 px tall:
- one bar per year from `annual_totals`
- the peak complete year in `--ink`, the others `--muted`
- years in `partial_years` hatched (with a `CanvasPattern`)
- x-axis labels only for the first and last year, e.g. "2026 (partial)"
- **Below it,** "Top years (complete years only)" (12 px 600) and a list of 3: rank · year ·
  total. Each row is 13 px with a 1 px `--fill` divider.
- A **PNG** button, as in chart 2.

**Chart.js rules:**
- Animation off, or 200 ms or less and off under reduced motion.
- Tooltips on.
- Fonts: Plex Sans 11 px.
- Each `<canvas>` has `role="img"` and an `aria-label` summary, e.g. "Yearly totals 2003 to
  2026; highest complete year 2010 with 34,567 hotspots".

**Data:** `/api/summary`, plus `/api/calendar` (`monthly_median`, `monthly_p25`,
`monthly_p75`, `annual_totals`, `partial_years`, and `values` for the focused year).

### 5.6 Watchlist tab (new, task 6i)

**Purpose:** watch several areas at once, and flag those where this month is running above
their median for the same days. It runs entirely in the browser and uses `/api/summary`, so
no backend change is needed.

**Storage** (local storage, key `firecal.watchlist.v1`):

```ts
{ threshold: number,                       // default 25 (%)
  areas: Array<{ id: string; name: string;
                 area: { bbox: [number, number, number, number] }
                     | { point: [number, number]; radius_km: number };
                 added: string }> }        // ISO date, at most 20 areas
```

Wrap every read and write in try/catch. If storage isn't available, show: "Can't save in this
browser; the list resets when you leave."

**Layout, top to bottom:**
1. Heading "Watched areas", then (13 px `--muted`) "Flags an area when this month is running
   above its median for the same days."
2. A full-width secondary button with the plus icon: "Watch the current area". It adds the
   applied area. If that area is already listed, the button is disabled and reads "Already
   watching this area".
3. **Threshold row** on `--fill` (padding 10 px 12 px, radius 4): "Flag when above the median
   by at least" `[25]` "%". The number input is 72 px wide, 0 to 500, step 5.
4. **Summary line** (bold 13 px, `aria-live`): "1 of 4 areas flagged at 25% or more above the
   median".
5. **One card per area.** Order: flagged first, then by % (highest first); areas with no data
   or errors go last.
   - **Card:** 1 px `--line` border (2 px `--ink` when flagged), radius 6, padding 12 px
     14 px.
   - **Top line:** the name (15 px 600). Under it, the coordinates (12 px `--muted`):
     "18.0°S–14.0°S · 64.0°W–60.0°W". When flagged, a chip on the right: "FLAGGED" (`--ink`
     background, white, mono 11 px 600).
   - **Status line:** a badge (section 2.3) and "Nov 1–12: 115 · median 82".
   - **Other states:**
     - loading: "Checking…"
     - 422: "Outside the data coverage, so there is nothing to compare yet."
     - other errors: "Couldn't check this area." with a **Retry** text button
     - `current_month` null: "No data for this month yet."
   - **Actions:**
     - Secondary **"Open on map"**: writes the area to the hash, sets the full date record and
       switches to the Comparisons tab.
     - Text button **"Stop watching"**: removes the area and announces "Stopped watching East
       Bolivia". An Undo option for 5 s is optional.
6. **Footer** (12 px `--muted`): "Saved in this browser only and checked each time you open
   this tab. Data through 12 Nov 2026."

**Requests:** one `useSummary` per area, with `start = coverage.start` and
`end = coverage.latest_date`. Only fetch while the tab is open.

**Tests:**
- Adding, removing and changing the threshold update the flags and the order.
- Local storage failing doesn't crash.
- A 422 row shows the coverage message.

### 5.7 Methods tab (`MethodsPanel`)

Five sections. Headings use mono 16/600; body text is 13 px `--muted` unless noted.

1. **"What one hotspot means"**
   "One grid cell (0.05°, about 5.5 km across) with at least one fire detection on a given
   day. Counting cells instead of raw detections stops VIIRS's smaller pixels from inflating
   the numbers, and MODIS days are scaled so they count like VIIRS days."
2. **"Where the data comes from"**
   - **Timeline bar** (32 px, 1 px `--line` border, radius 4), with segment widths
     proportional to time:
     - left, Jan 2003 to Jan 2012: hatched `--fill`, labeled "MODIS Aqua × k"
     - right, Feb 2012 to today: `--ink`, labeled "VIIRS S-NPP" in white
   - **Labels under the bar** (11 px): "Jan 2003", "Feb 2012" (`SWITCH_DATE`), "Today".
   - **Paragraph:** active-fire hotspots come from NASA FIRMS. MODIS (Aqua, about 1 km pixels)
     gives the long history; VIIRS (S-NPP, 375 m) takes over from February 2012. On days with
     no VIIRS data, scaled MODIS fills the gap.
3. **"How MODIS years were scaled"**
   - **Paragraph:** for each 1° tile and month, **k = VIIRS fire cell-days ÷ MODIS fire
     cell-days**, measured over 2013–2017. Tiles with too few fires fall back to the tile's
     overall k, then to the whole area.
   - **Definition list,** from `/api/methods` → `calibration`:

     | Label | Value |
     |---|---|
     | Median k | `k_median`, 2 decimals |
     | Range of k | `k_min`–`k_max` |
     | Calibration level used | from `count_per_level`, e.g. "tile × month: n · tile: n · all tiles × month: n · all: n" |
4. **"Does the scaling hold up?"**
   - **3 stat tiles in a grid** (1 px border, radius 6, padding 10). Label 11 px 600, value
     mono 24/600, note 11 px `--muted`. Values come from
     `validation.validation_years.metrics`:

     | Tile | Value | Note |
     |---|---|---|
     | Correlation (r) | `pearson_r`, 2 decimals | monthly totals |
     | Bias | `bias_pct`, signed, 1 decimal, % | scaled vs VIIRS |
     | Typical error | `median_abs_pct_error`, 0 decimals, % | median, per month |
   - **Caption:** "Held-out years 2018–2021 (not used to fit k)", built from
     `validation_years.years`.
   - **Chart** (Chart.js line, about 150 px tall):
     - `monthly_viirs` (solid `--ink`) against `monthly_modis` (dashed `#e31a1c`)
     - x axis: the calibration-year months followed by the validation-year months
     - the validation span shaded `--fill`, with top labels "Fitted 2013–2017" and "Held out
       2018–2021"
     - HTML legend: "VIIRS S-NPP", "MODIS Aqua × k"
5. **"How fresh is the data?"** A `--fill` box, radius 6:
   "Latest data: **12 Nov 2026**. The most recent months use near-real-time data, which
   standard processing replaces a few months later, so recent counts can shift slightly."

### 5.8 BurningCalendar (the main element)

- **Card:** padding 22 px 24 px 24 px; 16 px between parts.
- **Header row:**
  - Left: `<h2>` "Burning calendar" (mono 22/600). Under it (13 px `--muted`): "Hotspots
    (harmonized) per month · {area name} · {18.0°S–14.0°S, 64.0°W–60.0°W} · {190,127 km²} ·
    {1 Jan 2003 – 12 Nov 2026}".
  - Right: segmented **"Count | Anomaly vs median"**, stored in the hash as `view=`.
- **Legend row** (12 px):
  - A title: "Hotspots per month" or "Difference from the monthly median".
  - Swatches 26×16 px with a 1 px `rgba(0,0,0,.12)` inner border, each with its range label
    (section 2.3).
- **Warnings:** a box with a 1 px `--ink` border, radius 4, the alert icon, 13 px text.
  - `baseline_warning`: "Only N complete years in this range, so medians and anomalies aren't
    reliable. Widen the range to at least 5 full years."
  - `coverage_warning`: "This area is only partly covered by the data; counts outside the
    covered part are missing."
- **Table:** a real `<table>`, with `<caption class="visually-hidden">` "Hotspots per month
  (columns) and year (rows)" and `border-spacing: 3px`.
  - **Columns:**
    - **Year:** a `<th scope="row">`, 92 px, fixed to the left when scrolling.
    - **Jan to Dec:** `<th scope="col">`, mono 11 px small caps, equal widths, at least 56 px.
    - **Year total:** 170 px.
  - **Rows:** the newest year first.
  - **Year cell:** the year (13 px 600). Years in `partial_years` also get a "PARTIAL" tag
    (`--fill` background, mono 10 px 600).
  - **Month cell:** a `<button>` 30 px tall, radius 3, with the background from the current
    view and the text color from `textOn()`, 12 px tabular.
    - **Count text:**
      - `0` → "0"
      - more than 0 but under 1 → "<1"
      - anything else → a rounded integer with separators (values are harmonized floats)
    - **Anomaly text:** "+40%", "−12%", or "n/a" when the median is 0.
  - **Months outside the range, or with null values:** no button; "–" in `--muted` on
    `--surface`.
  - **The current month in progress** (from `partial`):
    - a 2 px dashed `--ink` inner border, drawn with `::after` so it doesn't clash with the
      focus outline
    - a "SO FAR" tag after the number (mono 10 px 600)
    - In Anomaly view, its % comes from `summary.current_month.pct_vs_median` (the same days),
      **not** the full-month `anomaly_pct`.
  - **The focused month:** a 3 px solid `--ink` outer ring (`box-shadow: 0 0 0 3px`).
  - **Labels on each cell:**
    - "August 2010: 1,234 hotspots, 85% above the median"
    - "November 2026, days 1 to 12 so far: 115 hotspots, 40% above the median for the same
      days"
    - "…, no median to compare with"
  - **Clicking a cell (or Enter/Space)** sets `focus=YYYY-MM`. Doing it again on the focused
    cell clears it. The map, the hotspot table and the Comparisons chart follow the focus.
  - **Year total cell:** a `--fill` track with a bar whose width is that total divided by the
    largest complete-year total.
    - The bar is `#c8c8c9`; partial years are hatched.
    - The number sits on top: 12 px 700, `--ink`.
- **Median row:** a footer row with a 2 px `--ink` top border, on `--fill`, numbers 12 px 700.
  - The label is "MEDIAN", with the baseline years under it (`baseline_years` first–last,
    e.g. "2003–2025").
  - Its total is the median of the baseline years' annual totals, computed on the client.
- **Footnote** (12 px `--muted`): "One hotspot = one fire cell-day in VIIRS-equivalent terms
  (see Methods). The outlined cell is the current month so far, compared with the median of
  the same days in past years. Hatched totals are partial years. Select a cell to show that
  month on the map."

**Tests (6d):**
- Numbers render rounded.
- The rows run newest first.
- Each cell has the right label.
- The view switch changes the cell text and the legend.
- The partial cell shows "SO FAR" and uses the same-days %.
- Selecting a cell updates `focus` in the hash.

### 5.9 HotspotTable (`instructions.md` 6g; not drawn in the canvas)

- **Placement:** a card between the calendar and Downloads.
- **Heading:** "Hotspots in this search" (mono 16/600), with the count on the right:
  "12,345 detections".
  - When a month is focused: "August 2010 · 1,234 detections", plus a text button
    "Show all dates". With a focus, the request uses that month's first and last day, clipped
    to the range.
- **Data:** server-paged from `/api/hotspots`, `page_size=100`.
- **Columns:** Date (local), Time (UTC), Latitude, Longitude, Confidence, FRP (MW),
  Day/Night.
  - A checkbox, **"Show sensor details"**, adds Sensor, Platform and Processing.
- **Style:**
  - text 13 px; headers mono 11 px small caps `--muted`
  - numbers right-aligned and tabular
  - 1 px `--fill` lines between rows
  - scrolls sideways inside the card on small screens
- **Pager:** "Previous", "Page 3 of 124", "Next", each 44 px tall.
- **Empty state:** "No hotspots in this area and date range."

### 5.10 Downloads

- **Header:** "Download this search" (mono 18/600). On the right (13 px `--muted`):
  "East Bolivia · 2003-01-01 to 2026-11-12".
- **Buttons:** 44 px tall, with the download icon. Use `<a href download>` styled as buttons,
  built from the applied query, not `fetch`.
  - Primary: **Hotspots CSV** → `/api/hotspots.csv?{query}&all_sensors=0|1`, next to a checkbox
    **"Include all sensors"**.
  - Secondary: **Calendar CSV** → `/api/calendar.csv?{query}`.
  - Secondary: **Calendar image (PNG)** → `/api/calendar.png?{query}`.
- **Note** (12 px `--muted`): "Hotspots CSV: one row per detection, with date, UTC time,
  latitude, longitude, confidence, fire radiative power, day/night and sensor. By default it
  holds only the detections behind the calendar; tick "Include all sensors" for every MODIS
  and VIIRS detection in the area."
- **Mock mode:** the buttons are disabled and a line explains "Downloads need the live API."
- Chart PNGs live on each chart (5.5), and **Copy link** is in the header (5.1).

---

## 6. Task list (in order, one sub-stage per session)

At the end of each sub-stage, follow `instructions.md` section 3: run `npm run check` (and
`pytest` if backend files changed), report the results, add a screenshot to
`docs/screenshots/`, then stop for review.

### 6a. Plumbing, tokens and the app shell (do first)
- [ ] Delete the Vite template CSS. Add the tokens and base rules from section 2: body margin
      0, `--paper` background, `--font-sans` 14 px/1.45 in `--ink`, headings in
      `--font-mono`, `:focus-visible`, and a `.visually-hidden` helper.
- [ ] Add the Google Fonts `<link>` and `<title>` in `index.html`.
- [ ] Turn on `"strict": true` and fix the errors.
- [ ] Linting: either switch to ESLint + `typescript-eslint` + `eslint-plugin-jsx-a11y` (as
      `instructions.md` says), or keep oxlint and turn on its `jsx-a11y` plugin. **Ask the
      owner which.**
- [ ] `vite.config.ts`: proxy `/api` and `/health` to `http://localhost:8000`.
- [ ] `api/schemas.ts`: zod schemas for every C6 response (the calendar's 16 fields, summary,
      map, the hotspots page, coverage, methods, and the error shape).
- [ ] `api/client.ts`: the only module that calls `fetch`.
  - Check `res.ok`.
  - Turn `{error, field}` into a typed `ApiError(status, field, message)`.
  - Mock mode (`?mock=1` or `VITE_USE_MOCKS=true`) reads `/mock/api_<name>.json`.
- [ ] `api/hooks.ts`: the hooks in section 4.
- [ ] `state/urlState.ts` and `useAppState`: hash ↔ state, with the defaults from section 4.
- [ ] `lib/colors.ts`, `lib/geo.ts` (the same cases as `area.py`) and `lib/format.ts`
      (counts, signed %, `12 Nov 2026`, `18.0°S`), each with unit tests.
- [ ] `App.tsx` laid out as in section 3, with placeholders. Add `AppHeader`,
      `SyntheticBanner` and the `aria-live` region.
- [ ] **Contract test:** every file in `public/mock/` parses with its schema.
- **Done when:**
  - `npm run check` passes
  - the page loads in mock mode
  - changing the hash changes the state, and the reverse

### 6b. Map card: map, draw tool and area fields (5.3 a and c, row 1)
- [ ] Map at 2:1, Street and Satellite basemaps, longitudes wrapped, world bounds.
- [ ] "Draw area" toggle with your own drag handler; Esc cancels.
- [ ] Box and Point + radius modes, fields kept as strings, live km², every validation
      message.
- [ ] Coverage outlines and the area label chip.
- **Done when:** the 6b tests in 5.3 pass, and it works with the keyboard only (typing
  coordinates).

### 6c. Dates and Analyze (5.3 c, row 2)
- [ ] Start and End with coverage limits, four presets, the date errors.
- [ ] `<form>` submit: check the draft, write the hash, `fitBounds`. Nothing is fetched before
      that.
- **Done when:** the 6c tests in 5.3 pass.

### 6d. Burning calendar (5.8)
- [ ] Table, ramps, legend, newest year first, year totals, median row, partial and SO FAR
      markers, the view switch, cell labels, focus on click.
- **Done when:** the 6d tests in 5.8 pass.

### 6e. Side panel and Comparisons tab (5.4, 5.5)
- [ ] ARIA tabs stored in the hash.
- [ ] The this-month card (including the null state), the 3-stat row, and both charts with
      PNG buttons and labels.

### 6f. Map results layer and footer (5.3 a and b)
- [ ] `/api/map` cells, popups, following the focused month, the footer text and legend, the
      aggregation notice.

### 6g. Hotspot table and Downloads (5.9, 5.10)
- [ ] The paged table, the sensor-details checkbox, following the focus, the pager, the empty
      state.
- [ ] Download links built from the applied query; disabled in mock mode.

### 6h. Methods tab (5.7)
- [ ] All five sections from `/api/methods`, the timeline bar, the stat tiles, the validation
      chart.

### 6i. Watchlist tab (5.6), new
**Status: not shipped.** The tab list in the Shipping app offers Comparisons and
Methods only; the hash `tab=watchlist` falls back to Comparisons. The placeholder
code stays in the tree for when this is built; no UI, tests or docs promise it.
- [ ] Local storage model, threshold, add/remove/open, ordering, every row state, the summary
      line.

---

## 7. Backend fixes the UI depends on

These belong to Stages 4 and 5. Each one is small; do them before (or alongside) the
sub-stage named.

- **B1. Partial-month bug** (before 6d). In `firecal/analytics/calendar.py`, the condition
  `if end_d.month < 12 or end_d.day < 28:` marks the end month as in progress for almost every
  end date. The mock data says January 2024 is partial "through day 31".
  - It should be partial only when `end_d.day` is before the last day of `end_d`'s month.
  - Add tests: `end=2024-01-31` → `partial` is `None`;
    `end=2026-11-12` → `{year: 2026, month: 11, through_day: 12}`.
- **B2. Coverage check** (before 6e). `/api/summary` doesn't run the coverage check (422) that
  `/api/calendar` does. The Watchlist relies on that 422.
- **B3. Which day counts as "today"** (before 6i; ask the owner).
  - Now: `summary.current_month` is filled only when the server's date falls inside
    `[start, end]`, and `params.py` rejects any `end` after the server's date.
  - The frontend will send `end = coverage.latest_date`.
  - Suggestion: work out `current_month` from `latest_data_date` (or accept a `today`
    parameter), so the comparison doesn't depend on the server clock or time zones.
- **B4. API tests.** Add Flask test-client tests for every endpoint, as `instructions.md`
  Stage 5 requires; none exist yet.
- **B5. Mock query field.** The mock calendar's `query` has no `bbox`, though C6 includes it.
  Regenerate it with `scripts/make_mocks.py`.
- **B6. Methods chart data.** Confirm that `validation.*.metrics.monthly_modis` is MODIS × k
  (scaled), since the Methods chart labels it that way.
- **Cleanup (Stage 7).** `templates/` and `static/` (the old dashboard, with unescaped
  `innerHTML`) are still in the repo. They're no longer served; delete them in Stage 7.

---

## 8. Definition of done (the whole UI)

- [ ] Every row in the objective table (`instructions.md` section 9) is visible in the UI.
- [ ] **Keyboard-only run-through:**
  - type an area
  - set the dates with a preset
  - Analyze
  - switch to Anomaly
  - select a calendar cell
  - switch tabs
  - add an area to the Watchlist
  - download the hotspot CSV
- [ ] No color carries meaning alone: every colored cell shows its number, and every badge has
      ▲/▼ and words.
- [ ] Text contrast meets WCAG AA (section 2.1); `--line` is never used for text.
- [ ] Works in mock mode and against the real API, with no console errors.
- [ ] Screenshots in `docs/screenshots/` for each sub-stage.
