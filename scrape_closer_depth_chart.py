"""
Scrapes https://www.fangraphs.com/roster-resource/closer-depth-chart

The page renders one table per team. A dropdown switches columns 12+
between "Results" (ERA, K%, etc.) and "Arsenal" (vFA, FA%, etc.) via AJAX.

Strategy:
  1. Load page → scrape all 30 teams for Results view
  2. Click the Arsenal dropdown option → wait for AJAX → scrape all 30 again
  3. Export as two sheets in an Excel workbook

Column headers:
  - Pitcher Usage date columns: "M/dd" format  (e.g. "5/28")
  - All other columns: data-stat attribute text (e.g. "ERA", "vFA", "K%")

Run:
    pip install playwright pandas openpyxl
    playwright install chromium
    python scrape_closer_depth_chart.py
"""

import datetime
import sys

import pandas as pd
from playwright.sync_api import sync_playwright

URL = "https://www.fangraphs.com/roster-resource/closer-depth-chart"
OUTPUT_FILE = f"closer_depth_chart_{datetime.date.today()}.xlsx"


def build_headers(page, thead_el) -> list[str]:
    """
    Extract column header names from the super-header-spacer <tr> only.
    - Date columns (data-col-id="specialBullpenUsage"): use the M/dd date text
    - All other columns: use data-stat attribute directly
    Uses JS evaluation for reliable DOM access on ElementHandles.
    """
    return page.evaluate("""(thead) => {
        const tr = thead.querySelector('tr.super-header-spacer') || thead.querySelector('tr');
        return [...tr.querySelectorAll('th')].map(th => {
            const colId = th.getAttribute('data-col-id') || '';
            const stat  = th.getAttribute('data-stat')   || '';
            if (colId === 'specialBullpenUsage') {
                const divs = th.querySelectorAll('div.game-bullpen-usage > div');
                return divs.length >= 2 ? divs[1].textContent.trim() : stat;
            }
            return stat || colId || '';
        });
    }""", thead_el)


TAG_SYMBOLS = {
    "Reliever On The Rise": "↑",
    "On The Hot Seat": "↓",
}


def parse_row(tr_el) -> tuple[list[str], str, str]:
    """
    Extract cell values from a <tr>.
    Also returns the player tag symbol and the FanGraphs player ID.
    """
    cells = tr_el.query_selector_all("td")
    values = []
    tag = ""
    player_id = ""
    for td in cells:
        stat = td.get_attribute("data-stat") or ""
        if stat == "PLAYER":
            badge = td.query_selector("[data-tag]")
            if badge:
                tag = TAG_SYMBOLS.get(badge.get_attribute("data-tag") or "", "")
            link = td.query_selector("a[href]")
            if link:
                # href format: /players/name/21520/stats/pitching → segment index 3
                parts = (link.get_attribute("href") or "").split("/")
                player_id = parts[3] if len(parts) > 3 else ""
        outcome = td.get_attribute("data-outcome")
        if outcome is not None:
            span = td.query_selector("span")
            values.append(span.inner_text().strip() if span else "")
        else:
            values.append(td.inner_text().strip())
    return values, tag, player_id


def scrape_all_grids(page) -> pd.DataFrame:
    """
    Read all 30 fg-data-grid sections. In each section, table[0] is the
    currently visible (active) table.
    """
    grids = page.query_selector_all("div.fg-data-grid")
    all_rows: list[list[str]] = []
    headers: list[str] = []

    for grid in grids:
        tables = grid.query_selector_all("table")
        if not tables:
            continue
        table = tables[0]  # always the currently active/visible table

        thead = table.query_selector("thead")
        tbody = table.query_selector("tbody")
        if not thead or not tbody:
            continue

        if not headers:
            raw = build_headers(page, thead)
            # Insert "PlayerID" and "Tag" between PLAYER (index 1) and THR (index 2)
            headers = raw[:2] + ["PlayerID", "Tag"] + raw[2:]

        for tr in tbody.query_selector_all("tr"):
            values, tag, player_id = parse_row(tr)
            row = values[:2] + [player_id, tag] + values[2:]
            all_rows.append(row)

    if not all_rows:
        return pd.DataFrame()

    max_cols = max(len(r) for r in all_rows)
    padded = [r + [""] * (max_cols - len(r)) for r in all_rows]

    col_count = max_cols
    if len(headers) < col_count:
        headers = headers + [f"col_{i}" for i in range(len(headers), col_count)]
    elif len(headers) > col_count:
        headers = headers[:col_count]

    return pd.DataFrame(padded, columns=headers)


