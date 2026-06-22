/*
 * content.js — injected into every https page (after fill_engine.js).
 *
 * It is the page-side message handler. The popup / background talk to it via
 * chrome.runtime / chrome.tabs.sendMessage. All real DOM work is delegated to
 * the FillEngine global that fill_engine.js installs.
 */
(function () {
  'use strict';

  // fill_engine.js runs first in the content_scripts array, so this is set.
  var FE = (typeof globalThis !== 'undefined' && globalThis.FillEngine) ||
    (typeof window !== 'undefined' && window.FillEngine);

  if (!FE) {
    // Defensive: never throw inside a content script.
    console.warn('[ProductLauncher] FillEngine not available on this page.');
  }

  function handleMessage(msg, sender, sendResponse) {
    if (!msg || !msg.type) return false;

    try {
      switch (msg.type) {
        case 'PING': {
          sendResponse({ ok: true, url: location.href, title: document.title });
          return false;
        }

        case 'FILL': {
          if (!FE) {
            sendResponse({ ok: false, error: 'FillEngine unavailable' });
            return false;
          }
          var plan = msg.fillPlan || [];
          var summary = FE.applyPlan(document, plan);
          // Visual feedback: green for actioned fields, orange for manual ones.
          for (var i = 0; i < summary.results.length; i++) {
            var r = summary.results[i];
            if (r && r.element) {
              FE.highlight(r.element, r.status !== 'manual_required' && r.status !== 'not_found');
            }
          }
          // Bring the first actioned field into view (best effort).
          var first = summary.results.find
            ? summary.results.find(function (r) { return r.element; })
            : null;
          if (first && first.element && typeof first.element.scrollIntoView === 'function') {
            try { first.element.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch (e) { /* ignore */ }
          }
          // Strip DOM nodes before sending back across the message boundary.
          sendResponse({ ok: true, summary: stripElements(summary) });
          return false;
        }

        case 'DETECT_AUTH': {
          if (!FE) {
            sendResponse({ ok: false, found: false });
            return false;
          }
          var btn = FE.detectAuthButton(document);
          sendResponse({
            ok: true,
            found: !!btn,
            text: btn ? FE.elementText(btn) : '',
            url: location.href
          });
          return false;
        }

        case 'CLICK_AUTH': {
          if (!FE) {
            sendResponse({ ok: false, clicked: false });
            return false;
          }
          var target = FE.detectAuthButton(document);
          if (target) {
            FE.highlight(target, true);
            try {
              if (typeof target.scrollIntoView === 'function') {
                target.scrollIntoView({ behavior: 'smooth', block: 'center' });
              }
              if (typeof target.click === 'function') target.click();
            } catch (e) { /* ignore */ }
            sendResponse({ ok: true, clicked: true, text: FE.elementText(target) });
          } else {
            sendResponse({ ok: true, clicked: false, text: '' });
          }
          return false;
        }

        default:
          return false;
      }
    } catch (err) {
      try { sendResponse({ ok: false, error: String(err && err.message ? err.message : err) }); } catch (e) { /* ignore */ }
      return false;
    }
  }

  /** Remove live DOM nodes from a summary so it is structured-clone safe. */
  function stripElements(summary) {
    var out = { filled: summary.filled, not_found: summary.not_found, manual_required: summary.manual_required, results: [] };
    for (var i = 0; i < summary.results.length; i++) {
      var r = summary.results[i];
      out.results.push({
        question_id: r.question_id,
        action: r.action,
        status: r.status,
        selector: r.selector || null
      });
    }
    return out;
  }

  if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.onMessage) {
    chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {
      var keepOpen = handleMessage(msg, sender, sendResponse);
      // Return true to keep the channel open for async responses where needed.
      return keepOpen === true;
    });
  }

  // ---------------------------------------------------------------------------
  // In-page Fill panel — shown when the web page has armed a task for this site.
  // Lets the user sign in and fill without ever opening the extension popup.
  // ---------------------------------------------------------------------------
  function bg(message) {
    return new Promise(function (resolve) {
      try {
        chrome.runtime.sendMessage(message, function (resp) {
          resolve(chrome.runtime.lastError ? null : resp);
        });
      } catch (e) { resolve(null); }
    });
  }

  function injectStyles() {
    if (document.getElementById('spl-panel-style')) return;
    var css =
      '#spl-panel{font:13px/1.4 -apple-system,Segoe UI,Roboto,sans-serif;color:#e8ecf6;width:268px}' +
      '#spl-panel .spl-hd{display:flex;align-items:center;gap:6px;font-weight:700;margin-bottom:8px}' +
      '#spl-panel .spl-x{margin-left:auto;cursor:pointer;background:transparent;border:0;color:#97a0bd;font-size:18px;line-height:1}' +
      '#spl-panel .spl-site{color:#c7cee3;margin-bottom:10px}' +
      '#spl-panel .spl-btns{display:flex;gap:8px}' +
      '#spl-panel .spl-b{flex:1;cursor:pointer;border-radius:8px;border:1px solid #2a3354;background:#1f2740;color:#e8ecf6;padding:8px;font-weight:600;font-size:12px}' +
      '#spl-panel .spl-b.spl-fill{background:#6c8cff;border-color:#6c8cff;color:#fff}' +
      '#spl-panel .spl-b:disabled{opacity:.6;cursor:progress}' +
      '#spl-panel .spl-status{margin-top:9px;font-size:12px;color:#97a0bd;min-height:16px}' +
      '#spl-panel .spl-status .ok{color:#46d3a0}#spl-panel .spl-status .warn{color:#f4a64a}';
    var style = document.createElement('style');
    style.id = 'spl-panel-style';
    style.textContent = css;
    (document.head || document.documentElement).appendChild(style);
  }

  function showPanel(task) {
    if (document.getElementById('spl-panel') || !document.body) return;
    injectStyles();
    var panel = document.createElement('div');
    panel.id = 'spl-panel';
    // Critical layout inline so it survives even if the page blocks our <style>.
    panel.style.cssText =
      'position:fixed;bottom:18px;right:18px;z-index:2147483647;background:#171c2e;' +
      'border:1px solid #2a3354;border-radius:12px;padding:14px;box-shadow:0 8px 30px rgba(0,0,0,.45)';
    panel.innerHTML =
      '<div class="spl-hd"><span>🚀</span> Product Launcher <button class="spl-x" title="Dismiss">×</button></div>' +
      '<div class="spl-site">Ready to fill <b></b></div>' +
      '<div class="spl-btns">' +
      '<button class="spl-b spl-signin">Help me sign in</button>' +
      '<button class="spl-b spl-fill">Fill this page</button></div>' +
      '<div class="spl-status"></div>';
    panel.querySelector('.spl-site b').textContent = task.site_name || task.site_id;
    document.body.appendChild(panel);

    var statusEl = panel.querySelector('.spl-status');
    var fillBtn = panel.querySelector('.spl-fill');
    var setStatus = function (html) { statusEl.innerHTML = html; };

    panel.querySelector('.spl-x').addEventListener('click', function () {
      panel.remove();
      bg({ type: 'CLEAR_TASK', host: location.hostname });
    });

    panel.querySelector('.spl-signin').addEventListener('click', function () {
      if (!FE) { setStatus('<span class="warn">Sign-in helper unavailable.</span>'); return; }
      var btn = FE.detectAuthButton(document);
      if (btn) {
        FE.highlight(btn, true);
        try { btn.scrollIntoView({ behavior: 'smooth', block: 'center' }); btn.click(); } catch (e) { /* ignore */ }
        setStatus('Opening sign-in… complete it in the page, then click <b>Fill this page</b>.');
      } else {
        setStatus('<span class="warn">No sign-in button found here. Sign in manually, then fill.</span>');
      }
    });

    fillBtn.addEventListener('click', function () {
      if (!FE) { setStatus('<span class="warn">Fill engine unavailable.</span>'); return; }
      fillBtn.disabled = true;
      setStatus('Fetching your draft…');
      bg({ type: 'FETCH_ANSWERS', backend: task.backend, site_id: task.site_id, product_url: task.product_url })
        .then(function (resp) {
          fillBtn.disabled = false;
          if (!resp || resp.ok === false || !resp.data || !resp.data.fill_plan) {
            setStatus('<span class="warn">Could not load the draft. Is the backend running?</span>');
            return;
          }
          var summary = FE.applyPlan(document, resp.data.fill_plan);
          for (var i = 0; i < summary.results.length; i++) {
            var r = summary.results[i];
            if (r && r.element) FE.highlight(r.element, r.status !== 'manual_required' && r.status !== 'not_found');
          }
          var first = summary.results.find ? summary.results.find(function (r) { return r.element; }) : null;
          if (first && first.element && first.element.scrollIntoView) {
            try { first.element.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch (e) { /* ignore */ }
          }
          setStatus('<span class="ok">Filled ' + summary.filled + '</span> · ' +
            summary.manual_required + ' manual · ' + summary.not_found + ' not found. Review &amp; submit.');
        });
    });
  }

  function initPanel() {
    if (window.top !== window) return; // only in the top frame
    bg({ type: 'GET_TASK', host: location.hostname }).then(function (resp) {
      if (resp && resp.ok && resp.task) showPanel(resp.task);
    });
  }

  if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.id) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', initPanel);
    } else {
      initPanel();
    }
  }
})();
