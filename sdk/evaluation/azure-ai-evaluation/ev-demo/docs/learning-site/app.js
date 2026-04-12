/* ============================================================
   Azure AI Evaluation Engine — Learning Site JavaScript
   Visualization engines, navigation, and interactivity
   ============================================================ */

// ── Navigation ──────────────────────────────────────────────
const state = { currentSection: 'architecture', traceSteps: {} };

function initNavigation() {
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      const sectionId = item.dataset.section;
      if (sectionId) navigateTo(sectionId);
    });
  });

  document.querySelectorAll('.nav-group-header').forEach(h => {
    h.addEventListener('click', () => {
      h.parentElement.classList.toggle('collapsed');
    });
  });

  // Handle hash navigation
  const hash = location.hash.slice(1);
  if (hash) navigateTo(hash);
  else navigateTo('architecture');

  window.addEventListener('hashchange', () => {
    const h = location.hash.slice(1);
    if (h) navigateTo(h);
  });
}

function navigateTo(sectionId) {
  state.currentSection = sectionId;

  // Update sections
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  const target = document.getElementById(sectionId);
  if (target) target.classList.add('active');

  // Update nav
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const navItem = document.querySelector(`.nav-item[data-section="${sectionId}"]`);
  if (navItem) {
    navItem.classList.add('active');
    // Expand parent group
    const group = navItem.closest('.nav-group');
    if (group) group.classList.remove('collapsed');
  }

  // Update breadcrumb
  const bc = document.getElementById('breadcrumb-current');
  if (bc && navItem) bc.textContent = navItem.textContent.trim();

  // Update URL
  history.replaceState(null, '', '#' + sectionId);

  // Scroll to top of content
  document.querySelector('.content-body')?.scrollTo(0, 0);
  window.scrollTo(0, 0);

  // Close mobile sidebar
  document.querySelector('.sidebar')?.classList.remove('open');
  document.querySelector('.overlay')?.classList.remove('visible');
}

// ── Search ──────────────────────────────────────────────────
function initSearch() {
  const input = document.getElementById('nav-search');
  if (!input) return;

  input.addEventListener('input', (e) => {
    const q = e.target.value.toLowerCase().trim();
    document.querySelectorAll('.nav-item').forEach(item => {
      const text = item.textContent.toLowerCase();
      const match = !q || text.includes(q);
      item.style.display = match ? '' : 'none';
    });
    // Show all groups when searching
    if (q) {
      document.querySelectorAll('.nav-group').forEach(g => g.classList.remove('collapsed'));
    }
  });

  // Keyboard shortcut
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      input.focus();
      input.select();
    }
    if (e.key === 'Escape') {
      input.value = '';
      input.dispatchEvent(new Event('input'));
      input.blur();
    }
  });
}

// ── Mobile ──────────────────────────────────────────────────
function initMobile() {
  document.querySelector('.mobile-toggle')?.addEventListener('click', () => {
    document.querySelector('.sidebar')?.classList.toggle('open');
    document.querySelector('.overlay')?.classList.toggle('visible');
  });
  document.querySelector('.overlay')?.addEventListener('click', () => {
    document.querySelector('.sidebar')?.classList.remove('open');
    document.querySelector('.overlay')?.classList.remove('visible');
  });
}

// ── Back to Top ─────────────────────────────────────────────
function initBackToTop() {
  const btn = document.querySelector('.back-to-top');
  if (!btn) return;
  window.addEventListener('scroll', () => {
    btn.classList.toggle('visible', window.scrollY > 400);
  });
  btn.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));
}

// ── Copy Code ───────────────────────────────────────────────
function initCopyButtons() {
  document.addEventListener('click', (e) => {
    const btn = e.target.closest('.copy-btn');
    if (!btn) return;
    const block = btn.closest('.code-block');
    const code = block?.querySelector('.code-content')?.textContent || '';
    navigator.clipboard.writeText(code).then(() => {
      btn.textContent = 'Copied!';
      btn.classList.add('copied');
      setTimeout(() => { btn.textContent = 'Copy'; btn.classList.remove('copied'); }, 2000);
    });
  });
}

