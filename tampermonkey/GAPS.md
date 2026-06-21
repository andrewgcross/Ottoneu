# Known Gaps & Future Work

## 1. Run values not yet sourced (Batting, Baserunning, Fielding)

The `#percentile-sliders` div on Savant player pages (which contains Batting Run Value,
Baserunning Run Value, Fielding Run Value, and LA Sweet-Spot %) is React-rendered and
not accessible via static HTML fetch. The `#percent_rank` table that IS in the static HTML
contains year-over-year season stats, not percentile rankings.

**To fix:** Open DevTools → Network → filter XHR/Fetch on a Savant player page and identify
the endpoint the React component calls to populate `#percentile-sliders`. It is likely under
`/player-services/`. Once found, add it as an on-demand fetch inside `showSavantOverlay`
in `otto-statcast.user.js`.

---

## 2. LA Sweet-Spot % not in bulk percentile CSV

The percentile-rankings CSV does not include `sweet_spot_percent`. The metric IS shown
on the Savant player page (typically 86th percentile range for good contact hitters) but
has no column in the download we use. It would only be available via the run-values
endpoint described in Gap #1.

---

## 3. Name collision risk in Savant search fallback

`_resolveViaPages()` searches Baseball Savant by last name and picks the first result whose
first name starts with the same 3 letters. This is fragile for:
- Common surnames (e.g. "Martinez", "Ramirez", "Garcia") with multiple active players
- Players whose display name differs from their Savant registration name
- Name suffixes (Jr./III) that may or may not appear in Savant search results

**Mitigation:** The ✏️ manual override link on every player row lets you set the MLBAM ID
directly. Once set, it's cached permanently and the search fallback never runs again for
that player.

---

## 4. Barrel % unavailable via histogram for truly new players

The histogram endpoint (`/player-services/histogram?fieldType=api_h_launch_speed`) bins
by exit velocity only. Barrel rate requires EV + launch angle simultaneously — not
derivable from EV buckets alone. Players in the expected stats CSV (1+ PA) do have
barrel% from that source. Only players with 0 PA (prospect callups, newly acquired)
would lack barrel data, and they'd also lack most other metrics.

---

## 5. CSV column names — verified 2026-06-13

**Percentile CSV** (`percentile-rankings?type=batter`):
`player_name, player_id, year, xwoba, xba, xslg, xiso, xobp, brl_percent, exit_velocity,
max_ev, hard_hit_percent, k_percent, bb_percent, whiff_percent, chase_percent, arm_strength,
sprint_speed, oaa, bat_speed, squared_up_rate, swing_length`

**Expected stats CSV** (`expected_statistics?min=1`):
`last_name, first_name, player_id, year, pa, bip, ba, est_ba, est_ba_minus_ba_diff, slg,
est_slg, est_slg_minus_slg_diff, woba, est_woba, est_woba_minus_woba_diff`

Note: expected stats CSV contains only xBA/xSLG/xwOBA differentials — no EV, barrel%,
hard hit%, whiff%, K%, or BB%. Those are percentile-circle-only for qualified players.

Note: `arm_strength` and `swing_length` are stored in the `pctl_${year}` object but are
not currently displayed in the popup (`POPUP_SECTIONS` in `otto-statcast.user.js`).
Arm strength is relevant for outfielders and catchers; could be added to a Fielding section.

---

## 6. Pitcher columns on search page not yet written

The setlineups pitcher table (`table.lineup-table.pitcher`) is covered with columns:
xwOBA, xISO, Brl%, EV, Whiff%, FB Vel. Still missing:

- **Search page** — pitcher results could use PITCHER_COLS but requires detecting player
  type per row, which isn't currently available in the search result HTML.

**FB Vel column name needs verification.** Currently mapped to `fastball_avg_speed` in
`PCT_COL`. On first load of a setlineups page the pitcher percentile CSV headers are
logged as `[OttoStatcast] Percentile CSV headers: ...` — confirm `fastball_avg_speed`
appears and update `PCT_COL.fb_vel` in `otto-statcast.user.js` if the column name differs.

---

## 7. Remaining high-value page targets

`otto-statcast.user.js` currently covers setlineups, search, and individual player pages. Still missing:

- **Trade analyser** — comparing player values across teams
- **Roster add page** (`/roster/add`) — if separate from `/search`
