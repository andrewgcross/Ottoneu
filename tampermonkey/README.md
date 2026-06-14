# Ottoneu Statcast TamperMonkey Scripts

Adds Baseball Savant Statcast percentile data to Ottoneu pages via TamperMonkey userscripts.

## Files

| File | Purpose |
|---|---|
| `otto-statcast-core.js` | Shared library — data fetching, IndexedDB caching, crosswalk. Not a standalone script. |
| `otto-roster.user.js` | Injects Statcast columns into the setlineups batter table. |
| `GAPS.md` | Known limitations and future work. |

## Installation

### 1. Install TamperMonkey

Install the TamperMonkey extension for your browser:
- [Chrome Web Store](https://chrome.google.com/webstore/detail/tampermonkey/dhdgffkkebhmkfjojejmpbldmpobfkfo)
- [Edge Add-ons](https://microsoftedge.microsoft.com/addons/detail/tampermonkey/iikmkjmpaadaobahmlepeloendndfphd)

### 2. Allow access to local files

TamperMonkey blocks `file://` URLs by default. This must be enabled before the scripts will work.

**Chrome:**
1. Go to `chrome://extensions/`
2. Find TamperMonkey → click **Details**
3. Toggle **"Allow access to file URLs"** on

**Edge:**
1. Go to `edge://extensions/`
2. Find TamperMonkey → click **Details**
3. Toggle **"Allow access to file URLs"** on

### 3. Install the page script

1. Open TamperMonkey → Dashboard → click **+** (New Script)
2. Delete the default template content
3. Paste the contents of `otto-roster.user.js`
4. Save (Ctrl+S)

The `@require` directive in the script header points to the core library on your local machine:
```
// @require  file:///C:/Users/Andrew/Documents/Ottoneu/tampermonkey/otto-statcast-core.js
```
Do not install `otto-statcast-core.js` as a separate TamperMonkey script — it is loaded automatically via `@require`.

## What it does

On the Ottoneu setlineups page (`/setlineups`), four Statcast columns are appended to the batter table:

| Column | Metric | Source |
|---|---|---|
| xwOBA | Expected weighted on-base average | Baseball Savant |
| HH% | Hard hit rate (EV ≥ 95 mph) | Baseball Savant |
| Brrl% | Barrel rate | Baseball Savant |
| K% | Strikeout rate (inverted — lower is better) | Baseball Savant |

**Qualified players** (meet the PA threshold for the percentile leaderboard) show a coloured circle matching the Baseball Savant percentile scale:

| Colour | Percentile |
|---|---|
| Red | 90th+ |
| Orange | 70–89th |
| Yellow | 55–69th |
| Light blue | 45–54th |
| Blue | 30–44th |
| Dark blue | Below 30th |

**Unqualified players** show the raw stat value prefixed with `*` and a tooltip with their PA count.

## Data sources and caching

All data is cached in IndexedDB (`OttoStatcast` database, v5) in the browser. Network fetches only occur when the cache is stale.

| Data | Source | Cache TTL |
|---|---|---|
| Ottoneu ID → MLBAM ID crosswalk | Self-building: name match against players store, then Ottoneu player page → Baseball Savant name search | Permanent (never expires) |
| Percentile rankings (qualified players) | Baseball Savant percentile-rankings CSV | 1 day |
| Raw stats for all players with 1+ PA | Baseball Savant expected_statistics CSV | 1 day |
| On-demand histogram data (unqualified players) | Baseball Savant `/player-services/histogram` API | 1 day |

On first page load, the batter percentile CSV is awaited before circles appear. All other fetches run in the background. Subsequent loads within the TTL window are instant (IndexedDB only).

## Troubleshooting

**`OttoStatcast is not defined`**
The core library failed to load. Check that "Allow access to file URLs" is enabled in the TamperMonkey extension settings (see Installation step 2).

**Columns show `…` indefinitely**
Open DevTools → Console and look for `[OttoStatcast]` log lines. A bulk CSV fetch may have failed or timed out. Check for network errors against `baseballsavant.mlb.com`.

**Columns show `—` for a specific player**
The Ottoneu → MLBAM mapping hasn't been resolved yet. The script will attempt it automatically via name matching and a Baseball Savant search. Use the ✏️ link on the player row to set the mapping manually if automatic resolution fails.

**CSV column headers changed**
Baseball Savant occasionally renames CSV columns. On first fetch, the actual headers are logged to the console as `[OttoStatcast] Percentile CSV headers: ...`. Compare against `PCT_COL` and `EXP_COL` in `otto-statcast-core.js` and update any mismatches.
