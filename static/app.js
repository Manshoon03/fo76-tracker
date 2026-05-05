// ── Table filter ──────────────────────────────────────────────────────────
function filterTable(query, tableId) {
  const table = document.getElementById(tableId);
  if (!table) return;
  const rows = table.querySelectorAll('tbody tr');
  const q = query.toLowerCase();
  rows.forEach(row => {
    row.style.display = row.textContent.toLowerCase().includes(q) ? '' : 'none';
  });
}

// ── Panel toggle ──────────────────────────────────────────────────────────
function togglePanel(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.toggle('open');
  if (el.classList.contains('open')) {
    localStorage.setItem('panel_' + id, '1');
  } else {
    localStorage.removeItem('panel_' + id);
  }
}

// ── Delete confirm ────────────────────────────────────────────────────────
function confirmDelete(msg) {
  return confirm(msg || 'Delete this item? This cannot be undone.');
}

// ── Auto-dismiss flash messages ───────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const flashes = document.querySelectorAll('.flash');
  if (flashes.length) {
    setTimeout(() => {
      flashes.forEach(el => {
        el.style.transition = 'opacity 0.4s';
        el.style.opacity = '0';
        setTimeout(() => el.remove(), 400);
      });
    }, 4000);
  }

  // Set today's date on date inputs that are empty
  const today = new Date().toISOString().split('T')[0];
  document.querySelectorAll('input[type=date]').forEach(inp => {
    if (!inp.value) inp.value = today;
  });

  // Auto-focus first text input in open panel
  const openPanel = document.querySelector('.add-panel.open input[type=text]');
  if (openPanel) openPanel.focus();

  // Restore collapsible panel states from localStorage
  document.querySelectorAll('.add-panel[id]').forEach(function(panel) {
    if (!panel.classList.contains('open') && localStorage.getItem('panel_' + panel.id) === '1') {
      panel.classList.add('open');
    }
  });

  // Scroll-to-top button
  const scrollBtn = document.getElementById('scrollTopBtn');
  if (scrollBtn) {
    window.addEventListener('scroll', function() {
      scrollBtn.style.display = window.scrollY > 300 ? 'flex' : 'none';
    }, { passive: true });
    scrollBtn.addEventListener('click', function() {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    });
  }
});

// ── Build SPECIAL total live update ──────────────────────────────────────
function updateSpecialTotal() {
  const fields = ['s','p','e','c','i','a','l'];
  let total = 0;
  fields.forEach(f => {
    const el = document.getElementById('special_' + f);
    if (el) total += parseInt(el.value) || 0;
  });
  const display = document.getElementById('specialTotal');
  if (display) {
    display.textContent = total + ' / 56';
    display.className = total > 56 ? 'pts-warn' : 'pts-ok';
  }
}

// ── Vendor price diff calculation ─────────────────────────────────────────
function updatePriceDiff() {
  const myPrice  = parseFloat(document.getElementById('my_price')?.value) || 0;
  const avgPrice = parseFloat(document.getElementById('avg_market_price')?.value) || 0;
  const display  = document.getElementById('priceDiff');
  if (display && avgPrice > 0) {
    const diff = ((myPrice / avgPrice - 1) * 100).toFixed(1);
    display.textContent = (diff > 0 ? '+' : '') + diff + '%';
    display.className = diff > 0 ? 'diff-over' : 'diff-under';
  } else if (display) {
    display.textContent = '';
  }
}

