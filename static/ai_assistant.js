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

  // ── Suggested chips ──────────────────────────────────
  document.querySelectorAll('.ai-chip').forEach(c => {
    c.addEventListener('click', () => {
      const q = c.dataset.q;
      inputEl.value = q;
      sendQuery();
    });
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
      // Try to plot on map if we're on a page with a global map
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
})();
