// otto-statcast-display.js
// Shared display/UI library for Ottoneu Statcast userscripts.
// @require this alongside otto-statcast-core.js in every page script.

var OttoStatcastUI = (() => { // eslint-disable-line no-var
  'use strict';

  // ── Colour scale ──────────────────────────────────────────────────────────────
  // Mirrors the Baseball Savant red (elite) → blue (poor) gradient.
  // All batter percentiles in the Savant CSV are pre-inverted (higher = better).

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

  // ── Table cell builder ────────────────────────────────────────────────────────

  function buildCell(stats, col) {
    const td = document.createElement('td');
    td.style.cssText = 'text-align:center;padding:2px 5px;font-size:11px;white-space:nowrap;vertical-align:middle;';

    if (!stats) { td.textContent = '—'; td.style.color = '#aaa'; return td; }

    // Run value columns: plain coloured number, no percentile circle or * prefix
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

  // ── Player links (⚾ + ✏️) ────────────────────────────────────────────────────
  // parentEl: the element to append links into (caller supplies the right container)

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

  // ── Manual Savant ID popup ────────────────────────────────────────────────────

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

  // ── Savant percentile hover overlay ──────────────────────────────────────────

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

  // ── Percentile popup rendering ────────────────────────────────────────────────

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
