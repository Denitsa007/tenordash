// Close slide-out panels when clicking overlay background
document.addEventListener('click', function(e) {
  if (e.target.classList.contains('panel-overlay')) {
    e.target.classList.remove('show');
  }
});

// Close panels on Escape key
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') {
    document.querySelectorAll('.panel-overlay.show').forEach(function(panel) {
      panel.classList.remove('show');
    });
  }
});

// ── Settings Modal ──

async function openSettingsModal() {
  const msgEl = document.getElementById('settings-msg');
  msgEl.style.display = 'none';
  document.getElementById('settings-submit-btn').disabled = false;

  try {
    const res = await fetch('/api/settings');
    const settings = await res.json();
    document.getElementById('settings-display-unit').value = settings.display_unit || 'millions';
    document.getElementById('settings-export-path').value = settings.export_path || '';
  } catch (e) {
    // Use defaults if fetch fails
  }

  document.getElementById('settings-modal').classList.add('show');
}

function closeSettingsModal() {
  document.getElementById('settings-modal').classList.remove('show');
}

async function saveSettings(e) {
  e.preventDefault();
  const msgEl = document.getElementById('settings-msg');
  const btn = document.getElementById('settings-submit-btn');
  btn.disabled = true;
  msgEl.style.display = 'none';

  const LABELS = { display_unit: 'Display Unit', export_path: 'Export Path' };
  const settings = [
    { key: 'display_unit', value: document.getElementById('settings-display-unit').value },
    { key: 'export_path', value: document.getElementById('settings-export-path').value.trim() },
  ];

  let saved = [];
  for (const s of settings) {
    const res = await fetch('/api/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(s),
    });
    const data = await res.json();
    if (!data.ok) {
      let msg = (LABELS[s.key] || s.key) + ': ' + (data.error || 'Failed to save');
      if (saved.length) msg += ' (other settings were saved)';
      msgEl.textContent = msg;
      msgEl.className = 'currency-msg error';
      msgEl.style.display = 'block';
      btn.disabled = false;
      return;
    }
    saved.push(s.key);
  }

  location.reload();
}

// Shared locale-aware number parsing/formatting helpers for forms.
window.TDNumber = (function() {
  const decSep = (1.1).toLocaleString().charAt(1);
  const thouSep = (1000).toLocaleString().length > 4 ? (1000).toLocaleString().charAt(1) : '';
  const stripGroupRe = thouSep ? new RegExp('\\' + thouSep, 'g') : null;

  function parseLocaleNumber(str) {
    let s = (str || '');
    if (stripGroupRe) s = s.replace(stripGroupRe, '');
    if (decSep !== '.') s = s.replace(decSep, '.');
    return parseFloat(s) || 0;
  }

  function formatAmountInput(el, allowDecimals) {
    const pos = el.selectionStart;
    const oldLen = el.value.length;
    let raw = el.value.replace(new RegExp('[^0-9' + (decSep === '.' ? '\\.' : '\\' + decSep) + ']', 'g'), '');
    if (decSep !== '.') raw = raw.replace(decSep, '.');
    if (!allowDecimals) raw = raw.replace(/\./g, '');
    if (!raw) { el.value = ''; return; }
    const parts = raw.split('.');
    parts[0] = parseInt(parts[0], 10).toLocaleString();
    el.value = allowDecimals && parts.length > 1 ? parts[0] + decSep + parts[1].slice(0, 2) : parts[0];
    const newLen = el.value.length;
    const newPos = Math.max(0, pos + (newLen - oldLen));
    el.setSelectionRange(newPos, newPos);
  }

  function formatIntegerInput(el) {
    const pos = el.selectionStart;
    const oldLen = el.value.length;
    let raw = el.value.replace(/[^0-9]/g, '');
    if (!raw) { el.value = ''; return; }
    el.value = parseInt(raw, 10).toLocaleString();
    const newLen = el.value.length;
    const newPos = Math.max(0, pos + (newLen - oldLen));
    el.setSelectionRange(newPos, newPos);
  }

  return {
    parseLocaleNumber,
    formatAmountInput,
    formatIntegerInput,
  };
})();
