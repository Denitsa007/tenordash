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
