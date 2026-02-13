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
