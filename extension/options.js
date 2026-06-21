/*
 * options.js — read & save Backend Base URL and default Product URL to
 * chrome.storage.local. Shared keys with popup.js / background.js.
 */
'use strict';

(function () {
  var DEFAULT_BACKEND = 'http://127.0.0.1:8000';
  var backendInput = document.getElementById('backend-url');
  var productInput = document.getElementById('product-url');
  var saveBtn = document.getElementById('save');
  var savedMsg = document.getElementById('saved');

  function normalize(base) {
    return (base || DEFAULT_BACKEND).trim().replace(/\/+$/, '');
  }

  function load() {
    chrome.storage.local.get(
      { backendUrl: DEFAULT_BACKEND, productUrl: '' },
      function (cfg) {
        backendInput.value = cfg.backendUrl || DEFAULT_BACKEND;
        productInput.value = cfg.productUrl || '';
      }
    );
  }

  function save() {
    var payload = {
      backendUrl: normalize(backendInput.value),
      productUrl: (productInput.value || '').trim()
    };
    chrome.storage.local.set(payload, function () {
      backendInput.value = payload.backendUrl;
      savedMsg.style.display = 'inline';
      setTimeout(function () { savedMsg.style.display = 'none'; }, 1800);
    });
  }

  document.addEventListener('DOMContentLoaded', load);
  saveBtn.addEventListener('click', save);
})();
