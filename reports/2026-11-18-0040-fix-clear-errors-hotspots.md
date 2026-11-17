# Report: error messages in calendar + hotspots, cleanup commits — 2026-11-18 00:40 Asia/Manila

## Summary
Three small changes landed on `pascual`. No tag, `main` not touched (it is still at v2.2.4, 7ed9934).

| what | branch | commit | merged into pascual | CI |
|---|---|---|---|---|
| calendar error cause, hotspots stay loading until visible | fix/clear-errors | 9d9f07d | 852f7b3 (--no-ff) | #158 success (branch), #159 success (pascual) |
| hotspot query error instead of loading forever | fix/hotspot-error | ef3b72b | ef07e85 (--no-ff) | #160 success (branch), #161 success (pascual) |
| drop sample-data + docs refs, move FIRMS CSVs | pascual | ab3e552 | ab3e552 (direct) | no own run; contained in #157 |
| drop one-off task notes in inbox/ | pascual | 6189cad | 6189cad (direct) | #157 success |

`pascual` tip: **ef07e85** (= `origin/pascual`).

CI runs: https://github.com/leon-pscl/4-bcc-nasa/actions/runs/44124037547 (#158),
https://github.com/leon-pscl/4-bcc-nasa/actions/runs/44124534516 (#159),
https://github.com/leon-pscl/4-bcc-nasa/actions/runs/44127364047 (#160),
https://github.com/leon-pscl/4-bcc-nasa/actions/runs/44127992716 (#161),
#157 = https://github.com/leon-pscl/4-bcc-nasa/actions/runs/44123492296

## 1. fix/clear-errors (9d9f07d)
- `BurningCalendar.tsx`: an error now shows its cause instead of a bare "Couldn't load calendar".
  `ApiError` → `Couldn’t load calendar (<status> – <message>).`; anything else → `Couldn’t load calendar (unexpected response from the server).` Raw Zod text is never shown.
- `HotspotTable.tsx`: the card is rendered before the query is enabled, so `isLoading` was false and `total` defaulted to 0 ("0 detections / No hotspots"). Now `!visible || data === undefined` counts as loading: no count in the header, "Loading hotspots…" in the body.
- Tests: two calendar tests (ApiError, non-ApiError) and a new `HotspotTable.test.tsx` (disabled query shows loading, not "No hotspots", not "0 detections").

## 2. Cleanup commits (ab3e552, 6189cad)
- `ab3e552`: removed `sample-data/` (FIRMS CSVs moved to `tests/fixtures/`, `tests/test_cells.py` updated), `docs/dashboard.jpg`, `docs/refs/*.png`; Dockerfile and docs references cleaned up.
- `6189cad`: removed the one-off task notes under `inbox/` from the code tree.
- Both were pushed in one push; GitHub ran CI once, on the tip — run #157 on `6189cad`, which contains `ab3e552`. There is no separate run for `ab3e552`.

## 3. fix/hotspot-error (ef3b72b)
- `HotspotTable.tsx`: reads `error` from `useHotspots` and renders it before the loading branch — `Couldn’t load hotspots (<status> – <message>).` for an `ApiError`, otherwise `Couldn’t load hotspots (unexpected response from the server).` No count in the header, and no "Updating…" while in the error state.
- An error now wins over loading and over stale/placeholder data, so a failed `/api/hotspots` no longer spins forever.
- Test: `{ data: undefined, error: ApiError(500, 'internal server error') }` with the card scrolled into view (IntersectionObserver callback invoked) → error line shown, "Loading hotspots…" and "0 detections" absent.

## Verification
- `npm run check` (typecheck + eslint + vitest) locally: 18 files, 80 tests after (1), 81 tests after (3). Green.
- CI `pytest -q` green on every run above; secret guard green.
- Backend pytest was not run locally — no Python/pytest on this PC. CI covered it.
- No tag created. `main` untouched: local `main` f14a797, `origin/main` 7ed9934 (v2.2.4).

## Live site check (owner, 2026-11-18)
- `/health` ok, `data_version eefaaeca5d9a1664`, latest date 2026-11-14, 75 partitions in packaged `data/processed`, `/api/hotspots` returns rows.
- The screenshot showing "Full record end 2026-11-07" came from a different instance, not this deployment; nothing changed for it here.

## Not done
- No fast-forward of `main` (as instructed). When wanted: `git push origin ef07e85:refs/heads/main`.
- No new tag for this round.
