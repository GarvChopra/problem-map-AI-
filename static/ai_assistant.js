/* ════════════════════ AreaPulse Civic AI — Frontend Logic ═════════════════ */

(function () {
  const fab        = document.getElementById('ai-fab');
  const panel      = document.getElementById('ai-panel');
  const closeBtn   = document.getElementById('ai-close');
  const messagesEl = document.getElementById('ai-messages');
  const inputEl    = document.getElementById('ai-input');
  const sendBtn    = document.getElementById('ai-send');
  const tabs       = document.querySelectorAll('.ai-tab');
  const tabPanels  = document.querySelectorAll('.ai-tab-panel');
  const insightsEl = document.getElementById('ai-insights-content');

  let panelOpen = false;
  let insightsLoaded = false;

  // ── Open / close ─────────────────────────────────────
  fab.addEventListener('click', () => {
    panelOpen = !panelOpen;
    panel.classList.toggle('hidden', !panelOpen);
    if (panelOpen && !insightsLoaded) loadInsights();
  });
  closeBtn.addEventListener('click', () => {
    panelOpen = false;
    panel.classList.add('hidden');
  });

  // ── Tabs ────────────────────────────────────────────
  tabs.forEach(t => t.addEventListener('click', () => {
    tabs.forEach(x => x.classList.remove('active'));
    tabPanels.forEach(p => p.classList.remove('active'));
    t.classList.add('active');
    document.getElementById('ai-tab-' + t.dataset.tab).classList.add('active');
    if (t.dataset.tab === 'insights' && !insightsLoaded) loadInsights();
  }));

  // ── Suggested chips: replace stock chips with dashboard-aware ones ──
  // The HTML in base.html has 6 stock chips; we swap them so users discover
  // the new compare / dashboard features the moment they open the panel.
  const NEW_CHIPS = [
    { q: 'compare rohini vs saket',     label: 'Compare Rohini vs Saket' },
    { q: 'show report rohini',          label: 'Rohini full report' },
    { q: 'how is lajpat nagar doing',   label: 'How is Lajpat Nagar?' },
    { q: 'compare dwarka vs hauz khas', label: 'Dwarka vs Hauz Khas' },
    { q: 'which areas need most attention?', label: 'Top priority areas' },
    { q: 'show me high severity issues on map', label: 'High-severity map' },
  ];
  const chipBox = document.querySelector('.ai-suggested');
  if (chipBox) {
    chipBox.innerHTML = NEW_CHIPS.map(c =>
      `<button class="ai-chip" data-q="${c.q.replace(/"/g, '&quot;')}">${c.label}</button>`
    ).join('');
  }
  // Use event delegation so dynamically-replaced chips still work
  document.addEventListener('click', e => {
    const chip = e.target.closest && e.target.closest('.ai-chip');
    if (!chip) return;
    const q = chip.dataset.q;
    if (!q) return;
    inputEl.value = q;
    sendQuery();
  });

  // ── Send ─────────────────────────────────────────────
  sendBtn.addEventListener('click', sendQuery);
  inputEl.addEventListener('keydown', e => {
    if (e.key === 'Enter') sendQuery();
  });

  function appendMsg(role, html) {
    const d = document.createElement('div');
    d.className = 'ai-msg ai-msg-' + role;
    d.innerHTML = `<div class="ai-msg-bubble">${html}</div>`;
    messagesEl.appendChild(d);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return d;
  }

  function escHtml(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function renderResponseHTML(resp) {
    let html = resp.message ? formatBold(escHtml(resp.message)).replace(/\n/g, '<br>') : '';

    // ── NEW: dashboard type — render compact preview in chat + open big modal ──
    if (resp.type === 'dashboard') {
      const isCompare = resp.mode === 'compare';
      const title = isCompare
        ? `${resp.area_a.area} vs ${resp.area_b.area}`
        : resp.area;
      const sub = isCompare
        ? `${resp.area_a.total} report${resp.area_a.total === 1 ? '' : 's'} vs ${resp.area_b.total} report${resp.area_b.total === 1 ? '' : 's'}`
        : `${resp.total} total · ${resp.open} open · ${resp.ngo_count} NGOs nearby`;
      // Each preview card stores its own payload via a unique key so older
      // previews always open their own data — not whatever was queried last.
      window.__dashPayloads = window.__dashPayloads || {};
      const payloadKey = 'dash_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
      window.__dashPayloads[payloadKey] = resp;
      // Also remember the latest one for the auto-open below
      window.__lastDashboardPayload = resp;

      html += `
        <div class="ai-dash-preview" onclick="window.openAreaDashboard(window.__dashPayloads['${payloadKey}'])">
          <div class="ai-dash-preview-title">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3v18h18"/><path d="M7 14l4-4 4 4 5-5"/></svg>
            ${escHtml(title)}
          </div>
          <div class="ai-dash-preview-sub">${escHtml(sub)}</div>
          <div class="ai-dash-preview-cta">Tap to open full dashboard →</div>
        </div>`;
      // Auto-open the modal for the freshly-arrived payload
      setTimeout(() => window.openAreaDashboard(resp), 250);
    }

    if (resp.type === 'table' && resp.columns && resp.rows) {
      html += `<div class="ai-table-wrap"><table class="ai-table">
        <thead><tr>${resp.columns.map(c => `<th>${escHtml(c)}</th>`).join('')}</tr></thead>
        <tbody>${resp.rows.map(r =>
          `<tr>${r.map(c => `<td>${escHtml(c)}</td>`).join('')}</tr>`
        ).join('')}</tbody>
      </table></div>`;
    }

    if (resp.type === 'map_markers' && resp.data) {
      html += `<div class="ai-marker-list">`;
      if (!resp.data.length) {
        html += `<div style="padding:14px; color:var(--text2); font-size:12px">No matching issues found.</div>`;
      } else {
        resp.data.slice(0, 12).forEach(m => {
          html += `<div class="ai-marker-row" onclick="aiFocusMap(${m.lat}, ${m.lng})">
            <span class="marker-sev ${m.severity || 'medium'}"></span>
            <b>${escHtml(m.area || 'Delhi')}</b> — ${escHtml(m.label || '')}
          </div>`;
        });
        if (resp.data.length > 12) {
          html += `<div style="padding:8px; text-align:center; font-size:11.5px; color:var(--text2)">+ ${resp.data.length - 12} more on map</div>`;
        }
      }
      html += `</div>`;
      setTimeout(() => plotOnMainMap(resp.data), 200);
    }

    if (resp.type === 'insights' && resp.cards) {
      resp.cards.forEach(c => {
        html += `<div class="ai-insight-card priority-${c.priority || 'medium'}">
          <div class="ai-insight-icon">${c.icon || '○'}</div>
          <div class="ai-insight-msg">${escHtml(c.message)}</div>
        </div>`;
      });
    }
    return html;
  }

  function formatBold(s) {
    return s.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
  }

  function sendQuery() {
    const q = inputEl.value.trim();
    if (!q) return;
    appendMsg('user', escHtml(q));
    inputEl.value = '';

    const thinking = appendMsg('bot', `<i style="opacity:0.6">Thinking…</i>`);

    fetch('/ai/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: q })
    })
      .then(r => r.json())
      .then(resp => {
        thinking.querySelector('.ai-msg-bubble').innerHTML = renderResponseHTML(resp);
        messagesEl.scrollTop = messagesEl.scrollHeight;
      })
      .catch(err => {
        thinking.querySelector('.ai-msg-bubble').innerHTML =
          `<span style="color:var(--accent)">Sorry, I couldn't reach the AI service right now.</span>`;
      });
  }

  // ── Insights tab ─────────────────────────────────────
  function loadInsights() {
    insightsEl.innerHTML = `<div class="ai-loading"><div class="spinner"></div><div>Analyzing civic data…</div></div>`;
    fetch('/ai/insights').then(r => r.json()).then(d => {
      let html = '';
      // Top insights
      html += `<div style="font-weight:600; font-size:13px; margin-bottom:10px">Live Insights</div>`;
      if (d.insights && d.insights.length) {
        d.insights.forEach(c => {
          html += `<div class="ai-insight-card priority-${c.priority || 'medium'}">
            <div class="ai-insight-icon">${c.icon || '○'}</div>
            <div class="ai-insight-msg">${escHtml(c.message)}</div>
          </div>`;
        });
      } else {
        html += `<div style="font-size:12.5px; color:var(--text2);">No standout insights right now.</div>`;
      }

      // Hot areas
      if (d.hot_areas && d.hot_areas.length) {
        html += `<div style="font-weight:600; font-size:13px; margin:18px 0 10px">Priority Areas</div>`;
        html += `<div class="ai-table-wrap"><table class="ai-table">
          <thead><tr><th>Area</th><th>Open</th><th>Score</th></tr></thead>
          <tbody>${d.hot_areas.slice(0, 6).map(h =>
            `<tr><td>${escHtml(h.area)}</td><td>${h.issue_count}</td><td>${h.priority_score}</td></tr>`
          ).join('')}</tbody>
        </table></div>`;
      }

      // 24h trends
      if (d.trends && d.trends.by_tag && d.trends.by_tag.length) {
        html += `<div style="font-weight:600; font-size:13px; margin:18px 0 10px">24h Trends</div>`;
        html += `<div class="ai-table-wrap"><table class="ai-table">
          <thead><tr><th>Category</th><th>Now</th><th>Prev</th><th>Δ</th></tr></thead>
          <tbody>${d.trends.by_tag.slice(0, 6).map(t => {
            const cls = t.change_pct > 0 ? 'color:#C84B31' : t.change_pct < 0 ? 'color:#2D6A4F' : '';
            return `<tr><td>${t.tag}</td><td>${t.recent}</td><td>${t.previous}</td>
              <td style="${cls}">${t.change_pct >= 0 ? '+' : ''}${t.change_pct}%</td></tr>`;
          }).join('')}</tbody>
        </table></div>`;
      }

      insightsEl.innerHTML = html;
      insightsLoaded = true;
    }).catch(() => {
      insightsEl.innerHTML = `<div style="padding:20px; color:var(--accent)">Could not load insights.</div>`;
    });
  }

  // ── Copilot tab ──────────────────────────────────────
  const copilotInput  = document.getElementById('ai-copilot-input');
  const copilotGo     = document.getElementById('ai-copilot-go');
  const copilotResult = document.getElementById('ai-copilot-result');
  if (copilotGo) {
    copilotGo.addEventListener('click', () => {
      const text = copilotInput.value.trim();
      if (text.length < 5) { showToast('Please write a longer description'); return; }
      copilotResult.innerHTML = `<div class="ai-loading"><div class="spinner"></div><div>Analyzing…</div></div>`;
      Promise.all([
        fetch('/ai/copilot', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ description: text })
        }).then(r => r.json()),
        fetch('/ai/moderation', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ description: text })
        }).then(r => r.json())
      ]).then(([co, mod]) => {
        const modCls = mod.action === 'auto_block' ? 'ai-mod-block'
                     : mod.action === 'review'     ? 'ai-mod-review'
                     : 'ai-mod-allow';
        const modIcon = mod.action === 'auto_block' ? '⛔'
                      : mod.action === 'review'     ? '⚠️'
                      : '✓';
        copilotResult.innerHTML = `
          <div class="copilot-result">
            <div style="font-weight:600; font-size:13px; margin-bottom:8px">AI Suggestions</div>
            <div class="copilot-row"><span class="copilot-key">Category</span>
              <span class="copilot-val">${escHtml(co.suggested_tag || 'other').toUpperCase()}</span></div>
            <div class="copilot-row"><span class="copilot-key">Severity</span>
              <span class="copilot-val">${escHtml(co.suggested_severity || 'medium').toUpperCase()}</span></div>
            <div class="copilot-row" style="flex-direction:column; align-items:flex-start; gap:4px">
              <span class="copilot-key">Improved description</span>
              <div style="font-size:12.5px; line-height:1.5; padding:8px; background:var(--surface2); border-radius:6px; width:100%">
                ${escHtml(co.improved_description || text)}
              </div>
            </div>
          </div>
          <div class="ai-mod-banner ${modCls}" style="margin-top:10px">
            ${modIcon}
            <div>
              <b>Spam check:</b> ${mod.action.toUpperCase()} (confidence ${mod.confidence}%) — ${escHtml(mod.reason)}
            </div>
          </div>
          <button class="btn btn-outline btn-sm" style="margin-top:10px; width:100%" onclick="aiFillForm('${escapeJs(co.suggested_tag)}', '${escapeJs(co.suggested_severity)}', \`${escapeJs(co.improved_description || text)}\`)">
            Use these in the Report Form
          </button>
        `;
      }).catch(() => {
        copilotResult.innerHTML = `<div style="color:var(--accent)">AI service unavailable.</div>`;
      });
    });
  }

  function escapeJs(s) {
    return String(s || '').replace(/\\/g, '\\\\').replace(/`/g, '\\`').replace(/'/g, "\\'");
  }

  // ── Hook into the index page form if present ─────────
  window.aiFillForm = function (tag, severity, description) {
    const sevField  = document.getElementById('r-severity')
                   || document.querySelector('select[name="severity"], #severity');
    const descField = document.getElementById('r-desc')
                   || document.querySelector('textarea[name="description"], #description');
    if (sevField) sevField.value = severity;
    if (descField) descField.value = description;
    // Update severity button highlights if the index page has them
    document.querySelectorAll('.severity-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.sev === severity);
    });
    showToast('AI suggestions applied to the form');
    panel.classList.add('hidden'); panelOpen = false;
  };

  // ── Safe map helpers (work even when no map is on the page) ──
  function findActiveMap() {
    if (typeof L === 'undefined') return null;

    // 1) Common globals first
    if (window.map && typeof window.map.addLayer === 'function') return window.map;
    if (window.heatmap && typeof window.heatmap.addLayer === 'function') return window.heatmap;
    if (window.ngoMap && typeof window.ngoMap.addLayer === 'function') return window.ngoMap;

    // 2) Scan for any Leaflet container on the page and find its map instance
    const mapEl = document.querySelector('.leaflet-container');
    if (mapEl) {
      for (const key in window) {
        try {
          const v = window[key];
          if (v && typeof v === 'object'
              && v._container === mapEl
              && typeof v.addLayer === 'function') {
            return v;
          }
        } catch (e) { /* ignore cross-origin / getter errors */ }
      }
    }
    return null;
  }

  window.aiFocusMap = function (lat, lng) {
    const m = findActiveMap();
    if (m && typeof m.setView === 'function') {
      m.setView([lat, lng], 15);
      showToast('Centered map on selected location');
    } else {
      showToast('Open the Home page to see this on the map');
    }
  };

  function plotOnMainMap(markers) {
    const targetMap = findActiveMap();
    if (!targetMap) {
      console.log('[AI] No Leaflet map on this page — markers shown in chat only.');
      return;
    }

    // Remove previous AI overlay
    if (window._aiOverlayLayer) {
      try { targetMap.removeLayer(window._aiOverlayLayer); } catch (e) {}
    }

    const group = L.layerGroup();
    markers.forEach(m => {
      if (!m.lat || !m.lng) return;
      const color = m.severity === 'high' ? '#C84B31'
                  : m.severity === 'low'  ? '#2D6A4F' : '#B7770D';
      L.circleMarker([m.lat, m.lng], {
        radius: 9, color, fillColor: color, fillOpacity: 0.7, weight: 2
      }).bindPopup(`<b>${m.area || ''}</b><br>${m.label || ''}`).addTo(group);
    });
    group.addTo(targetMap);
    window._aiOverlayLayer = group;
  }

  // ── Live moderation while typing in the report description field ─
  document.addEventListener('input', e => {
    if (!e.target) return;
    const isDescField = e.target.id === 'r-desc'
                     || e.target.id === 'description'
                     || e.target.name === 'description';
    if (!isDescField) return;
    const text = e.target.value || '';
    const banner = document.getElementById('ai-mod-live');
    if (text.length < 10) { if (banner) banner.remove(); return; }
    clearTimeout(window._modTimer);
    window._modTimer = setTimeout(() => {
      fetch('/ai/moderation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description: text })
      }).then(r => r.json()).then(mod => {
        let banner = document.getElementById('ai-mod-live');
        if (!banner) {
          banner = document.createElement('div');
          banner.id = 'ai-mod-live';
          banner.style.marginTop = '6px';
          e.target.parentElement.appendChild(banner);
        }
        const cls = mod.action === 'auto_block' ? 'ai-mod-block'
                  : mod.action === 'review' ? 'ai-mod-review' : 'ai-mod-allow';
        const icon = mod.action === 'auto_block' ? '⛔'
                   : mod.action === 'review' ? '⚠️' : '✓';
        banner.className = 'ai-mod-banner ' + cls;
        banner.innerHTML = `${icon} <span><b>AI moderation:</b> ${mod.action.toUpperCase()} · ${mod.reason}</span>`;
      }).catch(() => {});
    }, 600);
  });

  // ════════════════════════════════════════════════════════════
  // ── AREA DASHBOARD MODAL (compare + single-area + after-report) ──
  // ════════════════════════════════════════════════════════════

  function ensureDashboardModal() {
    let m = document.getElementById('ai-dash-modal');
    if (m) return m;
    m = document.createElement('div');
    m.id = 'ai-dash-modal';
    m.className = 'ai-dash-modal-backdrop hidden';
    m.innerHTML = `
      <div class="ai-dash-modal-card" onclick="event.stopPropagation()">
        <button class="ai-dash-close" onclick="window.closeAreaDashboard()">✕</button>
        <div id="ai-dash-body"></div>
      </div>`;
    m.addEventListener('click', () => window.closeAreaDashboard());
    document.body.appendChild(m);
    return m;
  }

  function bar(width, color) {
    return `<div class="ai-dash-bar"><div class="ai-dash-bar-fill" style="width:${Math.max(width, 2)}%; background:${color};"></div></div>`;
  }

  function renderTrendSVG(trend, color) {
    const max = Math.max(...trend, 1);
    const pts = trend.map((v, i) => {
      const x = 10 + i * (580 / 6);
      const y = 50 - (v / max) * 40;
      return `${x},${y}`;
    }).join(' ');
    const lastX = 10 + 6 * (580 / 6);
    const lastY = 50 - (trend[6] / max) * 40;
    return `
      <svg viewBox="0 0 600 60" style="width:100%; height:50px;">
        <line x1="0" y1="50" x2="600" y2="50" stroke="#E5E5E5" stroke-width="0.5"/>
        <polyline fill="none" stroke="${color}" stroke-width="2" points="${pts}"/>
        <circle cx="${lastX}" cy="${lastY}" r="3" fill="${color}"/>
      </svg>`;
  }

  function renderSingleArea(d, opts) {
    const accent = opts && opts.accent || '#C84B31';
    const accentLt = opts && opts.accentLt || '#FCEBEB';

    let bannerHtml = '';
    if (d.banner) {
      bannerHtml = `
        <div class="ai-dash-banner ai-dash-banner-${d.banner.kind}">
          <span class="ai-dash-banner-icon">✓</span>
          <span>${escHtml(d.banner.message)}</span>
        </div>`;
    }

    // Stat cards
    const stats = `
      <div class="ai-dash-stats">
        <div class="ai-dash-stat"><div class="ai-dash-stat-label">Total reports</div><div class="ai-dash-stat-num" style="color:${accent}">${d.total}</div></div>
        <div class="ai-dash-stat"><div class="ai-dash-stat-label">Open</div><div class="ai-dash-stat-num" style="color:#B7770D">${d.open}</div></div>
        <div class="ai-dash-stat"><div class="ai-dash-stat-label">Resolved</div><div class="ai-dash-stat-num" style="color:#2D6A4F">${d.resolved}</div></div>
        <div class="ai-dash-stat"><div class="ai-dash-stat-label">NGOs nearby</div><div class="ai-dash-stat-num" style="color:#1B4F72">${d.ngo_count}</div></div>
      </div>`;

    // Categories
    const maxCount = Math.max(...d.categories.map(c => c.count), 1);
    const catRows = d.categories.map(c => `
      <div class="ai-dash-bar-row">
        <span class="ai-dash-bar-label">${escHtml(c.label)}</span>
        ${bar((c.count / maxCount) * 100, accent)}
        <span class="ai-dash-bar-num" style="color:${accent}">${c.count}</span>
      </div>`).join('');

    // Severity donut (CSS conic-gradient)
    const high = d.severity.high_pct;
    const med  = d.severity.medium_pct;
    const low  = 100 - high - med;
    const conic = `conic-gradient(#C84B31 0 ${high}%, #B7770D ${high}% ${high+med}%, #2D6A4F ${high+med}% 100%)`;

    // Trend
    const trendArrow = d.change_pct > 0 ? '↑' : d.change_pct < 0 ? '↓' : '→';
    const trendColor = d.change_pct > 0 ? accent : '#2D6A4F';

    // NGOs
    const ngoRows = d.ngos.length ? d.ngos.map(n => `
      <div class="ai-dash-ngo-row">
        <div>
          <div class="ai-dash-ngo-name">${escHtml(n.name)}</div>
          <div class="ai-dash-ngo-meta">${escHtml(n.tag)} · ${n.distance_km} km${n.resolved ? ' · ' + n.resolved + ' resolved' : ''}</div>
        </div>
        <div class="ai-dash-ngo-rating">${(n.rating || 4.0).toFixed(1)} ★</div>
      </div>`).join('') : '<div class="ai-dash-empty">No NGOs found nearby</div>';

    return `
      ${bannerHtml}
      <div class="ai-dash-header">
        <div>
          <div class="ai-dash-kicker">AREA SNAPSHOT</div>
          <div class="ai-dash-title">${escHtml(d.area)}</div>
        </div>
      </div>
      ${stats}
      <div class="ai-dash-grid-2">
        <div class="ai-dash-panel">
          <div class="ai-dash-panel-title">REPORTS BY CATEGORY</div>
          ${catRows || '<div class="ai-dash-empty">No data</div>'}
        </div>
        <div class="ai-dash-panel">
          <div class="ai-dash-panel-title">SEVERITY MIX</div>
          <div class="ai-dash-severity">
            <div class="ai-dash-donut" style="background:${conic}"><div class="ai-dash-donut-hole"></div></div>
            <div class="ai-dash-sev-legend">
              <div><span class="dot" style="background:#C84B31"></span>High <b>${high}%</b></div>
              <div><span class="dot" style="background:#B7770D"></span>Med <b>${med}%</b></div>
              <div><span class="dot" style="background:#2D6A4F"></span>Low <b>${low}%</b></div>
            </div>
          </div>
        </div>
      </div>
      <div class="ai-dash-panel">
        <div class="ai-dash-panel-title">
          7-DAY TREND
          <span style="float:right; color:${trendColor}; font-weight:600">${trendArrow} ${d.change_pct >= 0 ? '+' : ''}${d.change_pct}%</span>
        </div>
        ${renderTrendSVG(d.trend, accent)}
      </div>
      <div class="ai-dash-panel">
        <div class="ai-dash-panel-title">NGOs WORKING IN ${d.area.toUpperCase()} · ${d.ngo_count}</div>
        ${ngoRows}
      </div>
      <div class="ai-dash-verdict">
        <b>AI insight:</b> ${formatBold(escHtml(d.insight))}
      </div>
    `;
  }

  function renderMiniArea(d, color) {
    const trendArrow = d.change_pct > 0 ? '↑' : d.change_pct < 0 ? '↓' : '→';
    const maxCount = Math.max(...d.categories.map(c => c.count), 1);
    const catRows = d.categories.slice(0, 4).map(c => `
      <div class="ai-dash-bar-row">
        <span class="ai-dash-bar-label">${escHtml(c.label)}</span>
        ${bar((c.count / maxCount) * 100, color)}
        <span class="ai-dash-bar-num" style="color:${color}">${c.count}</span>
      </div>`).join('');

    // Severity donut (same conic-gradient trick as single-area)
    const high = d.severity.high_pct;
    const med  = d.severity.medium_pct;
    const low  = 100 - high - med;
    const conic = `conic-gradient(#C84B31 0 ${high}%, #B7770D ${high}% ${high+med}%, #2D6A4F ${high+med}% 100%)`;

    const ngoList = d.ngos.length
      ? d.ngos.slice(0, 3).map(n => `<div class="ai-dash-ngo-mini">${escHtml(n.name)} · ${(n.rating||4).toFixed(1)}★</div>`).join('')
      : '<div class="ai-dash-empty">No NGOs nearby</div>';

    return `
      <div class="ai-dash-mini-header" style="color:${color}">${escHtml(d.area)}</div>
      <div class="ai-dash-mini-num" style="color:${color}">${d.total}</div>
      <div class="ai-dash-mini-stats">
        <span><b>${d.open}</b> open</span>
        <span><b>${d.resolved}</b> resolved</span>
        <span style="color:${color}">${trendArrow} ${d.change_pct>=0?'+':''}${d.change_pct}%</span>
      </div>
      <div class="ai-dash-mini-section-title">CATEGORIES</div>
      ${catRows || '<div class="ai-dash-empty">No data</div>'}
      <div class="ai-dash-mini-section-title">SEVERITY MIX</div>
      <div class="ai-dash-severity">
        <div class="ai-dash-donut" style="background:${conic}"><div class="ai-dash-donut-hole"></div></div>
        <div class="ai-dash-sev-legend">
          <div><span class="dot" style="background:#C84B31"></span>High <b>${high}%</b></div>
          <div><span class="dot" style="background:#B7770D"></span>Med <b>${med}%</b></div>
          <div><span class="dot" style="background:#2D6A4F"></span>Low <b>${low}%</b></div>
        </div>
      </div>
      <div class="ai-dash-mini-section-title">7-DAY TREND</div>
      ${renderTrendSVG(d.trend, color)}
      <div class="ai-dash-mini-section-title">NGOs (${d.ngo_count})</div>
      ${ngoList}
    `;
  }

  function renderCompare(payload) {
    return `
      <div class="ai-dash-header">
        <div>
          <div class="ai-dash-kicker">COMPARING</div>
          <div class="ai-dash-title">
            <span style="color:#C84B31">${escHtml(payload.area_a.area)}</span>
            <span style="color:var(--text2); font-weight:400; margin:0 8px">vs</span>
            <span style="color:#1B4F72">${escHtml(payload.area_b.area)}</span>
          </div>
        </div>
      </div>
      <div class="ai-dash-compare-grid">
        <div class="ai-dash-mini">${renderMiniArea(payload.area_a, '#C84B31')}</div>
        <div class="ai-dash-mini">${renderMiniArea(payload.area_b, '#1B4F72')}</div>
      </div>
      <div class="ai-dash-verdict">
        <b>AI verdict:</b> ${formatBold(escHtml(payload.verdict))}
      </div>
    `;
  }

  // Global API: open / close the dashboard modal
  window.openAreaDashboard = function (payload) {
    const data = payload || window.__lastDashboardPayload;
    if (!data || data.type !== 'dashboard') return;
    const modal = ensureDashboardModal();
    const body = modal.querySelector('#ai-dash-body');
    body.innerHTML = (data.mode === 'compare')
      ? renderCompare(data)
      : renderSingleArea(data);
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
  };

  window.closeAreaDashboard = function () {
    const modal = document.getElementById('ai-dash-modal');
    if (modal) modal.classList.add('hidden');
    document.body.style.overflow = '';
  };

  // Esc to close
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') window.closeAreaDashboard();
  });

})();