// ── Trace Steps ─────────────────────────────────────────────
function initTraceInteraction() {
  document.addEventListener('click', (e) => {
    const step = e.target.closest('.trace-step');
    if (!step) return;
    step.classList.toggle('expanded');
  });
}

// ══════════════════════════════════════════════════════════════
// VISUALIZATION ENGINES
// ══════════════════════════════════════════════════════════════

// ── Syntax Highlighting ─────────────────────────────────────
// Token-based highlighter: extracts tokens first as placeholders to prevent
// later regex passes from matching inside already-highlighted HTML spans.
function _tokenHighlight(code, tokenRules, fallbackRules) {
  // Escape HTML
  let src = code.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');

  // Phase 1: extract tokens into placeholders
  const tokens = [];
  function placeholder(cls, text) {
    const id = tokens.length;
    tokens.push(`<span class="${cls}">${text}</span>`);
    return `\x00T${id}\x00`;
  }

  // Apply token rules in priority order (strings/comments first)
  for (const rule of tokenRules) {
    src = src.replace(rule.re, function() {
      const m = arguments[0];
      return placeholder(rule.cls, m);
    });
  }

  // Phase 2: apply fallback rules on remaining text (keywords, builtins, etc.)
  for (const rule of fallbackRules) {
    src = src.replace(rule.re, rule.rep);
  }

  // Phase 3: restore placeholders
  src = src.replace(/\x00T(\d+)\x00/g, (_, id) => tokens[+id]);
  return src;
}

const _PY_KWS = /\b(def|class|return|if|elif|else|for|while|import|from|as|with|try|except|finally|raise|yield|async|await|None|True|False|self|pass|break|continue|and|or|not|in|is|lambda|global|nonlocal|assert|del)\b/g;
const _PY_BUILTINS = /\b(print|len|range|list|dict|set|tuple|str|int|float|bool|type|super|isinstance|hasattr|getattr|setattr|property|staticmethod|classmethod|abstractmethod|Optional|List|Dict|Any|Union|Callable|Type|Tuple|Set)\b/g;

