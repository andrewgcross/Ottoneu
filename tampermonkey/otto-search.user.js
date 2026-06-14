// ==UserScript==
// @name         Ottoneu – Statcast (Search)
// @namespace    https://ottoneu.fangraphs.com/
// @version      1.0
// @description  Adds Baseball Savant Statcast percentile columns to the Ottoneu player search page
// @match        https://ottoneu.fangraphs.com/*/search*
// @require      file:///C:/Users/Andrew/Documents/Ottoneu/tampermonkey/otto-statcast-core.js
// @require      file:///C:/Users/Andrew/Documents/Ottoneu/tampermonkey/otto-statcast-display.js
// @grant        GM_xmlhttpRequest
// @connect      baseballsavant.mlb.com
// @connect      ottoneu.fangraphs.com
// ==/UserScript==

(async () => {
  'use strict';

  const { buildCell, addPlayerLinks } = OttoStatcastUI;

  const _style = document.createElement('style');
  _style.textContent = [
    '.otto-savant-link, .otto-edit-link { text-decoration: none !important; }',
    'main { max-width: none !important; }',
  ].join('\n');
  document.head.appendChild(_style);

  const COLS = [
    { pctlKey: null, rawKey: 'runs_all', label: 'Runs', type: 'run_value', fmt: v => (v >= 0 ? '+' : '') + v.toFixed(1) },
    { pctlKey: 'xwoba', rawKey: 'xwoba', label: 'xwOBA', inverted: false, fmt: v => v.toFixed(3) },
    { pctlKey: 'hard_hit', rawKey: 'hard_hit_pct', label: 'HH%', inverted: false, fmt: v => v.toFixed(1) + '%' },
    { pctlKey: 'barrel', rawKey: 'barrel_pct', label: 'Brrl%', inverted: false, fmt: v => v.toFixed(1) + '%' },
    { pctlKey: 'k_pct', rawKey: 'k_pct', label: 'K%', inverted: false, fmt: v => v.toFixed(1) + '%' },
  ];

  const leagueId = window.location.pathname.split('/')[1];

  // Extract Ottoneu player ID from a link like /1740/players/12345
  function ottIdFromHref(href) {
    const m = (href || '').match(/\/players\/(\d+)/);
    return m ? m[1] : null;
  }

  // Find the results table — Ottoneu search uses a standard HTML table
  function findResultsTable() {
    const byClass = document.querySelector('table.player-list, table#search-results, table.search-results');
    if (byClass) return byClass;
    // Fallback: any table that contains a player link
    const byLink = [...document.querySelectorAll('table')].find(t =>
      t.querySelector('a[href*="/players/"]')
    );
    if (!byLink) {
      const allTables = document.querySelectorAll('table');
      console.log(`[OttoStatcast] No results table found. Tables on page: ${allTables.length}`,
        [...allTables].map(t => t.id || t.className || '(no id/class)'));
    }
    return byLink || null;
  }

  function addHeaders(table) {
    const headerRow = table.querySelector('thead tr') || table.querySelector('tr:first-child');
    if (!headerRow || headerRow.querySelector('.otto-stat-header')) return;
    COLS.forEach(col => {
      const th = document.createElement('th');
      th.textContent = col.label;
      th.className = 'otto-stat-header';
      th.title = col.type === 'run_value'
        ? `${col.label}: Swing/Take Run Value (qualified batters only)`
        : `Statcast: ${col.label} · circle = percentile · * = raw (unqualified)`;
      th.style.cssText = 'text-align:center;font-size:11px;padding:2px 5px;white-space:nowrap;cursor:help;';
      headerRow.appendChild(th);
    });
  }

  function processRows(table) {
    addHeaders(table);

    for (const row of table.querySelectorAll('tbody tr')) {
      // Sentinel prevents re-processing when the observer fires on our own DOM additions
      if (row.dataset.ottoProcessed) continue;

      const playerLink = row.querySelector('a[href*="/players/"]');
      if (!playerLink) continue;

      const ottId = ottIdFromHref(playerLink.getAttribute('href'));
      if (!ottId) continue;

      row.dataset.ottoProcessed = '1'; // mark before async work
      const playerName = playerLink.textContent.trim() || null;

      const placeholders = COLS.map(() => {
        const td = document.createElement('td');
        td.style.cssText = 'text-align:center;font-size:11px;color:#ccc;vertical-align:middle;';
        td.textContent = '…';
        row.appendChild(td);
        return td;
      });

      OttoStatcast.getStatsOrFetch(ottId, leagueId, playerName, 'batter')
        .then(stats => {
          COLS.forEach((col, i) => placeholders[i].replaceWith(buildCell(stats, col)));
          addPlayerLinks(playerLink.parentElement, playerName, ottId, stats?.mlbam_id || null);
        })
        .catch(err => {
          console.warn(`[OttoStatcast] search otto_id ${ottId}:`, err);
          placeholders.forEach(td => { td.textContent = '?'; td.style.color = '#c00'; });
          addPlayerLinks(playerLink.parentElement, playerName, ottId, null);
        });
    }
  }

  await OttoStatcast.init();

  const table = findResultsTable();
  if (table) processRows(table);

  // Re-process when search results are updated via AJAX.
  // Debounced so rapid DOM mutations (e.g. us adding tds) collapse into one call.
  let _debounceTimer = null;
  const observer = new MutationObserver(() => {
    clearTimeout(_debounceTimer);
    _debounceTimer = setTimeout(() => {
      const t = findResultsTable();
      if (t) processRows(t);
    }, 150);
  });
  observer.observe(document.body, { childList: true, subtree: true });
})();
