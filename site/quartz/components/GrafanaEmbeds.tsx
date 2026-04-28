import { QuartzComponentConstructor } from "./types"

// GrafanaEmbeds — progressive-enhancement upgrader for placeholder
// <div class="grafana-embed"> nodes emitted by the GrafanaDefer
// transformer. iOS Safari OOM-crashes when too many live Grafana
// React contexts allocate at once (the homepage has 8 panels), so on
// iOS we render a static PNG from Grafana's `/render/d-solo/...`
// endpoint and offer an "Open live panel" link. Desktop and Android
// get the live iframe.
//
// The component itself emits no DOM (returns null) — the render is
// done client-side by the afterDOMLoaded script below, which scans
// for `.grafana-embed` placeholder divs and upgrades them in place.
// The placeholder div carries data-iframe-src, data-image-src,
// data-height, data-title.
//
// Lifecycle: re-runs on every Quartz `nav` event so SPA navigations
// re-bind. Timers and IntersectionObserver are tracked by
// window.addCleanup so they don't leak across navigations.

export default (() => {
  function GrafanaEmbeds() {
    return null
  }

  GrafanaEmbeds.css = `
.grafana-embed {
  width: 100%;
  margin: 0.5rem 0;
  border-radius: 6px;
  overflow: hidden;
  background: var(--lightgray);
  border: 1px solid var(--lightgray);
  position: relative;
}
.grafana-embed__frame,
.grafana-embed__img {
  width: 100%;
  display: block;
  border: 0;
}
.grafana-embed__placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  color: var(--gray);
  font-size: 0.85rem;
  min-height: 60px;
}
.grafana-embed__actions {
  padding: 0.4rem 0.6rem;
  font-size: 0.8rem;
  color: var(--gray);
  border-top: 1px solid var(--lightgray);
  background: var(--light);
}
.grafana-embed__actions a {
  color: var(--secondary);
  text-decoration: underline;
}
`

  GrafanaEmbeds.afterDOMLoaded = `
(function () {
  function isIOS() {
    if (typeof navigator === 'undefined') return false;
    if (/iPad|iPhone|iPod/.test(navigator.userAgent)) return true;
    if (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1) return true;
    return false;
  }

  function addCacheBust(url) {
    try {
      var u = new URL(url, window.location.href);
      u.searchParams.set('_qts', String(Date.now()));
      return u.toString();
    } catch (_) {
      return url + (url.indexOf('?') >= 0 ? '&' : '?') + '_qts=' + Date.now();
    }
  }

  function appendActions(el, liveSrc) {
    if (!liveSrc) return;
    var actions = document.createElement('div');
    actions.className = 'grafana-embed__actions';
    var a = document.createElement('a');
    a.href = liveSrc;
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    a.textContent = 'Open live Grafana panel ↗';
    actions.appendChild(a);
    el.appendChild(actions);
  }

  function setup() {
    var embeds = Array.from(document.querySelectorAll('.grafana-embed[data-iframe-src], .grafana-embed[data-image-src]'));
    if (!embeds.length) return;

    var ios = isIOS();
    var loaded = new WeakSet();
    var timers = [];
    var observer = null;

    // Client-side concurrency cap on PNG fetches. The grafana-image-
    // renderer + nginx cache can comfortably keep ~2 renders in
    // flight at once; bursting all 8 panels at once during initial
    // page load saturates the host and causes 20s+ per-image times.
    // Queue surplus requests; pop on completion.
    var IMG_MAX_INFLIGHT = 2;
    var imgInflight = 0;
    var imgQueue = [];

    function dequeueImg() {
      while (imgInflight < IMG_MAX_INFLIGHT && imgQueue.length) {
        var fn = imgQueue.shift();
        imgInflight++;
        fn();
      }
    }

    function loadImg(img, src) {
      var done = false;
      var settle = function () {
        if (done) return;
        done = true;
        imgInflight = Math.max(0, imgInflight - 1);
        dequeueImg();
      };
      img.addEventListener('load', settle, { once: true });
      img.addEventListener('error', settle, { once: true });
      // Belt-and-suspenders: if neither fires within 35s (renders
      // queue can occasionally take that long), release the slot
      // anyway so we don't deadlock the queue.
      window.setTimeout(settle, 35000);
      img.src = src;
    }

    function enqueueImg(img, src) {
      imgQueue.push(function () { loadImg(img, src); });
      dequeueImg();
    }

    function renderImage(el, imgSrc, liveSrc, title, height, refreshMs) {
      el.innerHTML = '';
      el.style.minHeight = height + 'px';

      var img = document.createElement('img');
      img.className = 'grafana-embed__img';
      img.alt = title;
      img.loading = 'lazy';
      img.decoding = 'async';
      img.height = height;

      // The renderer can still 429/timeout under load even with the
      // nginx cache and concurrency cap. Retry up to 3 times with
      // exponential backoff (3s, 6s, 12s) before falling back to a
      // placeholder with the "Open live panel" escape hatch. The
      // retries themselves go through enqueueImg so they respect
      // the IMG_MAX_INFLIGHT cap and don't dogpile.
      var attempts = 0;
      var maxAttempts = 3;
      img.addEventListener('error', function () {
        attempts++;
        if (attempts <= maxAttempts) {
          var backoff = 3000 * Math.pow(2, attempts - 1); // 3s, 6s, 12s
          window.setTimeout(function () {
            if (document.body.contains(el)) {
              enqueueImg(img, addCacheBust(imgSrc));
            }
          }, backoff);
        } else {
          var ph = document.createElement('div');
          ph.className = 'grafana-embed__placeholder';
          ph.style.height = height + 'px';
          ph.textContent = 'Image render unavailable — tap below to open live panel.';
          if (img.parentNode) img.parentNode.replaceChild(ph, img);
        }
      });
      el.appendChild(img);
      enqueueImg(img, addCacheBust(imgSrc));

      appendActions(el, liveSrc);

      if (refreshMs > 0) {
        var t = window.setInterval(function () {
          if (document.body.contains(el)) {
            enqueueImg(img, addCacheBust(imgSrc));
          }
        }, refreshMs);
        timers.push(t);
      }
    }

    function renderIframe(el, iframeSrc, liveSrc, title, height) {
      el.innerHTML = '';
      el.style.minHeight = height + 'px';

      var f = document.createElement('iframe');
      f.className = 'grafana-embed__frame';
      f.title = title;
      f.src = iframeSrc;
      f.height = String(height);
      f.frameBorder = '0';
      f.loading = 'lazy';
      f.referrerPolicy = 'no-referrer-when-downgrade';
      el.appendChild(f);

      appendActions(el, liveSrc);
    }

    function load(el) {
      if (loaded.has(el)) return;
      loaded.add(el);

      var iframeSrc = el.getAttribute('data-iframe-src') || '';
      var imageSrc = el.getAttribute('data-image-src') || '';
      var liveSrc = el.getAttribute('data-live-src') || iframeSrc;
      var title = el.getAttribute('data-title') || 'Grafana panel';
      var height = parseInt(el.getAttribute('data-height') || '300', 10);
      var refreshMs = parseInt(el.getAttribute('data-refresh-ms') || '60000', 10);

      if (!iframeSrc && !imageSrc) {
        el.innerHTML = '<div class="grafana-embed__placeholder">Missing Grafana source.</div>';
        return;
      }

      if (ios && imageSrc) {
        renderImage(el, imageSrc, liveSrc, title, height, refreshMs);
      } else if (iframeSrc) {
        renderIframe(el, iframeSrc, liveSrc, title, height);
      } else {
        renderImage(el, imageSrc, liveSrc, title, height, refreshMs);
      }
    }

    // Pre-fill placeholders with a "Loading…" state so layout is
    // stable before each panel is upgraded.
    embeds.forEach(function (el) {
      var height = parseInt(el.getAttribute('data-height') || '300', 10);
      el.style.minHeight = height + 'px';
      el.innerHTML = '<div class="grafana-embed__placeholder" style="height:' + height + 'px">Loading…</div>';
    });

    if ('IntersectionObserver' in window) {
      observer = new IntersectionObserver(function (entries) {
        for (var i = 0; i < entries.length; i++) {
          if (entries[i].isIntersecting) {
            load(entries[i].target);
            observer.unobserve(entries[i].target);
          }
        }
      }, { rootMargin: '300px 0px', threshold: 0 });
      embeds.forEach(function (el) { observer.observe(el); });
    } else {
      embeds.forEach(load);
    }

    if (window.addCleanup) {
      window.addCleanup(function () {
        if (observer) observer.disconnect();
        for (var i = 0; i < timers.length; i++) window.clearInterval(timers[i]);
      });
    }
  }

  document.addEventListener('nav', setup);
  if (document.readyState !== 'loading') setup();
})();
`

  return GrafanaEmbeds
}) satisfies QuartzComponentConstructor
