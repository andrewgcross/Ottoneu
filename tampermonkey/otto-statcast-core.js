// otto-statcast-core.js
// Ottoneu Statcast Enhancement — Core Library
// Not a standalone userscript. @require this file from page scripts.
// The calling script must declare:
//   @grant  GM_xmlhttpRequest
//   @connect baseballsavant.mlb.com
//   @connect www.fangraphs.com

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

  // Step 1: check cache
  // Step 2: match player name against existing players store (no HTTP needed)
  // Step 3: fallback — scrape Ottoneu player page → FG ID → FanGraphs page → MLBAM ID
  async function _ottToMlbam(ottId, playerName, leagueId) {
    // 1. Cache hit
    const cached = await _get('otto_crosswalk', String(ottId));
    if (cached) return cached.mlbam_id;

    // 2. Name match against already-loaded players store
    if (playerName) {
      const mlbamId = await _scanPlayersByName(playerName);
      if (mlbamId) {
        await _put('otto_crosswalk', { otto_id: String(ottId), mlbam_id: mlbamId, source: 'name' });
        console.log(`[OttoStatcast] Resolved ${playerName} (otto ${ottId}) by name → mlbam ${mlbamId}`);
        return mlbamId;
      }
    }

    // 3. Savant search fallback for players not yet in the players store
    return _resolveViaPages(ottId, playerName, leagueId);
  }

  // Scan the players store cursor for a name match (covers ~1-5k records, fast).
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

    // If we don't have a name yet, fetch the Ottoneu player page to get it
    let resolvedName = playerName;
    let fgId = null;

    if (!resolvedName || true) { // always fetch to also capture FG ID for logging
      try {
        const resp = await fetch(`https://ottoneu.fangraphs.com/${leagueId}/players/${ottId}`);
        const html = await resp.text();
        const fgMatch = html.match(/statss\.aspx\?playerid=(\d+)/i);
        if (fgMatch) fgId = fgMatch[1];
        // Extract name from page title as a fallback if DOM name was unavailable
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

    // Search Baseball Savant by last name, disambiguate by first name
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

    // Log the raw result shape once so we can verify field names
    if (results[0]) console.log('[OttoStatcast] Savant search result shape:', Object.keys(results[0]).join(', '));

    // Pick best match: prefer exact first-name prefix match
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

  // ── On-demand: histogram + page scrape for players with no Statcast data ──────

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

  /**
   * Returns cached stats for an Ottoneu player ID.
   * Does NOT trigger network fetches — call getStatsOrFetch() for that.
   */
  async function getStats(ottId) {
    const cw = await _get('otto_crosswalk', String(ottId));
    if (!cw) return null;

    const p = await _get('players', cw.mlbam_id);
    if (!p) return null;

    const percentiles = p[`pctl_${YEAR}`] || null;
    // Merge raw sources: ondemand (histogram) provides hard_hit_pct/ev;
    // CSV expected stats override where both exist; swing-take adds runs_all.
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

  /**
   * Manually store an Ottoneu ID → MLBAM ID mapping.
   * Called from the roster script's manual-entry popup.
   */
  async function setOttoMapping(ottId, mlbamId) {
    await _put('otto_crosswalk', { otto_id: String(ottId), mlbam_id: String(mlbamId), source: 'manual' });
    console.log(`[OttoStatcast] Manual mapping saved: otto ${ottId} → mlbam ${mlbamId}`);
  }

  /**
   * Resolves Ottoneu ID → MLBAM ID (via name match or page scrape), fetches
   * Statcast data if absent, and returns the stats object.
   *
   * @param {string} ottId - value of data-player-id on the Ottoneu page
   * @param {string} leagueId - Ottoneu league ID (from window.location.pathname)
   * @param {string} playerName - player name as displayed on the page (for name matching)
   * @param {string} type - 'batter' or 'pitcher'
   */
  async function getStatsOrFetch(ottId, leagueId, playerName, type = 'batter') {
    const mlbamId = await _ottToMlbam(ottId, playerName, leagueId);
    if (!mlbamId) return null;

    const p = await _get('players', mlbamId);
    const isQualified = p && p[`pctl_${YEAR}`];
    const hasOnDemand = p && p[`ondemand_${YEAR}`];

    // Always run the histogram fetch for unqualified players so hard_hit_pct,
    // ev, etc. are available — unless we've already fetched it today.
    if (!isQualified && !hasOnDemand) {
      await _fetchOnDemand(mlbamId, p?.name || playerName, type);
    } else if (!p) {
      await _fetchOnDemand(mlbamId, playerName, type);
    }

    return getStats(ottId);
  }

  /**
   * Initialises the DB and loads the batter percentile CSV (needed for name matching).
   * Returns when that data is ready; all other fetches run in background.
   */
  async function init() {
    await _open();
    // Await the two data sources needed before any cell can render
    await Promise.allSettled([
      _refreshPercentiles('batter'),
      _refreshSwingTake(),
    ]);
    _refreshPercentiles('pitcher').catch(e => console.error('[OttoStatcast] Pitcher pctl:', e));
    _refreshExpected('batter').catch(e => console.error('[OttoStatcast] Batter exp:', e));
    _refreshExpected('pitcher').catch(e => console.error('[OttoStatcast] Pitcher exp:', e));
  }

  // ── Utilities ─────────────────────────────────────────────────────────────────

  function _i(v) { const n = parseInt(v, 10); return isNaN(n) ? null : n; }
  function _f(v) { const n = parseFloat(v); return isNaN(n) ? null : n; }

  // ── Debug helpers ─────────────────────────────────────────────────────────────

  const debug = {
    query: (store, key) => _get(store, key),
    otto: (ottId) => _get('otto_crosswalk', String(ottId)),
    player: (mlbamId) => _get('players', String(mlbamId)),
    meta: (key) => _get('meta', key),
    nameMatch: (name) => _scanPlayersByName(name),
  };

  return { init, getStats, getStatsOrFetch, setOttoMapping, fetchHtml: _fetch, debug };
})();
