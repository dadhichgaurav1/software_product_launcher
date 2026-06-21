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
})();