function highlightPython(code) {
  return _tokenHighlight(code,
    // Token rules (extracted first, in priority order)
    [
      { re: /"""[\s\S]*?"""|'''[\s\S]*?'''/g, cls: 'str' },  // triple-quoted strings
      { re: /#[^\n]*/g, cls: 'cmt' },                         // comments
      { re: /"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'/g, cls: 'str' }, // single/double strings
      { re: /@\w+(?:\.\w+)*/g, cls: 'dec' },                  // decorators
    ],
    // Fallback rules (applied to remaining plain text)
    [
      { re: _PY_KWS, rep: '<span class="kw">$1</span>' },
      { re: _PY_BUILTINS, rep: '<span class="bi">$1</span>' },
      { re: /\b(\d+\.?\d*)\b/g, rep: '<span class="num">$1</span>' },
      { re: /\b([a-zA-Z_]\w*)\s*(?=\()/g, rep: '<span class="fn">$1</span>' },
    ]
  );
}

function highlightYaml(code) {
  return _tokenHighlight(code,
    [
      { re: /#[^\n]*/g, cls: 'cmt' },
      { re: /"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'/g, cls: 'str' },
      { re: /\$\{[^}]+\}/g, cls: 'dec' },
    ],
    [
      { re: /^(\s*)([\w_.-]+)(\s*:)/gm, rep: '$1<span class="yaml-key">$2</span>$3' },
      { re: /\b(true|false|null)\b/gi, rep: '<span class="kw">$1</span>' },
      { re: /\b(\d+\.?\d*)\b/g, rep: '<span class="num">$1</span>' },
    ]
  );
}

function highlightBash(code) {
  return _tokenHighlight(code,
    [
      { re: /#[^\n]*/g, cls: 'cmt' },
      { re: /"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'/g, cls: 'str' },
    ],
    [
      { re: /(--?[\w-]+)/g, rep: '<span class="fn">$1</span>' },
      { re: /^(\s*)(ev|pip|python|uv|tox)\b/gm, rep: '$1<span class="kw">$2</span>' },
    ]
  );
}

function highlightJson(code) {
  return _tokenHighlight(code,
    [
      { re: /("(?:[^"\\]|\\.)*")\s*(?=:)/g, cls: 'yaml-key' },  // keys
      { re: /"(?:[^"\\]|\\.)*"/g, cls: 'str' },                   // string values
    ],
    [
      { re: /\b(true|false|null)\b/gi, rep: '<span class="kw">$1</span>' },
      { re: /\b(-?\d+\.?\d*)\b/g, rep: '<span class="num">$1</span>' },
    ]
  );
}

const highlighters = { python: highlightPython, yaml: highlightYaml, bash: highlightBash, json: highlightJson };

// ── createCodeBlock ─────────────────────────────────────────
function createCodeBlock(code, language = 'python', { filePath = '', highlightLines = [], title = '' } = {}) {
  const hl = highlighters[language] || (c => c.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'));
  const lines = code.split('\n');
  const linesHtml = lines.map((line, i) => {
    const num = i + 1;
    const isHL = highlightLines.includes(num);
    return `<div class="code-line${isHL ? ' highlighted' : ''}"><span class="line-num">${num}</span><span class="line-content">${hl(line)}</span></div>`;
  }).join('');

  const header = filePath || title
    ? `<div class="code-header"><span class="file-path">${filePath || title}</span><button class="copy-btn">Copy</button></div>`
    : `<div class="code-header"><span>${language}</span><button class="copy-btn">Copy</button></div>`;

  return `<div class="code-block">${header}<div class="code-content"><code>${linesHtml}</code></div></div>`;
}

// ── createInfoCard ──────────────────────────────────────────
function createInfoCard(title, content, type = 'info') {
  return `<div class="info-card ${type}">
    <div class="card-indicator"></div>
    <div class="card-body">
      <div class="card-title">${title}</div>
      <div class="card-text">${content}</div>
    </div>
  </div>`;
}

// ── createTable ─────────────────────────────────────────────
function createTable(headers, rows) {
  const ths = headers.map(h => `<th>${h}</th>`).join('');
  const trs = rows.map(row =>
    `<tr>${row.map(cell => `<td>${cell}</td>`).join('')}</tr>`
  ).join('');
  return `<table class="data-table"><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table>`;
}

// ── createTabs ──────────────────────────────────────────────
function createTabs(tabsData, id) {
  const tabId = id || 'tabs-' + Math.random().toString(36).slice(2, 8);
  const headers = tabsData.map((t, i) =>
    `<button class="tab-header${i === 0 ? ' active' : ''}" data-tab="${tabId}-${i}" onclick="switchTab(this, '${tabId}-${i}')">${t.label}</button>`
  ).join('');
  const panels = tabsData.map((t, i) =>
    `<div class="tab-panel${i === 0 ? ' active' : ''}" id="${tabId}-${i}">${t.content}</div>`
  ).join('');
  return `<div class="tabs"><div class="tab-headers">${headers}</div>${panels}</div>`;
}

function switchTab(btn, panelId) {
  const tabs = btn.closest('.tabs');
  tabs.querySelectorAll('.tab-header').forEach(h => h.classList.remove('active'));
  tabs.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById(panelId)?.classList.add('active');
}

// ── createCallTrace ─────────────────────────────────────────
function createCallTrace(title, steps) {
  const stepsHtml = steps.map((s, i) => {
    const tagClass = s.tag || 'engine';
    return `<div class="trace-step" data-step="${i}">
      <div class="trace-gutter">
        <div class="trace-num">${i + 1}</div>
        ${i < steps.length - 1 ? '<div class="trace-line"></div>' : ''}
      </div>
      <div class="trace-body">
        <div class="trace-caller">
          <span class="module">${s.module || ''}</span>${s.module ? '<span class="arrow">→</span>' : ''}
          <span class="func">${s.func}</span>
          <span class="trace-tag ${tagClass}">${tagClass}</span>
        </div>
        <div class="trace-file">${s.file || ''}</div>
        ${s.detail ? `<div class="trace-detail">${s.detail}</div>` : ''}
      </div>
    </div>`;
  }).join('');

  return `<div class="call-trace">
    <div class="call-trace-header">
      <span>${title}</span>
      <div class="trace-controls">
        <button class="trace-btn" onclick="expandAllTraceSteps(this)">Expand All</button>
      </div>
    </div>
    ${stepsHtml}
  </div>`;
}

function expandAllTraceSteps(btn) {
  const trace = btn.closest('.call-trace');
  const steps = trace.querySelectorAll('.trace-step');
  const allExpanded = [...steps].every(s => s.classList.contains('expanded'));
  steps.forEach(s => s.classList.toggle('expanded', !allExpanded));
  btn.textContent = allExpanded ? 'Expand All' : 'Collapse All';
}

// ── createFlowDiagram (SVG-based) ───────────────────────────
function createFlowDiagram(title, nodes, connections, { width = 900, height = 500, direction = 'TB' } = {}) {
  const nodeWidth = 160, nodeHeight = 52, padX = 40, padY = 30;

  // Position nodes
  nodes.forEach((n, i) => {
    if (n.x === undefined) {
      if (direction === 'TB') {
        n.x = n.col !== undefined ? padX + n.col * (nodeWidth + padX) : padX + (i % 4) * (nodeWidth + padX);
        n.y = n.row !== undefined ? padY + n.row * (nodeHeight + padY) : padY + Math.floor(i / 4) * (nodeHeight + padY);
      } else {
        n.x = n.col !== undefined ? padX + n.col * (nodeWidth + padX) : padX + Math.floor(i / 3) * (nodeWidth + padX);
        n.y = n.row !== undefined ? padY + n.row * (nodeHeight + padY) : padY + (i % 3) * (nodeHeight + padY);
      }
    }
  });

  // Auto-calc SVG size
  const maxX = Math.max(...nodes.map(n => n.x + nodeWidth)) + padX;
  const maxY = Math.max(...nodes.map(n => n.y + nodeHeight)) + padY;
  const svgW = Math.max(width, maxX);
  const svgH = Math.max(height, maxY);

  const nodeMap = {};
  nodes.forEach(n => { nodeMap[n.id] = n; });

  // Build arrows
  const arrowsSvg = connections.map(c => {
    const from = nodeMap[c.from], to = nodeMap[c.to];
    if (!from || !to) return '';
    const fromCx = from.x + nodeWidth / 2, fromCy = from.y + nodeHeight;
    const toCx = to.x + nodeWidth / 2, toCy = to.y;
    const midY = (fromCy + toCy) / 2;
    const anim = c.animated !== false ? ' animated' : '';
    const label = c.label ? `<text class="flow-label" x="${(fromCx + toCx) / 2 + 4}" y="${midY - 4}">${c.label}</text>` : '';
    return `<path class="flow-arrow${anim}" d="M${fromCx},${fromCy} C${fromCx},${midY} ${toCx},${midY} ${toCx},${toCy}" />
    ${label}`;
  }).join('');

  // Build nodes
  const nodesSvg = nodes.map(n => {
    const typeClass = `node-${n.type || 'class'}`;
    const subtitle = n.subtitle ? `<text class="node-subtitle" x="${n.x + nodeWidth / 2}" y="${n.y + 36}" text-anchor="middle">${n.subtitle}</text>` : '';
    const icon = n.icon ? `<text x="${n.x + 12}" y="${n.y + 30}" font-size="14">${n.icon}</text>` : '';
    const textX = n.icon ? n.x + nodeWidth / 2 + 8 : n.x + nodeWidth / 2;
    return `<g class="flow-node ${typeClass}" data-id="${n.id}" onclick="showNodeDetail(this, '${n.id}')">
      <rect x="${n.x}" y="${n.y}" width="${nodeWidth}" height="${nodeHeight}" />
      ${icon}
      <text x="${textX}" y="${n.y + (n.subtitle ? 22 : 30)}" text-anchor="middle" font-weight="600" font-size="12">${n.label}</text>
      ${subtitle}
    </g>`;
  }).join('');

  return `<div class="flow-diagram">
    ${title ? `<div style="text-align:center;margin-bottom:12px;font-weight:600;color:var(--text-secondary);font-size:14px">${title}</div>` : ''}
    <svg width="${svgW}" height="${svgH}" viewBox="0 0 ${svgW} ${svgH}" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <marker id="arrowhead" viewBox="0 0 10 7" refX="9" refY="3.5" markerWidth="8" markerHeight="6" orient="auto">
          <polygon points="0 0, 10 3.5, 0 7" fill="var(--text-muted)" />
        </marker>
      </defs>
      ${arrowsSvg}
      ${nodesSvg}
    </svg>
  </div>`;
}

// Node detail popup
window._nodeDetails = {};
function registerNodeDetails(details) {
  Object.assign(window._nodeDetails, details);
}

function _ensureDrawer() {
  let overlay = document.getElementById('node-popup-overlay');
  let popup = document.getElementById('node-popup');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'node-popup-overlay';
    overlay.className = 'node-popup-overlay';
    overlay.addEventListener('click', closeNodeDrawer);
    document.body.appendChild(overlay);
  }
  if (!popup) {
    popup = document.createElement('div');
    popup.id = 'node-popup';
    popup.className = 'node-popup';
    document.body.appendChild(popup);
  }
  return { overlay, popup };
}

function closeNodeDrawer() {
  const overlay = document.getElementById('node-popup-overlay');
  const popup = document.getElementById('node-popup');
  if (overlay) overlay.classList.remove('visible');
  if (popup) popup.classList.remove('visible');
}

function showNodeDetail(el, nodeId) {
  const detail = window._nodeDetails[nodeId];
  if (!detail) return;

  const { overlay, popup } = _ensureDrawer();

  const fileBadge = detail.file
    ? `<span class="node-file-badge">${detail.file}</span>`
    : '';

  const codeHtml = detail.code
    ? createCodeBlock(detail.code, detail.lang || 'python', { title: detail.file || '' })
    : '';

  popup.innerHTML = `
    <div class="node-popup-header">
      <h4>${detail.title || nodeId}</h4>
      <button class="popup-close" onclick="closeNodeDrawer()">&times;</button>
    </div>
    <div class="node-popup-body">
      ${fileBadge}
      <div class="node-desc">${detail.description || ''}</div>
      ${codeHtml}
    </div>
  `;

  overlay.classList.add('visible');
  popup.classList.add('visible');

  // Close on Escape
  const escHandler = (e) => {
    if (e.key === 'Escape') { closeNodeDrawer(); document.removeEventListener('keydown', escHandler); }
  };
  document.addEventListener('keydown', escHandler);
}

// ── createSequenceDiagram ───────────────────────────────────
function createSequenceDiagram(title, actors, messages) {
  const actorW = 120, actorGap = 40, padTop = 60, msgGap = 50, padBottom = 40;
  const totalW = actors.length * (actorW + actorGap) - actorGap + 80;
  const totalH = padTop + messages.length * msgGap + padBottom + 40;

  const actorPositions = {};
  actors.forEach((a, i) => {
    actorPositions[a.id] = 40 + i * (actorW + actorGap) + actorW / 2;
  });

  const actorsSvg = actors.map((a, i) => {
    const x = actorPositions[a.id];
    const colors = { engine: 'var(--accent)', evaluator: 'var(--green)', target: 'var(--orange)', data: 'var(--purple)', config: 'var(--yellow)', external: 'var(--cyan)' };
    const color = colors[a.type] || 'var(--accent)';
    return `
      <rect x="${x - actorW / 2}" y="10" width="${actorW}" height="32" rx="6" fill="none" stroke="${color}" stroke-width="1.5"/>
      <text x="${x}" y="30" text-anchor="middle" font-size="12" font-weight="600" fill="var(--text-primary)">${a.label}</text>
      <line x1="${x}" y1="42" x2="${x}" y2="${totalH - 10}" stroke="var(--border)" stroke-width="1" stroke-dasharray="4 3"/>
    `;
  }).join('');

  const msgsSvg = messages.map((m, i) => {
    const y = padTop + i * msgGap;
    const x1 = actorPositions[m.from];
    const x2 = actorPositions[m.to];
    if (x1 === undefined || x2 === undefined) return '';

    const isSelf = m.from === m.to;
    const isReturn = m.type === 'return';
    const dash = isReturn ? ' stroke-dasharray="5 3"' : '';
    const color = isReturn ? 'var(--text-muted)' : 'var(--accent)';

    if (isSelf) {
      return `
        <path d="M${x1},${y} C${x1 + 50},${y} ${x1 + 50},${y + 25} ${x1},${y + 25}" fill="none" stroke="${color}" stroke-width="1.5"${dash} marker-end="url(#arrowhead)"/>
        <text x="${x1 + 55}" y="${y + 16}" font-size="11" fill="var(--text-secondary)">${m.label}</text>
      `;
    }

    const textX = (x1 + x2) / 2;
    const textAnchor = 'middle';
    return `
      <line x1="${x1}" y1="${y}" x2="${x2}" y2="${y}" stroke="${color}" stroke-width="1.5"${dash} marker-end="url(#arrowhead)"/>
      <text x="${textX}" y="${y - 6}" text-anchor="${textAnchor}" font-size="11" fill="var(--text-secondary)">${m.label}</text>
    `;
  }).join('');

  return `<div class="sequence-diagram">
    ${title ? `<div style="text-align:center;margin-bottom:12px;font-weight:600;color:var(--text-secondary);font-size:14px">${title}</div>` : ''}
    <svg width="${totalW}" height="${totalH}" viewBox="0 0 ${totalW} ${totalH}" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <marker id="arrowhead" viewBox="0 0 10 7" refX="9" refY="3.5" markerWidth="8" markerHeight="6" orient="auto">
          <polygon points="0 0, 10 3.5, 0 7" fill="var(--text-muted)" />
        </marker>
      </defs>
      ${actorsSvg}
      ${msgsSvg}
    </svg>
  </div>`;
}

// ── createClassDiagram ──────────────────────────────────────
function createClassDiagram(title, classes) {
  const boxW = 220, boxPad = 30, methodH = 18;

  // Calculate box heights
  classes.forEach(c => {
    const methodCount = (c.methods || []).length;
    c._h = 40 + methodCount * methodH + 12;
  });

  // Auto-layout
  classes.forEach((c, i) => {
    if (c.x === undefined) {
      c.x = (c.col || i % 3) * (boxW + boxPad * 2) + boxPad;
      c.y = (c.row || Math.floor(i / 3)) * 160 + boxPad;
    }
  });

  const maxX = Math.max(...classes.map(c => c.x + boxW)) + boxPad;
  const maxY = Math.max(...classes.map(c => c.y + c._h)) + boxPad;

  const classMap = {};
  classes.forEach(c => { classMap[c.id] = c; });

  // Draw inheritance arrows
  const arrows = classes.filter(c => c.parent).map(c => {
    const parent = classMap[c.parent];
    if (!parent) return '';
    const cx = c.x + boxW / 2, cy = c.y;
    const px = parent.x + boxW / 2, py = parent.y + parent._h;
    return `<line x1="${cx}" y1="${cy}" x2="${px}" y2="${py}" stroke="var(--text-muted)" stroke-width="1.5" marker-end="url(#triangle)"/>`;
  }).join('');

  // Draw class boxes
  const boxes = classes.map(c => {
    const typeColors = { abstract: 'var(--accent)', concrete: 'var(--green)', mixin: 'var(--purple)' };
    const color = typeColors[c.type] || 'var(--accent)';
    const methods = (c.methods || []).map((m, i) => {
      const prefix = m.abstract ? '+ ' : m.static ? '- ' : '';
      return `<text x="${c.x + 12}" y="${c.y + 44 + i * methodH}" font-size="11" fill="var(--text-secondary)" font-family="'Fira Code', monospace">${prefix}${m.name}()</text>`;
    }).join('');

    const badge = c.type === 'abstract' ? ' «abstract»' : c.type === 'mixin' ? ' «mixin»' : '';
    return `
      <g class="flow-node">
        <rect x="${c.x}" y="${c.y}" width="${boxW}" height="${c._h}" rx="8" fill="var(--bg-card)" stroke="${color}" stroke-width="1.5"/>
        <line x1="${c.x}" y1="${c.y + 32}" x2="${c.x + boxW}" y2="${c.y + 32}" stroke="var(--border)" stroke-width="1"/>
        <text x="${c.x + boxW / 2}" y="${c.y + 20}" text-anchor="middle" font-size="13" font-weight="600" fill="${color}">${c.label}${badge ? `<tspan font-size="9" fill="var(--text-muted)">${badge}</tspan>` : ''}</text>
        ${methods}
      </g>
    `;
  }).join('');

  return `<div class="class-diagram">
    ${title ? `<div style="text-align:center;margin-bottom:12px;font-weight:600;color:var(--text-secondary);font-size:14px">${title}</div>` : ''}
    <svg width="${maxX}" height="${maxY}" viewBox="0 0 ${maxX} ${maxY}" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <marker id="triangle" viewBox="0 0 12 12" refX="6" refY="6" markerWidth="10" markerHeight="10" orient="auto">
          <path d="M0,0 L12,6 L0,12 z" fill="none" stroke="var(--text-muted)" stroke-width="1"/>
        </marker>
      </defs>
      ${arrows}
      ${boxes}
    </svg>
  </div>`;
}

// ── createMetricCard ────────────────────────────────────────
function createMetricCard(ev) {
  const badgeClass = {
    Quality: 'badge-quality', Safety: 'badge-safety', Agent: 'badge-agent',
    Reference: 'badge-reference', Retrieval: 'badge-retrieval', Composite: 'badge-composite'
  }[ev.category] || 'badge-quality';

  const backendColors = { Prompty: 'var(--accent)', RAI: 'var(--red)', Local: 'var(--green)', Multi: 'var(--purple)' };
  const scaleColor = backendColors[ev.backend] || 'var(--accent)';
  const scaleWidth = ev.scaleMax ? '100%' : '0%';

  const scaleBar = ev.scaleMax ? `
    <div class="metric-scale">
      <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text-muted)">
        <span>Scale: ${ev.scaleMin || 0} – ${ev.scaleMax}</span>
      </div>
      <div class="scale-bar">
        <div class="scale-fill" style="width:${scaleWidth};background:${scaleColor}"></div>
      </div>
    </div>` : '';

  const metaTags = [
    ev.backend ? `<span class="meta-tag" style="color:${scaleColor}">${ev.backend}</span>` : '',
    ev.metric ? `<span class="meta-tag">metric: ${ev.metric}</span>` : '',
  ].filter(Boolean).join('');

  const io = ev.inputs ? `
    <div class="metric-io">
      <div><strong>Inputs:</strong> ${ev.inputs.map(i => `<code>${i}</code>`).join(', ')}</div>
      ${ev.outputs ? `<div><strong>Outputs:</strong> ${ev.outputs.map(o => `<code>${o}</code>`).join(', ')}</div>` : ''}
    </div>` : '';

  return `<div class="metric-card">
    <div class="metric-card-header">
      <span class="metric-card-name">${ev.name}</span>
      <span class="metric-badge ${badgeClass}">${ev.category}</span>
    </div>
    <p style="font-size:12px;color:var(--text-secondary);margin:4px 0 8px">${ev.description || ''}</p>
    ${scaleBar}
    <div class="metric-meta">${metaTags}</div>
    ${io}
  </div>`;
}

// ── createConfigSchema ──────────────────────────────────────
function createConfigSchema(schema, depth = 0) {
  return schema.map(node => {
    const hasChildren = node.children && node.children.length > 0;
    const toggle = hasChildren ? `<span class="schema-toggle">▼</span>` : `<span class="schema-toggle" style="visibility:hidden">▼</span>`;
    const required = node.required ? `<span class="schema-required">*</span>` : '';
    const def = node.default !== undefined ? `<span class="schema-default">= ${JSON.stringify(node.default)}</span>` : '';
    const desc = node.desc ? `<span class="schema-desc"># ${node.desc}</span>` : '';
    const typeStr = node.type ? `<span class="schema-type">${node.type}</span>` : '';
    const childrenHtml = hasChildren ? `<div class="schema-children">${createConfigSchema(node.children, depth + 1)}</div>` : '';

    return `<div class="schema-node${depth === 0 ? '' : ''}">
      <div class="schema-node-header" onclick="this.parentElement.classList.toggle('collapsed')">
        ${toggle}
        <span class="schema-key">${node.key}</span>
        ${typeStr}${required}${def}${desc}
      </div>
      ${childrenHtml}
    </div>`;
  }).join('');
}

function renderConfigSchema(containerId, schema) {
  const el = document.getElementById(containerId);
  if (el) el.innerHTML = `<div class="schema-tree">${createConfigSchema(schema)}</div>`;
}

// ── Init ────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initNavigation();
  initSearch();
  initMobile();
  initBackToTop();
  initCopyButtons();
  initTraceInteraction();
});