def main():
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        ).new_page()

        print(f"Loading {URL} ...")
        page.goto(URL, wait_until="networkidle", timeout=60_000)
        page.wait_for_timeout(2_000)

        # --- Results view (default) ---
        print("Scraping Results view ...")
        results_df = scrape_all_grids(page)
        print(f"  {len(results_df)} rows x {len(results_df.columns)} cols")
        if not results_df.empty:
            print(f"  Columns: {list(results_df.columns)}")

        # --- Switch to Arsenal via AJAX ---
        print("Clicking Arsenal option ...")
        # A MUI modal may be covering the page; remove it before interacting.
        page.evaluate("""
            document.querySelectorAll('.MuiModal-root, .MuiDialog-root, .MuiBackdrop-root')
                .forEach(el => el.remove());
        """)
        page.wait_for_timeout(200)

        # Open the first team's dropdown then select Arsenal.
        # One click changes all 30 teams simultaneously.
        # Use JS clicks to bypass any remaining overlay interception.
        page.evaluate("""
            const dropdown = document.querySelector('div.fg-dropdown.rr-header__dropdown');
            if (dropdown) dropdown.click();
        """)
        page.wait_for_timeout(300)
        page.evaluate("""
            const li = document.querySelector("li[data-value='arsenal']");
            if (li) li.click();
        """)
        # Wait for AJAX responses to settle
        page.wait_for_load_state("networkidle", timeout=15_000)
        page.wait_for_timeout(1_000)

        # --- Arsenal view ---
        print("Scraping Arsenal view ...")
        arsenal_df = scrape_all_grids(page)
        print(f"  {len(arsenal_df)} rows x {len(arsenal_df.columns)} cols")
        if not arsenal_df.empty:
            print(f"  Columns: {list(arsenal_df.columns)}")

        browser.close()

    if results_df.empty or arsenal_df.empty:
        print("ERROR: no data scraped.", file=sys.stderr)
        sys.exit(1)

    # The first 14 columns are identical in both views (TEAM…last6IP, plus PlayerID+Tag).
    # Append only the Arsenal-specific columns (14 onwards) to the Results frame.
    SHARED_COLS = 14
    combined_df = pd.concat(
        [results_df, arsenal_df.iloc[:, SHARED_COLS:]],
        axis=1,
    )

    # Last 6 Days totals sit before SHARED_COLS but are also numeric.
    for col in ["last6P", "last6IP"]:
        combined_df[col] = pd.to_numeric(combined_df[col], errors="coerce")

    # Convert all numeric stat columns (G onwards, index 14+) from string to float.
    # Strip "%" before converting so percentage columns are stored as plain numbers
    # (e.g. "9.7%" → 9.7) rather than NaN.
    for col in combined_df.columns[SHARED_COLS:]:
        combined_df[col] = (
            combined_df[col]
            .str.replace("%", "", regex=False)
            .str.strip()
            .pipe(pd.to_numeric, errors="coerce")
        )

    print(f"\nCombined: {len(combined_df)} rows x {len(combined_df.columns)} cols")
    print(f"Columns: {list(combined_df.columns)}")

    print(f"\nWriting {OUTPUT_FILE} ...")
    with pd.ExcelWriter(OUTPUT_FILE, engine="openpyxl") as writer:
        combined_df.to_excel(writer, sheet_name="Closers", index=False)

    print("Done.")


if __name__ == "__main__":
    main()
