(function () {
  // Auto-dismiss flash banners.
  document.querySelectorAll('[data-autodismiss]').forEach(function (el) {
    var ms = parseInt(el.getAttribute('data-autodismiss'), 10) || 4500;
    setTimeout(function () {
      el.style.transition = 'opacity 240ms ease';
      el.style.opacity = '0';
      setTimeout(function () { el.remove(); }, 280);
    }, ms);
  });

  // Copy-to-clipboard buttons. Targets are nodes with [data-copy].
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('[data-copy]');
    if (!btn) return;
    var text = btn.getAttribute('data-copy');
    if (!text) return;
    var done = function () {
      var prev = btn.textContent;
      btn.classList.add('copied');
      btn.textContent = 'copied';
      setTimeout(function () {
        btn.classList.remove('copied');
        btn.textContent = prev;
      }, 1100);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done).catch(function () {});
    } else {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy'); done(); } catch (_) {}
      document.body.removeChild(ta);
    }
  });

  // Scan button: optimistic feedback so manual scans feel immediate.
  document.querySelectorAll('form[data-scan-form] button').forEach(function (btn) {
    btn.form.addEventListener('submit', function () {
      btn.disabled = true;
      btn.dataset.prev = btn.textContent;
      btn.textContent = 'Scanning…';
    });
  });
})();
