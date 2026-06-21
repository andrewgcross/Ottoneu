// ==UserScript==
// @name         Ottoneu – Statcast
// @namespace    https://ottoneu.fangraphs.com/
// @version      1.0
// @description  Adds Baseball Savant Statcast percentile columns to Ottoneu setlineups and search pages
// @match        https://ottoneu.fangraphs.com/*/setlineups*
// @match        https://ottoneu.fangraphs.com/*/search*
// @grant        GM_xmlhttpRequest
// @connect      baseballsavant.mlb.com
// @connect      ottoneu.fangraphs.com
// ==/UserScript==

// ── Core library ──────────────────────────────────────────────────────────────

var OttoStatcast = (() => { // eslint-disable-line no-var
  'use strict';

  const DB_NAME = 'OttoStatcast';
  const DB_VERSION = 5;
  const YEAR = new Date().getFullYear();

  const TTL = {
    BULK: 1 * 86400e3, // 1 day
    ONDEMAND: 1 * 86400e3, // 1 day
  };

  // ── Column name maps ──────────────────────────────────────────────────────────

  const PCT_COL = { // percentile-rankings CSV (headers verified 2026-06-13)
    id: 'player_id',
    name: 'player_name',
    xba: 'xba',
    xslg: 'xslg',
    xwoba: 'xwoba',
    xobp: 'xobp',
    xiso: 'xiso',
    ev: 'exit_velocity',
    barrel: 'brl_percent',
    hard_hit: 'hard_hit_percent',
    k_pct: 'k_percent',
    bb_pct: 'bb_percent',
    whiff: 'whiff_percent',
    chase: 'chase_percent',
    sprint: 'sprint_speed',
    bat_speed: 'bat_speed',
    squared_up: 'squared_up_rate',
    oaa: 'oaa',
  };

  const ST_COL = { // swing-take leaderboard CSV
    player_id: 'player_id',
    runs_all: 'runs_all',
  };

  const EXP_COL = { // expected_statistics CSV (min=1, headers verified 2026-06-13)
    id: 'player_id',
    last: 'last_name',
    first: 'first_name',
    pa: 'pa',
    xba: 'est_ba',
    xslg: 'est_slg',
    xwoba: 'est_woba',
  };

  // ── IndexedDB ─────────────────────────────────────────────────────────────────

  let _db = null;

  function _open() {
    if (_db) return Promise.resolve(_db);
    return new Promise((res, rej) => {
      const r = indexedDB.open(DB_NAME, DB_VERSION);
      r.onupgradeneeded = e => {
        const d = e.target.result;
        const tx = e.target.transaction;

        // v3: one-time removal of old file-based crosswalk stores.
        // Gated to oldVersion < 3 so subsequent bumps never touch otto_crosswalk
        // (it holds manually entered mappings that must survive upgrades).
        if (e.oldVersion < 3) {
          if (d.objectStoreNames.contains('crosswalk'))
            d.deleteObjectStore('crosswalk');
          if (d.objectStoreNames.contains('otto_crosswalk'))
            d.deleteObjectStore('otto_crosswalk');
          d.createObjectStore('otto_crosswalk', { keyPath: 'otto_id' });
        }

        if (!d.objectStoreNames.contains('players'))
          d.createObjectStore('players', { keyPath: 'mlbam_id' });
        if (!d.objectStoreNames.contains('meta'))
          d.createObjectStore('meta', { keyPath: 'key' });
        if (!d.objectStoreNames.contains('otto_crosswalk'))
          d.createObjectStore('otto_crosswalk', { keyPath: 'otto_id' });

        // v4: corrected column names (brl_percent, exit_velocity, etc.)
        // v5: added squared_up, oaa columns
        // Both purge percentile meta keys to force a re-download.
        if (e.oldVersion < 5 && d.objectStoreNames.contains('meta')) {
          const meta = tx.objectStore('meta');
          meta.delete(`pctl_batter_${YEAR}`);
          meta.delete(`pctl_pitcher_${YEAR}`);
        }
      };
      r.onsuccess = e => { _db = e.target.result; res(_db); };
      r.onerror = e => rej(e.target.error);
    });
  }

  async function _get(store, key) {
    const db = await _open();
    return new Promise((res, rej) => {
      const r = db.transaction(store, 'readonly').objectStore(store).get(key);
      r.onsuccess = () => res(r.result);
      r.onerror = () => rej(r.error);
    });
  }

  async function _put(store, val) {
    const db = await _open();
    return new Promise((res, rej) => {
      const r = db.transaction(store, 'readwrite').objectStore(store).put(val);
      r.onsuccess = () => res();
      r.onerror = () => rej(r.error);
    });
  }

  async function _putBatch(store, vals) {
    if (!vals.length) return;
    const db = await _open();
    return new Promise((res, rej) => {
      const tx = db.transaction(store, 'readwrite');
      const s = tx.objectStore(store);
      for (const v of vals) s.put(v);
      tx.oncomplete = res;
      tx.onerror = () => rej(tx.error);
    });
  }

  // ── HTTP ──────────────────────────────────────────────────────────────────────

  function _fetch(url) {
    return new Promise((res, rej) => {
      GM_xmlhttpRequest({
        method: 'GET',
        url,
        timeout: 30000,
        onload: r => r.status >= 200 && r.status < 300
          ? res(r.responseText)
          : rej(new Error(`HTTP ${r.status}: ${url}`)),
        onerror: rej,
        ontimeout: () => rej(new Error(`Timeout: ${url}`)),
      });
    });
  }

  // ── CSV ───────────────────────────────────────────────────────────────────────

  function _csv(text) {
    const lines = text.trim().split(/\r?\n/);
    if (lines.length < 2) return [];
    const hdrs = _csvLine(lines[0]);
    return lines.slice(1).filter(l => l.trim()).map(l => {
      const vals = _csvLine(l);
      const obj = {};
      hdrs.forEach((h, i) => { obj[h] = vals[i] ?? null; });
      return obj;
    });
  }

  function _csvLine(line) {
    const out = []; let cur = '', inQ = false;
    for (const c of line) {
      if (c === '"') inQ = !inQ;
      else if (c === ',' && !inQ) { out.push(cur.trim()); cur = ''; }
      else cur += c;
    }
    out.push(cur.trim());
    return out;
  }

  // ── Name normalisation ────────────────────────────────────────────────────────
  // Converts both "Last, First" (CSV) and "First Last" (DOM) to a comparable key.

  function _normName(name) {
    if (!name) return '';
    // Reorder "Last, First" → "First Last" before stripping punctuation,
    // otherwise the comma is stripped and the reorder never fires.
    if (name.includes(',')) {
      const [last, first] = name.split(',', 2).map(s => s.trim());
      name = `${first} ${last}`;
    }
    return name.toLowerCase().replace(/[^a-z0-9 ]/g, ' ').replace(/\s+/g, ' ').trim();
  }

  // ── Otto crosswalk: self-building Ottoneu ID → MLBAM ID ──────────────────────

  async function _ottToMlbam(ottId, playerName, leagueId) {
    const cached = await _get('otto_crosswalk', String(ottId));
    if (cached) return cached.mlbam_id;

    if (playerName) {
      const mlbamId = await _scanPlayersByName(playerName);
      if (mlbamId) {
        await _put('otto_crosswalk', { otto_id: String(ottId), mlbam_id: mlbamId, source: 'name' });
        console.log(`[OttoStatcast] Resolved ${playerName} (otto ${ottId}) by name → mlbam ${mlbamId}`);
        return mlbamId;
      }
    }

    return _resolveViaPages(ottId, playerName, leagueId);
  }

  async function _scanPlayersByName(playerName) {
    const target = _normName(playerName);
    const db = await _open();
    return new Promise((res, rej) => {
      const req = db.transaction('players', 'readonly').objectStore('players').openCursor();
      req.onsuccess = e => {
        const cursor = e.target.result;
        if (!cursor) { res(null); return; }
        if (_normName(cursor.value.name) === target) { res(cursor.value.mlbam_id); return; }
        cursor.continue();
      };
      req.onerror = () => rej(req.error);
    });
  }

  // Fallback: fetch Ottoneu player page to confirm the player name / get FG ID,
  // then search Baseball Savant by name to get the MLBAM ID directly.
  // FanGraphs pages embed Savant data via JavaScript and don't expose the MLBAM ID
  // in static HTML, so searching Savant by name is more reliable.
  async function _resolveViaPages(ottId, playerName, leagueId) {
    console.log(`[OttoStatcast] Resolving otto_id ${ottId} via Savant search…`);

    let resolvedName = playerName;
    let fgId = null;

    if (!resolvedName || true) { // always fetch to also capture FG ID for logging
      try {
        const resp = await fetch(`https://ottoneu.fangraphs.com/${leagueId}/players/${ottId}`);
        const html = await resp.text();
        const fgMatch = html.match(/statss\.aspx\?playerid=(\d+)/i);
        if (fgMatch) fgId = fgMatch[1];
        if (!resolvedName) {
          const titleMatch = html.match(/<h1[^>]*>([^<]+)</i);
          if (titleMatch) resolvedName = titleMatch[1].trim();
        }
      } catch (e) {
        console.warn(`[OttoStatcast] Ottoneu player page failed for otto_id ${ottId}:`, e);
      }
    }

    if (!resolvedName) {
      console.warn(`[OttoStatcast] No player name available for otto_id ${ottId}`);
      return null;
    }

    const parts = resolvedName.trim().split(' ');
    const firstName = parts[0] || '';
    const lastName = parts.slice(1).join(' ') || resolvedName;
    const term = encodeURIComponent(lastName);

    let results;
    try {
      const json = await _fetch(`https://baseballsavant.mlb.com/player/search-all-players?term=${term}`);
      results = JSON.parse(json);
    } catch (e) {
      console.warn(`[OttoStatcast] Savant search failed for "${resolvedName}":`, e);
      return null;
    }

    if (!Array.isArray(results) || !results.length) {
      console.warn(`[OttoStatcast] No Savant results for "${resolvedName}"`);
      return null;
    }

    if (results[0]) console.log('[OttoStatcast] Savant search result shape:', Object.keys(results[0]).join(', '));

    const normFirst = firstName.toLowerCase().slice(0, 3);
    const pick = results.find(p => {
      const pFirst = (p.first_name || p.name_first || p.firstname || '').toLowerCase();
      return pFirst.startsWith(normFirst);
    }) || results[0];

    const mlbamId = String(pick.id || pick.mlbam || pick.player_id || pick.mlbam_id || '');
    if (!mlbamId || mlbamId === 'undefined') {
      console.warn(`[OttoStatcast] Could not extract MLBAM from Savant result for "${resolvedName}":`, pick);
      return null;
    }

    await _put('otto_crosswalk', { otto_id: String(ottId), mlbam_id: mlbamId, fg_id: fgId, source: 'savant_search' });
    console.log(`[OttoStatcast] Resolved "${resolvedName}" (otto ${ottId}) → mlbam ${mlbamId}`);
    return mlbamId;
  }

  // ── Bulk: percentile rankings ─────────────────────────────────────────────────

  async function _refreshPercentiles(type = 'batter', year = YEAR) {
    const mkey = `pctl_${type}_${year}`;
    const m = await _get('meta', mkey);
    if (m && Date.now() - m.v < TTL.BULK) return;

    const csvType = type === 'batter' ? 'batter' : 'pitchers';
    const url = `https://baseballsavant.mlb.com/leaderboard/percentile-rankings` +
                `?type=${csvType}&year=${year}&team=&csv=true`;
    console.log(`[OttoStatcast] Fetching ${year} ${type} percentile rankings…`);

    const rows = _csv(await _fetch(url));
    if (rows[0]) console.log('[OttoStatcast] Percentile CSV headers:', Object.keys(rows[0]).join(', '));

    const C = PCT_COL;
    const now = Date.now();
    const updates = [];

    for (const r of rows) {
      if (!r[C.id]) continue;
      const existing = await _get('players', String(r[C.id])) || {};
      updates.push({
        ...existing,
        mlbam_id: String(r[C.id]),
        name: r[C.name] || existing.name || '',
        player_type: type,
        [`pctl_${year}`]: {
          xba: _i(r[C.xba]),
          xslg: _i(r[C.xslg]),
          xwoba: _i(r[C.xwoba]),
          xobp: _i(r[C.xobp]),
          xiso: _i(r[C.xiso]),
          ev: _i(r[C.ev]),
          barrel: _i(r[C.barrel]),
          hard_hit: _i(r[C.hard_hit]),
          k_pct: _i(r[C.k_pct]),
          bb_pct: _i(r[C.bb_pct]),
          whiff: _i(r[C.whiff]),
          chase: _i(r[C.chase]),
          sprint: _i(r[C.sprint]),
          bat_speed: _i(r[C.bat_speed]),
          squared_up: _i(r[C.squared_up]),
          oaa: _i(r[C.oaa]),
        },
        pctl_at: now,
      });
    }

    await _putBatch('players', updates);
    await _put('meta', { key: mkey, v: now });
    console.log(`[OttoStatcast] Percentiles: ${updates.length} ${type} records for ${year}`);
  }

  // ── Bulk: expected stats (min=1) ──────────────────────────────────────────────

  async function _refreshExpected(type = 'batter', year = YEAR) {
    const mkey = `exp_${type}_${year}`;
    const m = await _get('meta', mkey);
    if (m && Date.now() - m.v < TTL.BULK) return;

    const csvType = type === 'batter' ? 'batter' : 'pitcher';
    const url = `https://baseballsavant.mlb.com/leaderboard/expected_statistics` +
                `?type=${csvType}&year=${year}&position=&team=&min=1&csv=true`;
    console.log(`[OttoStatcast] Fetching ${year} ${type} expected stats (min=1)…`);

    const rows = _csv(await _fetch(url));

    const C = EXP_COL;
    const now = Date.now();
    const updates = [];

    for (const r of rows) {
      if (!r[C.id]) continue;
      const existing = await _get('players', String(r[C.id])) || {};
      updates.push({
        ...existing,
        mlbam_id: String(r[C.id]),
        name: existing.name || `${r[C.first] || ''} ${r[C.last] || ''}`.trim(),
        player_type: type,
        [`raw_${year}`]: {
          pa: _i(r[C.pa]),
          xba: _f(r[C.xba]),
          xslg: _f(r[C.xslg]),
          xwoba: _f(r[C.xwoba]),
        },
        raw_at: now,
      });
    }

    await _putBatch('players', updates);
    await _put('meta', { key: mkey, v: now });
    console.log(`[OttoStatcast] Expected stats: ${updates.length} ${type} records for ${year}`);
  }

  // ── Bulk: swing-take run values ───────────────────────────────────────────────

  async function _refreshSwingTake(year = YEAR) {
    const mkey = `st_batter_${year}`;
    const m = await _get('meta', mkey);
    if (m && Date.now() - m.v < TTL.BULK) return;

    const url = `https://baseballsavant.mlb.com/leaderboard/swing-take` +
      `?year=${year}&team=&leverage=Neutral&group=Batter&type=All&sub_type=null&min=q&csv=true`;
    console.log(`[OttoStatcast] Fetching ${year} swing-take run values…`);

    const rows = _csv(await _fetch(url));
    const C = ST_COL;
    const now = Date.now();
    const updates = [];

    for (const r of rows) {
      if (!r[C.player_id]) continue;
      const existing = await _get('players', String(r[C.player_id])) || {};
      updates.push({
        ...existing,
        mlbam_id: String(r[C.player_id]),
        [`st_${year}`]: { runs_all: _f(r[C.runs_all]) },
        st_at: now,
      });
    }

    await _putBatch('players', updates);
    await _put('meta', { key: mkey, v: now });
    console.log(`[OttoStatcast] Swing-take: ${updates.length} records for ${year}`);
  }

  // ── On-demand: histogram stats for unqualified players ───────────────────────

  async function _histStats(mlbamId) {
    const url = `https://baseballsavant.mlb.com/player-services/histogram` +
      `?playerId=${mlbamId}&fieldType=api_h_launch_speed&hand=&size=5&season=&event=pitch_count&pitchType=`;
    const buckets = JSON.parse(await _fetch(url));

    let bbe = 0, evS = 0, laS = 0, xwS = 0, xbaS = 0, xslgS = 0, hhBBE = 0;
    for (const b of buckets) {
      const n = parseFloat(b.bbe) || 0;
      if (!n) continue;
      bbe += n;
      if (b.ev != null) evS += parseFloat(b.ev) * n;
      if (b.la != null) laS += parseFloat(b.la) * n;
      if (b.xwoba != null) xwS += parseFloat(b.xwoba) * n;
      if (b.xba != null) xbaS += parseFloat(b.xba) * n;
      if (b.xslg != null) xslgS += parseFloat(b.xslg) * n;
      if (parseFloat(b.histogram_value) >= 95) hhBBE += n;
    }
    if (!bbe) return null;
    return {
      ev: evS / bbe,
      la: laS / bbe,
      xwoba: xwS / bbe,
      xba: xbaS / bbe,
      xslg: xslgS / bbe,
      hard_hit_pct: (hhBBE / bbe) * 100,
      bbe,
    };
  }

  async function _fetchOnDemand(mlbamId, name, type = 'batter') {
    const existing = await _get('players', String(mlbamId)) || {};
    if (existing.ondemand_at && Date.now() - existing.ondemand_at < TTL.ONDEMAND) return existing;

    let histData = null;
    try { histData = await _histStats(mlbamId); }
    catch (e) { console.warn('[OttoStatcast] Histogram failed:', e); }

    const rec = {
      ...existing,
      mlbam_id: String(mlbamId),
      [`ondemand_${YEAR}`]: histData,
      ondemand_at: Date.now(),
    };
    await _put('players', rec);
    return rec;
  }

  // ── Public API ────────────────────────────────────────────────────────────────

  async function getStats(ottId) {
    const cw = await _get('otto_crosswalk', String(ottId));
    if (!cw) return null;

    const p = await _get('players', cw.mlbam_id);
    if (!p) return null;

    const percentiles = p[`pctl_${YEAR}`] || null;
    const rawCSV = p[`raw_${YEAR}`] || {};
    const rawOnDemand = p[`ondemand_${YEAR}`] || {};
    const rawST = p[`st_${YEAR}`] || {};
    const merged = { ...rawOnDemand, ...rawCSV, ...rawST };
    const raw = Object.values(merged).some(v => v != null) ? merged : null;

    return {
      mlbam_id: cw.mlbam_id,
      otto_id: String(ottId),
      name: p.name,
      qualified: !!percentiles,
      percentiles,
      raw,
    };
  }

  async function setOttoMapping(ottId, mlbamId) {
    await _put('otto_crosswalk', { otto_id: String(ottId), mlbam_id: String(mlbamId), source: 'manual' });
    console.log(`[OttoStatcast] Manual mapping saved: otto ${ottId} → mlbam ${mlbamId}`);
  }

  async function getStatsOrFetch(ottId, leagueId, playerName, type = 'batter') {
    const mlbamId = await _ottToMlbam(ottId, playerName, leagueId);
    if (!mlbamId) return null;

    const p = await _get('players', mlbamId);
    const isQualified = p && p[`pctl_${YEAR}`];
    const hasOnDemand = p && p[`ondemand_${YEAR}`];

    if (!isQualified && !hasOnDemand) {
      await _fetchOnDemand(mlbamId, p?.name || playerName, type);
    } else if (!p) {
      await _fetchOnDemand(mlbamId, playerName, type);
    }

    return getStats(ottId);
  }

  async function init() {
    await _open();
    await Promise.allSettled([
      _refreshPercentiles('batter'),
      _refreshSwingTake(),
    ]);
    _refreshPercentiles('pitcher').catch(e => console.error('[OttoStatcast] Pitcher pctl:', e));
    _refreshExpected('batter').catch(e => console.error('[OttoStatcast] Batter exp:', e));
    _refreshExpected('pitcher').catch(e => console.error('[OttoStatcast] Pitcher exp:', e));
  }

  function _i(v) { const n = parseInt(v, 10); return isNaN(n) ? null : n; }
  function _f(v) { const n = parseFloat(v); return isNaN(n) ? null : n; }

  const debug = {
    query: (store, key) => _get(store, key),
    otto: (ottId) => _get('otto_crosswalk', String(ottId)),
    player: (mlbamId) => _get('players', String(mlbamId)),
    meta: (key) => _get('meta', key),
    nameMatch: (name) => _scanPlayersByName(name),
  };

  return { init, getStats, getStatsOrFetch, setOttoMapping, fetchHtml: _fetch, debug };
})();

