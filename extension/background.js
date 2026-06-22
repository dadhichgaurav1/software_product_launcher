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

/** Hostname without a leading www., for matching tabs to launch sites. */
function hostOf(u) {
  try { return new URL(u).hostname.replace(/^www\./, ''); }
  catch (e) { return String(u || '').replace(/^www\./, ''); }
}

// -- pending fill tasks (keyed by host) in session storage ------------------
// A task is armed when the web page triggers a launch; the launch-site content
// script reads it to show its in-page "Fill" panel — no popup needed.
var TASK_TTL_MS = 30 * 60 * 1000;

function taskStore() {
  return (chrome.storage && chrome.storage.session) || chrome.storage.local;
}

function getTasks(cb) {
  taskStore().get({ tasks: {} }, function (r) { cb(r.tasks || {}); });
}

function armTask(payload, cb) {
  getTasks(function (tasks) {
    var host = hostOf(payload.site_url || payload.site_id);
    tasks[host] = {
      backend: normalizeBase(payload.backend),
      product_url: payload.product_url || '',
      site_id: payload.site_id || '',
      site_name: payload.site_name || payload.site_id || '',
      site_url: payload.site_url || '',
      ts: Date.now()
    };
    taskStore().set({ tasks: tasks }, function () { cb(host); });
  });
}

function getTaskForHost(host, cb) {
  var key = hostOf(host);
  getTasks(function (tasks) {
    var t = tasks[key];
    if (t && Date.now() - t.ts > TASK_TTL_MS) t = null;
    cb(t || null);
  });
}

function clearTask(host, cb) {
  getTasks(function (tasks) {
    delete tasks[hostOf(host)];
    taskStore().set({ tasks: tasks }, function () { cb && cb(); });
  });
}

// -- unified message handler (popup, bridge, content scripts) ----------------
chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {
  if (!msg || !msg.type) return false;

  switch (msg.type) {
    case 'BACKEND_FETCH':
      backendFetch(msg.base || DEFAULTS.backendUrl, msg.path || '/api/health', msg.options || {}).then(sendResponse);
      return true;

    case 'SYNC_CONFIG': {
      // Keep the popup/extension config in sync with the web page's session.
      var p = msg.payload || {};
      var cfg = {};
      if (p.backend) cfg.backendUrl = normalizeBase(p.backend);
      if (p.product_url !== undefined) cfg.productUrl = p.product_url;
      chrome.storage.local.set(cfg, function () { sendResponse({ ok: true }); });
      return true;
    }

    case 'LAUNCH_FILL': {
      // Arm a task for the site, store config, and open the launch-site tab.
      var pl = msg.payload || {};
      chrome.storage.local.set({
        backendUrl: normalizeBase(pl.backend),
        productUrl: pl.product_url || ''
      }, function () {
        armTask(pl, function (host) {
          if (pl.site_url) {
            chrome.tabs.create({ url: pl.site_url, active: true }, function (tab) {
              sendResponse({ ok: true, host: host, tabId: tab && tab.id });
            });
          } else {
            sendResponse({ ok: true, host: host });
          }
        });
      });
      return true;
    }

    case 'GET_TASK':
      getTaskForHost(msg.host || (sender.tab && sender.tab.url) || '', function (task) {
        sendResponse({ ok: true, task: task });
      });
      return true;

    case 'FETCH_ANSWERS': {
      var base = msg.backend || DEFAULTS.backendUrl;
      var path = '/api/answers/' + encodeURIComponent(msg.site_id) +
        '?url=' + encodeURIComponent(msg.product_url || '');
      backendFetch(base, path, {}).then(sendResponse);
      return true;
    }

    case 'CLEAR_TASK':
      clearTask(msg.host || '', function () { sendResponse({ ok: true }); });
      return true;

    default:
      return false;
  }
});

// Expose for any other module that imports the worker (harmless in browser).
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    normalizeBase: normalizeBase, backendFetch: backendFetch, DEFAULTS: DEFAULTS,
    hostOf: hostOf, armTask: armTask, getTaskForHost: getTaskForHost, clearTask: clearTask
  };
}
