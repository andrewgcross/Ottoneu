// ==UserScript==
// @name         Ottoneu – Statcast (Lineup)
// @namespace    https://ottoneu.fangraphs.com/
// @version      2.0
// @description  Adds Baseball Savant Statcast percentile columns to the setlineups batter table
// @match        https://ottoneu.fangraphs.com/*/setlineups*
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
  _style.textContent = '.otto-savant-link, .otto-edit-link { text-decoration: none !important; }';
  document.head.appendChild(_style);

  const _mainEl = document.querySelector('main');
  if (_mainEl) {
    const _currentMax = parseInt(getComputedStyle(_mainEl).maxWidth, 10);
    _mainEl.style.maxWidth = (isNaN(_currentMax) ? 1300 : _currentMax + 100) + 'px';
  }

  const COLS = [
    { pctlKey: null, rawKey: 'runs_all', label: 'Runs', type: 'run_value', fmt: v => (v >= 0 ? '+' : '') + v.toFixed(1) },
    { pctlKey: 'xwoba', rawKey: 'xwoba', label: 'xwOBA', inverted: false, fmt: v => v.toFixed(3) },
    { pctlKey: 'hard_hit', rawKey: 'hard_hit_pct', label: 'HH%', inverted: false, fmt: v => v.toFixed(1) + '%' },
    { pctlKey: 'barrel', rawKey: 'barrel_pct', label: 'Brrl%', inverted: false, fmt: v => v.toFixed(1) + '%' },
    { pctlKey: 'k_pct', rawKey: 'k_pct', label: 'K%', inverted: false, fmt: v => v.toFixed(1) + '%' },
  ];

  function addHeaders(table) {
    const row = table.querySelector('thead tr') || table.querySelector('tr:first-child');
    if (!row) return;
    COLS.forEach(col => {
      const th = document.createElement('th');
      th.textContent = col.label;
      th.title = col.type === 'run_value'
        ? `${col.label}: Swing/Take Run Value (qualified batters only)`
        : `Statcast: ${col.label} · circle = percentile · * = raw (unqualified)`;
      th.style.cssText = 'text-align:center;font-size:11px;padding:2px 5px;white-space:nowrap;cursor:help;';
      row.appendChild(th);
    });
  }

  await OttoStatcast.init();

  const leagueId = window.location.pathname.split('/')[1];
  const table = document.querySelector('table.lineup-table.batter');
  if (!table) return;

  addHeaders(table);

  for (const row of table.querySelectorAll('tbody tr')) {
    if (row.hasAttribute('style')) continue;

    const posTd = row.querySelector('td[data-position]');
    const nameTd = row.querySelector('td.player-name');
    const ottId = posTd?.getAttribute('data-player-id');
    const playerName = nameTd?.querySelector('a')?.textContent?.trim() || null;

    if (!ottId || nameTd?.classList.contains('empty_slot')) {
      COLS.forEach(() => {
        const td = document.createElement('td');
        td.style.cssText = 'text-align:center;font-size:11px;color:#aaa;';
        td.textContent = '—';
        row.appendChild(td);
      });
      continue;
    }

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
        const bio = row.querySelector('.lineup-player-bio');
        addPlayerLinks(bio, playerName, ottId, stats?.mlbam_id || null);
      })
      .catch(err => {
        console.warn(`[OttoStatcast] otto_id ${ottId}:`, err);
        placeholders.forEach(td => { td.textContent = '?'; td.style.color = '#c00'; });
        const bio = row.querySelector('.lineup-player-bio');
        addPlayerLinks(bio, playerName, ottId, null);
      });
  }
})();