// ── Display library ───────────────────────────────────────────────────────────

var OttoStatcastUI = (() => { // eslint-disable-line no-var
  'use strict';

  function pctlColor(rank, inverted) {
    const p = inverted ? 100 - rank : rank;
    if (p > 95) return { bg: 'rgb(216,33,41)', text: '#fff', border: false };
    if (p > 77) return { bg: 'rgb(229,107,112)', text: '#333', border: false };
    if (p > 60) return { bg: 'rgb(242,181,184)', text: '#333', border: false };
    if (p > 42) return { bg: 'rgb(255,255,255)', text: '#333', border: true };
    if (p > 23) return { bg: 'rgb(188,202,228)', text: '#333', border: false };
    if (p > 5) return { bg: 'rgb(121,150,200)', text: '#fff', border: false };
    return { bg: 'rgb(54,97,173)', text: '#fff', border: false };
  }

  function buildCell(stats, col) {
    const td = document.createElement('td');
    td.style.cssText = 'text-align:center;padding:2px 5px;font-size:11px;white-space:nowrap;vertical-align:middle;';

    if (!stats) { td.textContent = '—'; td.style.color = '#aaa'; return td; }

    if (col.type === 'run_value') {
      const val = stats.raw?.[col.rawKey] ?? null;
      if (val == null) { td.textContent = '—'; td.style.color = '#aaa'; return td; }
      td.textContent = col.fmt(val);
      td.style.color = val > 0.5 ? '#2d7d3a' : val < -0.5 ? '#c00' : '#666';
      td.title = `${col.label}: ${col.fmt(val)}`;
      return td;
    }

    const pctl = stats.percentiles?.[col.pctlKey] ?? null;
    const rawVal = stats.raw?.[col.rawKey] ?? null;

    if (stats.qualified && pctl != null) {
      const colors = pctlColor(pctl, col.inverted);
      const circle = document.createElement('span');
      circle.style.cssText = [
        'display:inline-flex', 'align-items:center', 'justify-content:center',
        'width:26px', 'height:26px', 'border-radius:50%',
        `background:${colors.bg}`, `color:${colors.text}`,
        colors.border ? 'border:1px solid #ccc' : '',
        'font-weight:700', 'font-size:11px', 'cursor:default',
      ].filter(Boolean).join(';');
      circle.textContent = pctl;
      td.appendChild(circle);
      if (rawVal != null) td.title = `${col.fmt(rawVal)} · ${pctl}th percentile`;
    } else if (rawVal != null) {
      const pa = stats.raw?.pa;
      td.textContent = '*' + col.fmt(rawVal);
      td.style.color = '#555';
      td.title = `Unqualified · ${col.fmt(rawVal)}${pa != null ? ` in ${pa} PA` : ''}`;
    } else {
      td.textContent = '—';
      td.style.color = '#aaa';
    }
    return td;
  }

  const LINK_STYLE = 'text-decoration:none;margin-left:4px;font-size:12px;vertical-align:middle;cursor:pointer;';

  function addPlayerLinks(parentEl, playerName, ottId, mlbamId) {
    if (!parentEl) return;
    parentEl.querySelectorAll('.otto-savant-link, .otto-edit-link').forEach(el => el.remove());

    if (mlbamId) {
      const slug = (playerName || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
      const savantUrl = `https://baseballsavant.mlb.com/savant-player/${slug}-${mlbamId}`;
      const savantA = document.createElement('a');
      savantA.href = savantUrl;
      savantA.title = 'Baseball Savant percentile data';
      savantA.className = 'otto-savant-link';
      savantA.textContent = '⚾';
      savantA.style.cssText = LINK_STYLE;
      savantA.addEventListener('mouseenter', () => {
        _cancelSavantHide();
        showSavantOverlay(savantA, savantUrl, playerName, ottId);
      });
      savantA.addEventListener('mouseleave', _scheduleSavantHide);
      parentEl.appendChild(savantA);
    }

    const editA = document.createElement('a');
    editA.href = '#';
    editA.title = 'Set Savant ID manually';
    editA.className = 'otto-edit-link';
    editA.textContent = '✏️';
    editA.style.cssText = LINK_STYLE;
    editA.addEventListener('click', e => { e.preventDefault(); showEditPopup(ottId, playerName, parentEl); });
    parentEl.appendChild(editA);
  }

  let _editPopup = null;

  function getEditPopup() {
    if (_editPopup) return _editPopup;

    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);display:none;align-items:center;justify-content:center;z-index:99999;';

    const box = document.createElement('div');
    box.style.cssText = 'background:#fff;border-radius:8px;padding:20px 24px;width:440px;box-shadow:0 4px 24px rgba(0,0,0,0.25);font-family:sans-serif;';
    box.innerHTML = [
      '<h3 id="otto-pp-title" style="margin:0 0 4px;font-size:15px;"></h3>',
      '<p style="margin:0 0 12px;font-size:12px;color:#666;">Paste the Baseball Savant player page URL.</p>',
      '<input id="otto-pp-input" type="text" placeholder="https://baseballsavant.mlb.com/savant-player/..."',
      '  style="width:100%;box-sizing:border-box;padding:7px 10px;border:1px solid #ccc;border-radius:4px;font-size:13px;">',
      '<p id="otto-pp-parsed" style="margin:8px 0 14px;font-size:12px;min-height:16px;"></p>',
      '<div style="display:flex;gap:8px;justify-content:flex-end;">',
      '  <button id="otto-pp-cancel" style="padding:6px 14px;font-size:13px;border:1px solid #ccc;border-radius:4px;cursor:pointer;background:#fff;">Cancel</button>',
      '  <button id="otto-pp-save" style="padding:6px 14px;font-size:13px;background:#2d7d3a;color:#fff;border:none;border-radius:4px;cursor:pointer;" disabled>Save</button>',
      '</div>',
    ].join('');

    overlay.appendChild(box);
    document.body.appendChild(overlay);

    const input = box.querySelector('#otto-pp-input');
    const parsedEl = box.querySelector('#otto-pp-parsed');
    const saveBtn = box.querySelector('#otto-pp-save');
    const cancelBtn = box.querySelector('#otto-pp-cancel');

    function hide() { overlay.style.display = 'none'; }
    function extractMlbam(url) {
      const m = url.match(/savant-player\/[\w-]+-(\d{5,7})/);
      return m ? m[1] : null;
    }

    input.addEventListener('input', () => {
      const mlbam = extractMlbam(input.value.trim());
      if (mlbam) {
        parsedEl.textContent = `MLBAM ID: ${mlbam}`;
        parsedEl.style.color = '#2d7d3a';
        saveBtn.disabled = false;
        saveBtn.dataset.mlbam = mlbam;
      } else {
        parsedEl.textContent = input.value ? 'Could not parse MLBAM ID — check URL' : '';
        parsedEl.style.color = '#c00';
        saveBtn.disabled = true;
        delete saveBtn.dataset.mlbam;
      }
    });

    cancelBtn.addEventListener('click', hide);
    overlay.addEventListener('click', e => { if (e.target === overlay) hide(); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') hide(); });

    overlay.show = (ottId, playerName, parentEl) => {
      box.querySelector('#otto-pp-title').textContent = `Set Savant ID — ${playerName || ottId}`;
      input.value = '';
      parsedEl.textContent = '';
      saveBtn.disabled = true;
      delete saveBtn.dataset.mlbam;
      overlay.style.display = 'flex';
      input.focus();

      saveBtn.onclick = async () => {
        const mlbam = saveBtn.dataset.mlbam;
        if (!mlbam) return;
        saveBtn.disabled = true;
        saveBtn.textContent = 'Saving…';
        await OttoStatcast.setOttoMapping(ottId, mlbam);
        addPlayerLinks(parentEl, playerName, ottId, mlbam);
        hide();
        saveBtn.textContent = 'Save';
      };
    };

    _editPopup = overlay;
    return _editPopup;
  }

  function showEditPopup(ottId, playerName, parentEl) {
    getEditPopup().show(ottId, playerName, parentEl);
  }

  let _savantOverlay = null;
  let _savantHideTimer = null;

  function _scheduleSavantHide() {
    _savantHideTimer = setTimeout(() => {
      if (_savantOverlay) _savantOverlay.style.display = 'none';
    }, 200);
  }

  function _cancelSavantHide() {
    if (_savantHideTimer) { clearTimeout(_savantHideTimer); _savantHideTimer = null; }
  }

  function getSavantOverlay() {
    if (_savantOverlay) return _savantOverlay;

    const el = document.createElement('div');
    el.style.cssText = [
      'position:fixed', 'z-index:99998', 'display:none',
      'background:#fff', 'border:1px solid #ddd', 'border-radius:8px',
      'box-shadow:0 4px 20px rgba(0,0,0,0.2)',
      'width:420px', 'max-height:560px', 'overflow-y:auto',
      'font-family:sans-serif',
    ].join(';');

    document.body.appendChild(el);
    el.addEventListener('mouseenter', _cancelSavantHide);
    el.addEventListener('mouseleave', _scheduleSavantHide);
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape' && _savantOverlay) _savantOverlay.style.display = 'none';
    });

    _savantOverlay = el;
    return el;
  }

  function positionSavantOverlay(overlay, anchor) {
    const r = anchor.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const w = 420, h = 560;
    let left = r.right + 10;
    let top = r.top;
    if (left + w > vw - 8) left = r.left - w - 10;
    if (top + h > vh - 8) top = Math.max(8, vh - h - 8);
    overlay.style.left = `${Math.max(8, left)}px`;
    overlay.style.top = `${top}px`;
  }

  async function showSavantOverlay(anchor, savantUrl, playerName, ottId) {
    const overlay = getSavantOverlay();
    positionSavantOverlay(overlay, anchor);

    overlay.innerHTML = '';
    const header = document.createElement('div');
    header.style.cssText = 'padding:10px 14px;font-weight:700;font-size:13px;border-bottom:1px solid #eee;display:flex;align-items:center;justify-content:space-between;';
    header.innerHTML = `<span>${playerName}</span>
      <a href="${savantUrl}" target="_blank" rel="noopener noreferrer"
         style="font-size:11px;color:#1a6faf;text-decoration:none !important;">Open Savant ↗</a>`;
    overlay.appendChild(header);

    const body = document.createElement('div');
    body.style.cssText = 'padding:12px 14px;';
    body.innerHTML = '<p style="color:#aaa;font-size:12px;margin:0;">Loading…</p>';
    overlay.appendChild(body);
    overlay.style.display = 'block';

    const stats = await OttoStatcast.getStats(ottId);
    body.innerHTML = '';
    if (stats?.percentiles) {
      body.appendChild(renderPercentileGrid(stats.percentiles, stats.raw));
    } else if (stats?.raw) {
      body.appendChild(renderRawGrid(stats.raw, stats.raw?.pa));
    } else {
      body.innerHTML = '<p style="font-size:12px;color:#888;margin:0;">No data cached — open Savant to view.</p>';
    }
  }

  const POPUP_SECTIONS = [
    {
      title: 'Batting',
      metrics: [
        { key: 'xwoba', label: 'xwOBA', rawKey: 'xwoba', fmt: v => v.toFixed(3) },
        { key: 'xba', label: 'xBA', rawKey: 'xba', fmt: v => v.toFixed(3) },
        { key: 'xslg', label: 'xSLG', rawKey: 'xslg', fmt: v => v.toFixed(3) },
        { key: 'ev', label: 'Avg Exit Velo', rawKey: 'ev', fmt: v => v.toFixed(1) },
        { key: 'barrel', label: 'Barrel %', rawKey: 'barrel_pct', fmt: v => v.toFixed(1) + '%' },
        { key: 'hard_hit', label: 'Hard-Hit %', rawKey: 'hard_hit_pct', fmt: v => v.toFixed(1) + '%' },
        { key: 'bat_speed', label: 'Bat Speed', rawKey: null },
        { key: 'squared_up', label: 'Squared-Up %', rawKey: null },
        { key: 'chase', label: 'Chase %', rawKey: null },
        { key: 'whiff', label: 'Whiff %', rawKey: null },
        { key: 'k_pct', label: 'K %', rawKey: 'k_pct', fmt: v => v.toFixed(1) + '%' },
        { key: 'bb_pct', label: 'BB %', rawKey: 'bb_pct', fmt: v => v.toFixed(1) + '%' },
      ],
    },
    {
      title: 'Running',
      metrics: [
        { key: 'sprint', label: 'Sprint Speed', rawKey: null },
      ],
    },
  ];

  function renderMetricSlider(label, pctl, fmtVal) {
    const row = document.createElement('div');
    row.style.cssText = 'display:grid;grid-template-columns:116px 1fr 44px;align-items:center;gap:4px;margin:2px 0;min-height:24px;';

    const labelEl = document.createElement('span');
    labelEl.style.cssText = 'font-size:11px;color:#555;text-align:right;padding-right:6px;white-space:nowrap;';
    labelEl.textContent = label;

    const trackWrap = document.createElement('div');
    trackWrap.style.cssText = 'position:relative;height:24px;';

    const bg = document.createElement('div');
    bg.style.cssText = 'position:absolute;top:50%;left:0;right:0;height:5px;transform:translateY(-50%);background:#ddd;border-radius:3px;';
    trackWrap.appendChild(bg);

    if (pctl != null) {
      const colors = pctlColor(pctl, false);
      const pos = Math.max(2, Math.min(pctl, 98));
      const fill = document.createElement('div');
      fill.style.cssText = `position:absolute;top:50%;left:0;width:${pctl}%;height:5px;transform:translateY(-50%);background:${colors.bg};border-radius:3px;opacity:0.65;`;
      const circle = document.createElement('div');
      circle.style.cssText = [
        'position:absolute;top:50%;z-index:1;',
        `left:${pos}%;transform:translate(-50%,-50%);`,
        'width:21px;height:21px;border-radius:50%;',
        `background:${colors.bg};color:${colors.text};`,
        colors.border ? 'border:1px solid #ccc;' : '',
        'font-size:10px;font-weight:700;display:flex;align-items:center;justify-content:center;',
      ].join('');
      circle.textContent = pctl;
      trackWrap.appendChild(fill);
      trackWrap.appendChild(circle);
    } else {
      const dash = document.createElement('span');
      dash.style.cssText = 'position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);font-size:11px;color:#bbb;';
      dash.textContent = '—';
      trackWrap.appendChild(dash);
    }

    const valEl = document.createElement('span');
    valEl.style.cssText = 'font-size:11px;color:#333;white-space:nowrap;';
    valEl.textContent = fmtVal ?? '';

    row.appendChild(labelEl);
    row.appendChild(trackWrap);
    row.appendChild(valEl);
    return row;
  }

  function renderPercentileGrid(percentiles, raw) {
    const container = document.createElement('div');
    for (const section of POPUP_SECTIONS) {
      const hdr = document.createElement('div');
      hdr.style.cssText = 'font-size:10px;font-weight:700;color:#999;text-transform:uppercase;letter-spacing:0.06em;margin:10px 0 4px;padding-top:8px;border-top:1px solid #eee;';
      hdr.textContent = section.title;
      container.appendChild(hdr);
      for (const m of section.metrics) {
        const pctl = m.key ? (percentiles?.[m.key] ?? null) : null;
        const rawVal = m.rawKey ? (raw?.[m.rawKey] ?? null) : null;
        const fmtVal = rawVal != null && m.fmt ? m.fmt(rawVal) : null;
        container.appendChild(renderMetricSlider(m.label, pctl, fmtVal));
      }
    }
    return container;
  }

  function renderRawGrid(raw, pa) {
    const wrap = document.createElement('div');
    const note = document.createElement('p');
    note.style.cssText = 'font-size:11px;color:#888;margin:0 0 8px;';
    note.textContent = `Unqualified${pa != null ? ` · ${pa} PA` : ''} — raw values only`;
    wrap.appendChild(note);
    const items = [
      { key: 'xwoba', label: 'xwOBA', fmt: v => v.toFixed(3) },
      { key: 'xba', label: 'xBA', fmt: v => v.toFixed(3) },
      { key: 'xslg', label: 'xSLG', fmt: v => v.toFixed(3) },
      { key: 'ev', label: 'Exit Velo', fmt: v => v.toFixed(1) },
      { key: 'hard_hit_pct', label: 'Hard-Hit %', fmt: v => v.toFixed(1) + '%' },
    ];
    for (const { key, label, fmt } of items) {
      if (raw[key] == null) continue;
      wrap.appendChild(renderMetricSlider(label, null, fmt(raw[key])));
    }
    return wrap;
  }

  return { pctlColor, buildCell, addPlayerLinks, showEditPopup, showSavantOverlay, renderPercentileGrid, renderRawGrid };
})();

