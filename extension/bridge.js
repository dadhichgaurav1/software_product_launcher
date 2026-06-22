/*
 * bridge.js — content script injected into the Software Product Launcher web app
 * (http://localhost or http://127.0.0.1, any port).
 *
 * It is the link between the web page and the extension so the user never has to
 * configure the extension separately:
 *   - announces the extension's presence to the page (EXT_READY),
 *   - relays page -> background messages (SYNC_CONFIG, LAUNCH_FILL),
 *   - keeps the page/extension config in sync.
 *
 * Protocol (window.postMessage):
 *   page -> bridge : { source: 'spl-web', type, payload }
 *   bridge -> page : { source: 'spl-ext', type, ... }
 */
(function () {
  'use strict';

  if (!(typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.id)) return;

  var ORIGIN = location.origin;
  var VERSION = (chrome.runtime.getManifest && chrome.runtime.getManifest().version) || '1.0.0';

  function toPage(msg) {
    msg.source = 'spl-ext';
    try { window.postMessage(msg, ORIGIN); } catch (e) { /* ignore */ }
  }

  function announce() {
    toPage({ type: 'EXT_READY', version: VERSION });
    document.documentElement.setAttribute('data-spl-extension', VERSION);
  }

  // Relay messages coming from the page.
  window.addEventListener('message', function (event) {
    if (event.source !== window) return;
    var data = event.data;
    if (!data || data.source !== 'spl-web' || !data.type) return;

    if (data.type === 'PING_EXT') {
      announce();
      return;
    }

    // Forward actionable messages to the background worker.
    if (data.type === 'SYNC_CONFIG' || data.type === 'LAUNCH_FILL') {
      var payload = data.payload || {};
      // Default the backend to this page's origin if not provided.
      if (!payload.backend) payload.backend = ORIGIN;
      try {
        chrome.runtime.sendMessage({ type: data.type, payload: payload }, function (resp) {
          var err = chrome.runtime.lastError;
          toPage({
            type: data.type + '_ACK',
            ok: !err && !!(resp && resp.ok !== false),
            error: err ? err.message : (resp && resp.error) || null,
            resp: resp || null,
            requestId: data.requestId || null
          });
        });
      } catch (e) {
        toPage({ type: data.type + '_ACK', ok: false, error: String(e), requestId: data.requestId || null });
      }
    }
  });

  // Announce on load (covers "page loaded before the extension" too).
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', announce);
  } else {
    announce();
  }
  // A short follow-up in case the page's listener wasn't ready yet.
  setTimeout(announce, 400);
})();
