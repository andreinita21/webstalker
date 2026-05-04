(function () {
  // ---- flash auto-dismiss --------------------------------------------------
  document.querySelectorAll('[data-autodismiss]').forEach(function (el) {
    var ms = parseInt(el.getAttribute('data-autodismiss'), 10) || 4500;
    setTimeout(function () {
      el.style.transition = 'opacity 240ms ease';
      el.style.opacity = '0';
      setTimeout(function () { el.remove(); }, 280);
    }, ms);
  });

  // ---- copy-to-clipboard ---------------------------------------------------
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

  // ---- optimistic scan-button feedback -------------------------------------
  document.querySelectorAll('form[data-scan-form]').forEach(function (form) {
    form.addEventListener('submit', function () {
      var btn = form.querySelector('button');
      if (!btn) return;
      btn.disabled = true;
      btn.dataset.prev = btn.textContent;
      btn.textContent = 'Scanning…';
    });
  });

  // ---- live activity stream (Server-Sent Events) ---------------------------
  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
  }

  function formatTime(iso) {
    try {
      var d = new Date(iso);
      var hh = String(d.getHours()).padStart(2, '0');
      var mm = String(d.getMinutes()).padStart(2, '0');
      var ss = String(d.getSeconds()).padStart(2, '0');
      return hh + ':' + mm + ':' + ss;
    } catch (_) { return ''; }
  }

  function renderEvent(stream, ev) {
    // Optional per-website filter on the stream container.
    var filter = stream.dataset.websiteFilter;
    if (filter && String(ev.website_id) !== filter) return;

    var empty = stream.querySelector('.activity-empty');
    if (empty) empty.remove();

    var row = document.createElement('div');
    var resultClass = ev.type === 'scan.start' ? 'start' : (ev.result || 'unknown');
    row.className = 'activity-row activity-' + resultClass;

    var icon = '?';
    var msg = escapeHtml(ev.website_name || '');
    if (ev.type === 'scan.start') {
      icon = '↻';
      msg = 'scanning <b>' + escapeHtml(ev.website_name) + '</b>'
        + ' <span class="muted">(' + escapeHtml(ev.trigger || 'manual') + ')</span>';
    } else {
      switch (ev.result) {
        case 'changed':
          icon = '+';
          msg = '<b>' + escapeHtml(ev.website_name) + '</b> changed → v' + (ev.version_number || '?');
          break;
        case 'unchanged':
          icon = '·';
          msg = '<b>' + escapeHtml(ev.website_name) + '</b> unchanged';
          break;
        case 'error':
          icon = '✗';
          msg = '<b>' + escapeHtml(ev.website_name) + '</b> error: '
            + '<span class="error-text">' + escapeHtml(ev.error_message || 'unknown') + '</span>';
          break;
        case 'skipped':
          icon = '~';
          msg = '<b>' + escapeHtml(ev.website_name) + '</b> skipped (already running)';
          break;
        default:
          icon = '?';
          msg = '<b>' + escapeHtml(ev.website_name) + '</b> done';
      }
      var meta = [];
      if (ev.http_status) meta.push('HTTP ' + ev.http_status);
      if (ev.duration_ms != null) meta.push(ev.duration_ms + 'ms');
      if (meta.length) msg += ' <span class="muted">' + meta.join(' · ') + '</span>';
    }

    row.innerHTML =
      '<span class="activity-time">' + formatTime(ev.ts) + '</span>'
      + '<span class="activity-icon">' + icon + '</span>'
      + '<span class="activity-msg" title="' + escapeHtml((ev.url || '') + ' ' + (ev.error_message || '')) + '">' + msg + '</span>';

    stream.prepend(row);
    while (stream.children.length > 80) stream.lastChild.remove();
  }

  function updateRowBadge(ev) {
    document.querySelectorAll('[data-website-id="' + ev.website_id + '"]').forEach(function (el) {
      var badge = el.querySelector('[data-status-badge]');
      if (!badge) return;
      var cls, label;
      if (ev.type === 'scan.start') {
        cls = 'badge badge-pending';
        label = 'Scanning';
      } else {
        switch (ev.result) {
          case 'changed':   cls = 'badge badge-changed'; label = 'Changed'; break;
          case 'unchanged': cls = 'badge badge-ok';      label = 'OK';      break;
          case 'error':     cls = 'badge badge-error';   label = 'Error';   break;
          case 'skipped':   return; // keep current
          default: return;
        }
      }
      badge.className = cls;
      badge.textContent = label;
    });
  }

  function setStatus(node, mode, text) {
    if (!node) return;
    node.classList.remove('live', 'error-state');
    if (mode === 'live') node.classList.add('live');
    if (mode === 'error') node.classList.add('error-state');
    node.textContent = text;
  }

  function startEventStream() {
    var stream = document.getElementById('activity-stream');
    if (!stream) return;
    var statusEl = document.getElementById('activity-status');
    setStatus(statusEl, '', 'connecting…');

    if (!window.EventSource) {
      setStatus(statusEl, 'error', 'live updates unavailable');
      return;
    }

    var src = new EventSource('/api/events');

    src.addEventListener('open', function () {
      setStatus(statusEl, 'live', 'live');
    });
    src.addEventListener('error', function () {
      // EventSource auto-reconnects; just reflect the state.
      setStatus(statusEl, 'error', 'reconnecting…');
    });
    function handle(e) {
      try {
        var ev = JSON.parse(e.data);
        renderEvent(stream, ev);
        updateRowBadge(ev);
      } catch (_) {}
    }
    src.addEventListener('scan.start', handle);
    src.addEventListener('scan.end', handle);

    // Stop the stream when the tab unloads to avoid hanging requests.
    window.addEventListener('beforeunload', function () { src.close(); });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startEventStream);
  } else {
    startEventStream();
  }
})();