// ── Page scripts ──────────────────────────────────────────────────────────────

(async () => {
  'use strict';

  const { buildCell, addPlayerLinks } = OttoStatcastUI;

  const _style = document.createElement('style');
  const leagueId = window.location.pathname.split('/')[1];
  const isLineup = window.location.pathname.includes('/setlineups');

  const COLS = [
    { pctlKey: null, rawKey: 'runs_all', label: 'Runs', type: 'run_value', fmt: v => (v >= 0 ? '+' : '') + v.toFixed(1) },
    { pctlKey: 'xwoba', rawKey: 'xwoba', label: 'xwOBA', inverted: false, fmt: v => v.toFixed(3) },
    { pctlKey: 'hard_hit', rawKey: 'hard_hit_pct', label: 'HH%', inverted: false, fmt: v => v.toFixed(1) + '%' },
    { pctlKey: 'barrel', rawKey: 'barrel_pct', label: 'Brrl%', inverted: false, fmt: v => v.toFixed(1) + '%' },
    { pctlKey: 'k_pct', rawKey: 'k_pct', label: 'K%', inverted: false, fmt: v => v.toFixed(1) + '%' },
  ];

  if (isLineup) {
    _style.textContent = '.otto-savant-link, .otto-edit-link { text-decoration: none !important; }';
    document.head.appendChild(_style);

    const _mainEl = document.querySelector('main');
    if (_mainEl) {
      const _currentMax = parseInt(getComputedStyle(_mainEl).maxWidth, 10);
      _mainEl.style.maxWidth = (isNaN(_currentMax) ? 1300 : _currentMax + 100) + 'px';
    }

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

  } else {
    // Search page
    _style.textContent = [
      '.otto-savant-link, .otto-edit-link { text-decoration: none !important; }',
      'main { max-width: none !important; }',
    ].join('\n');
    document.head.appendChild(_style);

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

    function ottIdFromHref(href) {
      const m = (href || '').match(/\/players\/(\d+)/);
      return m ? m[1] : null;
    }

    function findResultsTable() {
      const byClass = document.querySelector('table.player-list, table#search-results, table.search-results');
      if (byClass) return byClass;
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

    function processRows(table) {
      addHeaders(table);

      for (const row of table.querySelectorAll('tbody tr')) {
        if (row.dataset.ottoProcessed) continue;

        const playerLink = row.querySelector('a[href*="/players/"]');
        if (!playerLink) continue;

        const ottId = ottIdFromHref(playerLink.getAttribute('href'));
        if (!ottId) continue;

        row.dataset.ottoProcessed = '1';
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

    let _debounceTimer = null;
    const observer = new MutationObserver(() => {
      clearTimeout(_debounceTimer);
      _debounceTimer = setTimeout(() => {
        const t = findResultsTable();
        if (t) processRows(t);
      }, 150);
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }
})();