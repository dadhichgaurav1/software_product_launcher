/*
 * background.js — MV3 service worker.
 *
 * Responsibilities:
 *   - Seed default configuration into chrome.storage.local on install.
 *   - Expose a tiny backend-fetch helper over chrome.runtime messaging so the
 *     popup (or future surfaces) can call the local backend without re-deriving
 *     the base URL each time. The popup mostly fetches directly; this is a
 *     convenience / fallback.
 */
'use strict';

var DEFAULTS = {
  backendUrl: 'http://127.0.0.1:8000',
  productUrl: '',
  selectedSiteIds: []
};

// -- install: seed defaults without clobbering anything the user already set --
chrome.runtime.onInstalled.addListener(function () {
  chrome.storage.local.get(DEFAULTS, function (current) {
    var toSet = {};
    Object.keys(DEFAULTS).forEach(function (key) {
      if (current[key] === undefined || current[key] === null) {
        toSet[key] = DEFAULTS[key];
      }
    });
    // Ensure backendUrl always has a sane value even if stored empty.
    if (!current.backendUrl) toSet.backendUrl = DEFAULTS.backendUrl;
    if (Object.keys(toSet).length) chrome.storage.local.set(toSet);
  });
});

/** Normalise a base URL: trim and strip any trailing slash. */
function normalizeBase(base) {
  base = (base || DEFAULTS.backendUrl).trim();
  return base.replace(/\/+$/, '');
}

/**
 * Generic backend fetch. Resolves to { ok, status, data } | { ok:false, error }.
 * Used by the message handler below.
 */
function backendFetch(base, path, options) {
  var url = normalizeBase(base) + path;
  var opts = options || {};
  return fetch(url, opts)
    .then(function (resp) {
      return resp.text().then(function (text) {
        var data = null;
        try { data = text ? JSON.parse(text) : null; } catch (e) { data = text; }
        return { ok: resp.ok, status: resp.status, data: data };
      });
    })
    .catch(function (err) {
      return { ok: false, status: 0, error: String(err && err.message ? err.message : err) };
    });
}

// -- message bridge for the popup / options ---------------------------------
chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {
  if (!msg || msg.type !== 'BACKEND_FETCH') return false;
  var base = msg.base || DEFAULTS.backendUrl;
  var path = msg.path || '/api/health';
  var options = msg.options || {};
  backendFetch(base, path, options).then(sendResponse);
  return true; // async response — keep the channel open
});

// Expose for any other module that imports the worker (harmless in browser).
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { normalizeBase: normalizeBase, backendFetch: backendFetch, DEFAULTS: DEFAULTS };
}
