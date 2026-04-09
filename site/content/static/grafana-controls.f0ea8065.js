/**
 * Verdify Grafana Panel Controller v4
 *
 * Scoped: each .grafana-controls only affects iframes in the same section.
 * Supports forecast ranges (from=past, to=future).
 *
 *   .grafana-controls                    → full range picker
 *   .grafana-controls[data-mode="none"]  → hidden, iframes keep their native range
 *   .grafana-controls[data-ranges]       → custom range set, e.g. "24h,forecast,7d,30d"
 *   .grafana-controls[data-scope="page"] → affects ALL iframes on page (legacy behavior)
 */
(function() {
  'use strict';

  var ALL_RANGES = [
    { label: '24h',      from: 'now-24h',  to: 'now' },
    { label: 'Forecast', from: 'now-72h',  to: 'now+72h' },
    { label: '7d',       from: 'now-7d',   to: 'now' },
    { label: '30d',      from: 'now-30d',  to: 'now' },
    { label: '60d',      from: 'now-60d',  to: 'now' },
    { label: '90d',      from: 'now-90d',  to: 'now' },
    { label: '6mo',      from: 'now-180d', to: 'now' },
    { label: '1y',       from: 'now-1y',   to: 'now' },
  ];

  var DEFAULT_LABEL = 'Forecast';

  function findSiblingFrames(controlEl) {
    // Scoped: find iframes in the next .pg divs until the next h2 or grafana-controls
    var frames = [];
    var el = controlEl.nextElementSibling;
    while (el) {
      if (el.classList && (el.classList.contains('grafana-controls') || el.tagName === 'H2')) break;
      el.querySelectorAll('iframe[src*="verdify.ai"]').forEach(function(f) { frames.push(f); });
      el = el.nextElementSibling;
    }
    return frames;
  }

  function updateFrames(frames, from, to) {
    frames.forEach(function(f) {
      if (f.closest('[data-mode="none"]') || f.closest('.gc-locked')) return;
      try {
        var u = new URL(f.src);
        u.searchParams.set('from', from);
        u.searchParams.set('to', to);
        if (f.src !== u.toString()) f.src = u.toString();
      } catch(e) {}
    });
  }

  function parseRanges(rangeStr) {
    if (!rangeStr) return ALL_RANGES;
    var labels = rangeStr.split(',').map(function(s) { return s.trim(); });
    return ALL_RANGES.filter(function(r) { return labels.indexOf(r.label) !== -1; });
  }

  function init() {
    document.querySelectorAll('.grafana-controls').forEach(function(c) {
      if (c.childNodes.length > 0) return;

      var mode = c.getAttribute('data-mode');
      if (mode === 'none') { c.style.display = 'none'; return; }

      var pageScope = c.getAttribute('data-scope') === 'page';
      var ranges = parseRanges(c.getAttribute('data-ranges'));
      var defaultLabel = c.getAttribute('data-default') || DEFAULT_LABEL;
      var activeRange = ranges.find(function(r) { return r.label === defaultLabel; }) || ranges[0];

      // Find which iframes this control manages
      var frames = pageScope
        ? Array.from(document.querySelectorAll('iframe[src*="verdify.ai"]'))
        : findSiblingFrames(c);

      ranges.forEach(function(r) {
        var b = document.createElement('button');
        b.textContent = r.label;
        b.className = 'gc-btn' + (r.label === activeRange.label ? ' gc-active' : '');
        b.onclick = function() {
          c.querySelectorAll('.gc-btn').forEach(function(x) { x.classList.remove('gc-active'); });
          b.classList.add('gc-active');
          updateFrames(frames, r.from, r.to);
        };
        c.appendChild(b);
      });
    });
  }

  init();
  document.addEventListener('DOMContentLoaded', init);
  document.addEventListener('nav', function() { setTimeout(init, 50); });
  window.addEventListener('popstate', function() { setTimeout(init, 50); });

  new MutationObserver(function() {
    if (document.querySelector('.grafana-controls:empty')) init();
  }).observe(document.documentElement, { childList: true, subtree: true });
})();