// ── Toast notifications ────────────────────────────────────────────────────
function showToast(msg, type = 'success') {
  const container = document.getElementById('toastContainer');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = msg;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.3s';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}

// ── Nuke code reset countdown ─────────────────────────────────────────────
function startNukeCountdown(elementId) {
  const el = document.getElementById(elementId);
  if (!el) return;
  function update() {
    const now = new Date();
    const target = new Date(now);
    target.setUTCHours(16, 0, 0, 0); // Tuesday noon ET ≈ 16:00 UTC (EDT)
    let diff = (2 - target.getUTCDay() + 7) % 7;
    if (diff === 0 && target <= now) diff = 7;
    target.setUTCDate(target.getUTCDate() + diff);
    const ms = target - now;
    const d = Math.floor(ms / 86400000);
    const h = Math.floor((ms % 86400000) / 3600000);
    const m = Math.floor((ms % 3600000) / 60000);
    const parts = [];
    if (d > 0) parts.push(d + 'd');
    if (h > 0 || d > 0) parts.push(h + 'h');
    parts.push(m + 'm');
    el.textContent = parts.join(' ');
  }
  update();
  setInterval(update, 60000);
}

// ── Quick Log Modal ────────────────────────────────────────────────────────
const _QL_INV_DL_MAP = { Aid:'qlDlAid', Chem:'qlDlAid', Ammo:'qlDlAmmo', 'Food/Drink':'qlDlFood', Junk:'qlDlComponent', Component:'qlDlComponent' };
function updateQlInvName(sel) {
  const el = document.getElementById('qlInvName');
  if (el) el.setAttribute('list', _QL_INV_DL_MAP[sel.value] || '');
}

function openQuickLog() {
  document.getElementById('qlOverlay').classList.add('open');
  // Focus first visible input
  setTimeout(() => {
    const active = document.querySelector('.ql-fields.active input, .ql-fields.active select');
    if (active) active.focus();
  }, 50);
}

function closeQuickLog() {
  document.getElementById('qlOverlay').classList.remove('open');
}

function closeQuickLogIfOverlay(e) {
  if (e.target === document.getElementById('qlOverlay')) closeQuickLog();
}

function switchQlSection(section, btn) {
  // Update hidden input
  document.getElementById('qlSection').value = section;
  // Switch tabs
  document.querySelectorAll('.ql-tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  // Switch field groups
  document.querySelectorAll('.ql-fields').forEach(f => f.classList.remove('active'));
  document.getElementById('ql-' + section)?.classList.add('active');
  // Load challenges if switching to challenge section
  if (section === 'challenge') loadChallengesForQuickLog();
  if (section === 'repeatable') loadRepeatables();
  // Hide submit button for repeatable tab (actions are inline)
  const submitBtn = document.querySelector('#qlForm button[type=submit]');
  if (submitBtn) submitBtn.style.display = section === 'repeatable' ? 'none' : '';
  // Focus first input
  setTimeout(() => {
    const first = document.querySelector('.ql-fields.active input, .ql-fields.active select');
    if (first) first.focus();
  }, 30);
}

async function loadChallengesForQuickLog() {
  const sel = document.getElementById('qlChallengeSelect');
  if (sel.dataset.loaded) return;
  try {
    const resp = await fetch('/api/challenges-active');
    const list = await resp.json();
    sel.innerHTML = list.length
      ? list.map(c => `<option value="${c.id}">[${c.ctype}] ${c.name} (${c.progress}/${c.target})</option>`).join('')
      : '<option value="">No active challenges</option>';
    sel.dataset.loaded = '1';
  } catch {
    sel.innerHTML = '<option value="">Failed to load</option>';
  }
}

async function loadRepeatables() {
  const container = document.getElementById('qlRepeatableList');
  if (!container || container.dataset.loaded) return;
  try {
    const items = await fetch('/api/challenges-repeatables').then(r => r.json());
    container.innerHTML = '';
    if (!items.length) {
      container.innerHTML = '<span class="dim" style="font-size:11px">No repeatable Daily/Weekly challenges found.<br>Add challenges with the ↺ Repeatable flag in Challenges.</span>';
      return;
    }
    let currentType = '';
    items.forEach(item => {
      if (item.ctype !== currentType) {
        currentType = item.ctype;
        const hdr = document.createElement('div');
        hdr.className = 'dim';
        hdr.style.cssText = 'font-size:10px;letter-spacing:.06em;margin-top:6px;padding-bottom:2px;border-bottom:1px solid var(--border)';
        hdr.textContent = currentType.toUpperCase();
        container.appendChild(hdr);
      }
      const row = document.createElement('div');
      row.id = `ql-rep-row-${item.id}`;
      row.style.cssText = 'display:flex;align-items:center;gap:8px;padding:3px 0';

      const nameSpan = document.createElement('span');
      nameSpan.style.cssText = 'flex:1;font-size:12px';
      nameSpan.textContent = item.name;
      if (item.times_completed > 0) {
        const badge = document.createElement('span');
        badge.id = `ql-rep-badge-${item.id}`;
        badge.className = 'accent';
        badge.style.cssText = 'font-size:10px;margin-left:5px';
        badge.textContent = `x${item.times_completed}`;
        nameSpan.appendChild(badge);
      }
      row.appendChild(nameSpan);

      const btns = document.createElement('div');
      btns.style.cssText = 'display:flex;align-items:center;gap:4px';

      if (item.target > 1) {
        const prog = document.createElement('span');
        prog.id = `ql-rep-prog-${item.id}`;
        prog.className = 'dim';
        prog.style.cssText = 'font-size:10px;min-width:34px;text-align:center';
        prog.textContent = `${item.progress}/${item.target}`;
        btns.appendChild(prog);

        const incBtn = document.createElement('button');
        incBtn.className = 'btn-sm btn-keep';
        incBtn.textContent = '+1';
        incBtn.title = 'Add 1 progress';
        incBtn.onclick = () => qlRepeatableIncrement(item.id);
        btns.appendChild(incBtn);
      }

      const doneBtn = document.createElement('button');
      doneBtn.className = 'btn-sm btn-secondary';
      doneBtn.textContent = '↺ Done';
      doneBtn.title = 'Mark complete (auto-resets)';
      doneBtn.onclick = () => qlRepeatableDone(item.id);
      btns.appendChild(doneBtn);

      row.appendChild(btns);
      container.appendChild(row);
    });
    container.dataset.loaded = '1';
  } catch {
    container.innerHTML = '<span class="dim" style="font-size:11px">Failed to load.</span>';
  }
}

function qlRepeatableUpdateBadge(id, timesCompleted) {
  // Update or create the x-count badge
  let badge = document.getElementById(`ql-rep-badge-${id}`);
  if (!badge) {
    const row = document.getElementById(`ql-rep-row-${id}`);
    const nameSpan = row?.querySelector('span');
    if (nameSpan) {
      badge = document.createElement('span');
      badge.id = `ql-rep-badge-${id}`;
      badge.className = 'accent';
      badge.style.cssText = 'font-size:10px;margin-left:5px';
      nameSpan.appendChild(badge);
    }
  }
  if (badge) badge.textContent = `x${timesCompleted}`;
}

async function qlRepeatableIncrement(id) {
  const r = await fetch(`/challenges/${id}/increment`, {method:'POST'}).then(r => r.json());
  if (!r.ok) return;
  const prog = document.getElementById(`ql-rep-prog-${id}`);
  if (r.repeatable) {
    if (prog) prog.textContent = `0/${r.target}`;
    qlRepeatableUpdateBadge(id, r.times_completed);
    showToast(`Done! x${r.times_completed} — ${r.name}`, 'success');
  } else {
    if (prog) prog.textContent = `${r.progress}/${r.target}`;
  }
}

async function qlRepeatableDone(id) {
  const r = await fetch(`/challenges/${id}/toggle`, {method:'POST'}).then(r => r.json());
  if (!r.ok || !r.repeatable) return;
  const prog = document.getElementById(`ql-rep-prog-${id}`);
  if (prog) prog.textContent = `0/${r.target}`;
  qlRepeatableUpdateBadge(id, r.times_completed);
  showToast(`Done! x${r.times_completed} — ${r.name}`, 'success');
}

async function submitQuickLog(e) {
  e.preventDefault();
  const form = document.getElementById('qlForm');
  const btn  = form.querySelector('button[type=submit]');
  const status = document.getElementById('qlStatus');
  btn.disabled = true;
  btn.textContent = '...';
  try {
    const resp   = await fetch('/quick-log', { method: 'POST', body: new FormData(form) });
    const result = await resp.json();
    if (result.ok) {
      showToast(result.message, 'success');
      // Reset only the dynamic fields, keep section selection
      const activeFields = document.querySelector('.ql-fields.active');
      activeFields?.querySelectorAll('input[type=text], input[type=number]').forEach(i => i.value = '');
      activeFields?.querySelectorAll('select').forEach(s => s.selectedIndex = 0);
      activeFields?.querySelectorAll('input[type=checkbox]').forEach(c => c.checked = false);
      // Restore source default
      const src = activeFields?.querySelector('input[name=ql_source]');
      if (src) src.value = 'Vendor';
      // Reload challenges list next time
      const csel = document.getElementById('qlChallengeSelect');
      if (csel) delete csel.dataset.loaded;
      // Close unless "keep open" is checked
      if (!document.getElementById('qlKeepOpen')?.checked) closeQuickLog();
    } else {
      showToast(result.message || 'Error logging', 'error');
    }
  } catch {
    showToast('Server error', 'error');
  }
  btn.disabled = false;
  btn.textContent = 'Log It';
}

// ── Lunchbox burst animation ───────────────────────────────────────────────
function lunchboxBurst(fromEl) {
  const symbols = ['⭐','★','💰','✦','☢','✓','+','🎊','◈','⬡'];
  const colors  = ['var(--gold)','var(--accent)','#fff','var(--amber)','#a3e635'];
  const rect = fromEl.getBoundingClientRect();
  const cx = rect.left + rect.width  / 2;
  const cy = rect.top  + rect.height / 2;

  // Brief screen flash
  const flash = document.createElement('div');
  flash.className = 'lunchbox-screen-flash';
  document.body.appendChild(flash);
  flash.addEventListener('animationend', () => flash.remove());

  // Row highlight
  const rowId = fromEl.id.replace('tbtn-', 'crow-');
  const row = document.getElementById(rowId);
  if (row) {
    row.classList.remove('row-complete-flash');
    void row.offsetWidth; // force reflow to restart animation
    row.classList.add('row-complete-flash');
    row.addEventListener('animationend', () => row.classList.remove('row-complete-flash'), { once: true });
  }

  // Particles
  const count = 16;
  for (let i = 0; i < count; i++) {
    const el = document.createElement('span');
    el.className = 'lunchbox-particle';
    el.textContent = symbols[Math.floor(Math.random() * symbols.length)];
    el.style.color = colors[Math.floor(Math.random() * colors.length)];
    el.style.fontSize = (11 + Math.random() * 14) + 'px';

    const angle = (i / count) * Math.PI * 2 + (Math.random() - 0.5) * 0.8;
    const dist  = 55 + Math.random() * 130;
    const tx    = Math.cos(angle) * dist;
    const ty    = Math.sin(angle) * dist - 20; // bias upward slightly
    const rot   = (Math.random() * 720 - 360) + 'deg';

    el.style.left = (cx - 8) + 'px';
    el.style.top  = (cy - 8) + 'px';
    el.style.setProperty('--tx', tx + 'px');
    el.style.setProperty('--ty', ty + 'px');
    el.style.setProperty('--rot', rot);
    el.style.animationDelay    = (Math.random() * 0.1) + 's';
    el.style.animationDuration = (0.9 + Math.random() * 0.5) + 's';

    document.body.appendChild(el);
    el.addEventListener('animationend', () => el.remove());
  }
}

// ── Challenge AJAX actions ─────────────────────────────────────────────────
async function toggleChallenge(id) {
  try {
    const resp = await fetch(`/challenges/${id}/toggle`, { method: 'POST' });
    const r = await resp.json();
    if (!r.ok) return;
    const row = document.getElementById('crow-' + id);
    const btn = document.getElementById('tbtn-' + id);
    if (r.repeatable) {
      // Reset progress bar to 0, ensure row is never crossed out
      row?.classList.remove('completed-row');
      const pbar  = document.getElementById('pbar-' + id);
      const ptext = document.getElementById('ptext-' + id);
      if (pbar)  { pbar.style.width = '0%'; pbar.classList.remove('complete'); }
      if (ptext) ptext.textContent = `0/${r.target}`;
      if (btn) { btn.textContent = '✓'; btn.className = 'btn-sm btn-keep'; btn.title = 'Mark complete'; }
      if (btn) lunchboxBurst(btn);
      showToast(`Done! x${r.times_completed} — ${r.name}`, 'success');
    } else if (r.completed) {
      row?.classList.add('completed-row');
      if (btn) { btn.textContent = '↩'; btn.className = 'btn-sm btn-secondary'; btn.title = 'Unmark'; }
      if (btn) lunchboxBurst(btn);
      showToast(`Complete: ${r.name}`, 'success');
      // Fade row out after animation if we're on the incomplete view
      if (!window.location.search.includes('type=all') && !window.location.search.includes('type=done')) {
        setTimeout(() => {
          if (row) {
            row.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
            row.style.opacity = '0';
            row.style.transform = 'translateX(20px)';
            setTimeout(() => row.remove(), 500);
          }
        }, 1500);
      }
    } else {
      row?.classList.remove('completed-row');
      if (btn) { btn.textContent = '✓'; btn.className = 'btn-sm btn-keep'; btn.title = 'Mark complete'; }
      showToast(`Unmarked: ${r.name}`, 'info');
    }
  } catch {
    showToast('Error', 'error');
  }
}

async function incrementChallenge(id) {
  try {
    const resp = await fetch(`/challenges/${id}/increment`, { method: 'POST' });
    const r = await resp.json();
    if (!r.ok) return;
    const pbar  = document.getElementById('pbar-' + id);
    const ptext = document.getElementById('ptext-' + id);
    const pct   = Math.min(Math.round(r.progress / r.target * 100), 100);
    if (pbar)  { pbar.style.width = pct + '%'; if (r.completed) pbar.classList.add('complete'); }
    if (ptext) ptext.textContent = `${r.progress}/${r.target}`;
    if (r.repeatable) {
      const row2 = document.getElementById('crow-' + id);
      row2?.classList.remove('completed-row');
      if (pbar) { pbar.style.width = '0%'; pbar.classList.remove('complete'); }
      if (ptext) ptext.textContent = `0/${r.target}`;
      const incBtn = document.querySelector(`#crow-${id} .btn-keep`);
      if (incBtn) lunchboxBurst(incBtn);
      showToast(`Done! x${r.times_completed} — ${r.name}`, 'success');
    } else if (r.completed) {
      showToast(`Complete: ${r.name}`, 'success');
      const row = document.getElementById('crow-' + id);
      row?.classList.add('completed-row');
      const btn = document.getElementById('tbtn-' + id);
      if (btn) { btn.textContent = '↩'; btn.className = 'btn-sm btn-secondary'; }
      if (btn) lunchboxBurst(btn);
    } else {
      showToast(`${r.name}: ${r.progress}/${r.target}`, 'info');
    }
  } catch {
    showToast('Error', 'error');
  }
}

// ── Universal item autocomplete ───────────────────────────────────────────
function initItemAutocomplete(inputId, catSelectId) {
  const input  = document.getElementById(inputId);
  const catSel = catSelectId ? document.getElementById(catSelectId) : null;
  if (!input) return;

  const wrap = input.parentNode;
  wrap.style.position = 'relative';

  const dropdown = document.createElement('div');
  dropdown.className = 'ac-dropdown';
  wrap.appendChild(dropdown);

  let timer, activeIdx = -1, items = [];

  function render() {
    dropdown.innerHTML = '';
    if (!items.length) { dropdown.style.display = 'none'; return; }
    items.forEach((item, i) => {
      const row = document.createElement('div');
      row.className = 'ac-item';
      row.innerHTML = `<span>${item.name}</span><span class="ac-cat">${item.category}</span>`;
      row.addEventListener('mousedown', e => { e.preventDefault(); pick(i); });
      dropdown.appendChild(row);
    });
    dropdown.style.display = 'block';
    activeIdx = -1;
  }

  function pick(i) {
    const item = items[i];
    if (!item) return;
    input.value = item.name;
    if (catSel) {
      const opt = Array.from(catSel.options).find(o => o.value === item.category);
      if (opt) {
        catSel.value = item.category;
        catSel.dispatchEvent(new Event('change'));
      }
    }
    items = [];
    dropdown.style.display = 'none';
  }

  input.addEventListener('input', function() {
    clearTimeout(timer);
    const q = this.value.trim();
    if (q.length < 2) { items = []; dropdown.style.display = 'none'; return; }
    timer = setTimeout(async () => {
      try {
        items = await fetch(`/api/item-search?q=${encodeURIComponent(q)}`).then(r => r.json());
        render();
      } catch { dropdown.style.display = 'none'; }
    }, 180);
  });

  input.addEventListener('keydown', function(e) {
    if (dropdown.style.display === 'none') return;
    const rows = dropdown.querySelectorAll('.ac-item');
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      activeIdx = Math.min(activeIdx + 1, rows.length - 1);
      rows.forEach((r, i) => r.classList.toggle('active', i === activeIdx));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      activeIdx = Math.max(activeIdx - 1, 0);
      rows.forEach((r, i) => r.classList.toggle('active', i === activeIdx));
    } else if (e.key === 'Enter' && activeIdx >= 0) {
      e.preventDefault();
      pick(activeIdx);
    } else if (e.key === 'Escape') {
      items = []; dropdown.style.display = 'none';
    }
  });

  document.addEventListener('click', e => {
    if (!wrap.contains(e.target)) { items = []; dropdown.style.display = 'none'; }
  });
}

// ── Sidebar toggle ─────────────────────────────────────────────────────────
function toggleSidebar() {
  const open = document.documentElement.classList.toggle('sidebar-open');
  localStorage.setItem('sidebarOpen', open ? 'true' : 'false');
}

// ── Theme switching ────────────────────────────────────────────────────────
function setTheme(name) {
  document.documentElement.setAttribute('data-theme', name);
  localStorage.setItem('fo76theme', name);
  // Update active dot
  document.querySelectorAll('.theme-dot').forEach(d => {
    d.classList.toggle('active-theme', d.dataset.theme === name);
  });
}

// Mark active theme dot on load
document.addEventListener('DOMContentLoaded', () => {
  const t = localStorage.getItem('fo76theme') || 'green';
  document.querySelectorAll('.theme-dot').forEach(d => {
    d.classList.toggle('active-theme', d.dataset.theme === t);
  });
});

// ── Bulk selection ────────────────────────────────────────────────────────────
function toggleAll(cb) {
  document.querySelectorAll('.row-cb').forEach(c => c.checked = cb.checked);
  updateBulkBar();
}
function updateBulkBar() {
  const checked = document.querySelectorAll('.row-cb:checked');
  const bar = document.getElementById('bulkBar');
  const cnt = document.getElementById('bulkCount');
  if (bar) bar.style.display = checked.length ? 'flex' : 'none';
  if (cnt) cnt.textContent = checked.length + ' selected';
}
function clearBulk() {
  document.querySelectorAll('.row-cb, #selectAll').forEach(c => c.checked = false);
  updateBulkBar();
}
function confirmBulk() {
  const action = document.getElementById('bulkAction')?.value;
  const checked = document.querySelectorAll('.row-cb:checked');
  if (!action) { alert('Select an action first.'); return false; }
  if (!checked.length) { alert('Select at least one item.'); return false; }
  const msg = action === 'delete'
    ? `Delete ${checked.length} items? This cannot be undone.`
    : `Apply "${action}" to ${checked.length} items?`;
  if (!confirm(msg)) return false;
  const form = document.getElementById('bulkForm');
  if (!form) return false;
  form.querySelectorAll('input[name="ids"]').forEach(el => el.remove());
  const actionInput = form.querySelector('input[name="bulk_action"]');
  if (actionInput) actionInput.remove();
  checked.forEach(cb => {
    const inp = document.createElement('input');
    inp.type = 'hidden'; inp.name = 'ids'; inp.value = cb.dataset.id;
    form.appendChild(inp);
  });
  const actInp = document.createElement('input');
  actInp.type = 'hidden'; actInp.name = 'bulk_action'; actInp.value = action;
  form.appendChild(actInp);
  form.submit();
  return false;
}

// ── Draggable Quick Log FAB ────────────────────────────────────────────────
(function() {
  const fab = document.querySelector('.ql-fab');
  if (!fab) return;

  // Restore saved position
  const saved = localStorage.getItem('fabPos');
  if (saved) {
    try {
      const p = JSON.parse(saved);
      fab.style.right  = 'auto';
      fab.style.bottom = 'auto';
      fab.style.left   = p.left;
      fab.style.top    = p.top;
    } catch(e) {}
  }

  let startX, startY, startLeft, startTop, moved = false;

  function onDown(e) {
    const touch = e.touches ? e.touches[0] : e;
    const rect = fab.getBoundingClientRect();
    startX    = touch.clientX;
    startY    = touch.clientY;
    startLeft = rect.left;
    startTop  = rect.top;
    moved     = false;
    fab.style.transition = 'none';
    fab.style.right  = 'auto';
    fab.style.bottom = 'auto';
    fab.style.left   = startLeft + 'px';
    fab.style.top    = startTop  + 'px';
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup',   onUp);
    document.addEventListener('touchmove', onMove, { passive: false });
    document.addEventListener('touchend',  onUp);
  }

  function onMove(e) {
    const touch = e.touches ? e.touches[0] : e;
    const dx = touch.clientX - startX;
    const dy = touch.clientY - startY;
    if (Math.abs(dx) > 4 || Math.abs(dy) > 4) moved = true;
    if (!moved) return;
    if (e.cancelable) e.preventDefault();
    const newLeft = Math.max(0, Math.min(window.innerWidth  - fab.offsetWidth,  startLeft + dx));
    const newTop  = Math.max(0, Math.min(window.innerHeight - fab.offsetHeight, startTop  + dy));
    fab.style.left = newLeft + 'px';
    fab.style.top  = newTop  + 'px';
  }

  function onUp() {
    fab.style.transition = '';
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup',   onUp);
    document.removeEventListener('touchmove', onMove);
    document.removeEventListener('touchend',  onUp);
    if (moved) {
      localStorage.setItem('fabPos', JSON.stringify({ left: fab.style.left, top: fab.style.top }));
    }
  }

  fab.addEventListener('mousedown',  onDown);
  fab.addEventListener('touchstart', onDown, { passive: true });

  // Only open quick log if NOT a drag
  fab.addEventListener('click', function(e) {
    if (moved) { moved = false; return; }
    openQuickLog();
  });
  // Remove the inline onclick
  fab.removeAttribute('onclick');
})();
