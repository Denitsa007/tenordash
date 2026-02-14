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
  var msgEl = document.getElementById('settings-msg');
  msgEl.style.display = 'none';
  document.getElementById('folder-browser').style.display = 'none';
  document.getElementById('settings-submit-btn').disabled = false;

  // Load current settings
  var res = await fetch('/api/settings');
  var data = await res.json();
  document.getElementById('settings-export-path').value = data.export_path || '';

  document.getElementById('settings-modal').classList.add('show');
}

function closeSettingsModal() {
  document.getElementById('settings-modal').classList.remove('show');
}

async function saveSettings(e) {
  e.preventDefault();
  var msgEl = document.getElementById('settings-msg');
  var btn = document.getElementById('settings-submit-btn');
  btn.disabled = true;
  msgEl.style.display = 'none';

  var exportPath = document.getElementById('settings-export-path').value;
  var res = await fetch('/api/settings', {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({export_path: exportPath})
  });
  var data = await res.json();
  if (data.ok) {
    msgEl.textContent = 'Settings saved.';
    msgEl.className = 'settings-msg success';
    msgEl.style.display = 'block';
    setTimeout(function() { closeSettingsModal(); }, 800);
  } else {
    msgEl.textContent = data.error || 'Failed to save settings';
    msgEl.className = 'settings-msg error';
    msgEl.style.display = 'block';
    btn.disabled = false;
  }
}

// ── Folder Browser ──

var currentBrowsePath = '';

async function openFolderBrowser() {
  var current = document.getElementById('settings-export-path').value;
  var startPath = current || '~';
  await navigateToFolder(startPath);
  document.getElementById('folder-browser').style.display = 'block';
}

async function navigateToFolder(path) {
  var res = await fetch('/api/browse-dirs?path=' + encodeURIComponent(path));
  var data = await res.json();
  if (data.error) return;

  currentBrowsePath = data.path;

  // Render breadcrumb using data-path attributes (no inline handlers)
  var bcEl = document.getElementById('folder-breadcrumb');
  bcEl.innerHTML = '';
  var rootLink = document.createElement('a');
  rootLink.textContent = '/';
  rootLink.dataset.path = '/';
  bcEl.appendChild(rootLink);

  var parts = data.path.split('/').filter(Boolean);
  var cumulative = '';
  parts.forEach(function(p, i) {
    cumulative += '/' + p;
    if (i === parts.length - 1) {
      var span = document.createElement('span');
      span.textContent = ' ' + p;
      bcEl.appendChild(span);
    } else {
      var sep = document.createElement('span');
      sep.textContent = ' ';
      bcEl.appendChild(sep);
      var link = document.createElement('a');
      link.textContent = p;
      link.dataset.path = cumulative;
      bcEl.appendChild(link);
      var slash = document.createElement('span');
      slash.textContent = ' /';
      bcEl.appendChild(slash);
    }
  });

  // Render directory list using data-path attributes
  var listEl = document.getElementById('folder-list');
  listEl.innerHTML = '';
  if (data.dirs.length === 0) {
    var empty = document.createElement('div');
    empty.className = 'folder-item';
    empty.style.color = 'var(--text-light)';
    empty.textContent = 'No subdirectories';
    listEl.appendChild(empty);
  } else {
    data.dirs.forEach(function(d) {
      var fullPath = data.path === '/' ? '/' + d : data.path + '/' + d;
      var item = document.createElement('div');
      item.className = 'folder-item';
      item.dataset.path = fullPath;
      item.innerHTML = '&#128193; ';
      item.appendChild(document.createTextNode(d));
      listEl.appendChild(item);
    });
  }

  // Update select button state
  var selectBtn = document.getElementById('folder-select-btn');
  var statusEl = document.getElementById('folder-status');
  if (data.writable) {
    selectBtn.disabled = false;
    statusEl.textContent = '';
  } else {
    selectBtn.disabled = true;
    statusEl.textContent = 'This directory is not writable';
  }
}

function selectFolder() {
  document.getElementById('settings-export-path').value = currentBrowsePath;
  document.getElementById('folder-browser').style.display = 'none';
}

// Event delegation for folder browser clicks (breadcrumb + directory list)
document.addEventListener('click', function(e) {
  var target = e.target.closest('[data-path]');
  if (!target) return;
  var container = target.closest('#folder-breadcrumb, #folder-list');
  if (container) navigateToFolder(target.dataset.path);
});

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
