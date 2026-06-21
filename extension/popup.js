/*
 * popup.js — the extension UI controller.
 *
 * Talks to the local backend over fetch and to the active tab's content script
 * over chrome.tabs.sendMessage. Persists product URL, backend URL and selected
 * site ids to chrome.storage.local.
 */
'use strict';

(function () {
  var DEFAULT_BACKEND = 'http://127.0.0.1:8000';

  // ---- state ----
  var state = {
    backendUrl: DEFAULT_BACKEND,
    productUrl: '',
    sites: [],            // [{id,name,url,...}]
    selectedSiteIds: [],
    generated: [],        // [{site_id, site_name}]
    currentTab: null,     // chrome tab
    currentMatch: null    // matched site for the current tab
  };

  // ---- element handles ----
  var $ = function (id) { return document.getElementById(id); };
  var el = {
    productUrl: $('product-url'),
    backendUrl: $('backend-url'),
    btnScan: $('btn-scan'),
    btnSites: $('btn-sites'),
    productCard: $('product-card'),
    productName: $('product-name'),
    productTagline: $('product-tagline'),
    productLogo: $('product-logo'),
    sitesCard: $('sites-card'),
    sitesCount: $('sites-count'),
    sitesList: $('sites-list'),
    btnSelectAll: $('btn-select-all'),
    btnSelectNone: $('btn-select-none'),
    btnGenerate: $('btn-generate'),
    generatedCard: $('generated-card'),
    generatedCount: $('generated-count'),
    generatedList: $('generated-list'),
    currentHost: $('current-host'),
    matchInfo: $('match-info'),
    btnFill: $('btn-fill'),
    fillResult: $('fill-result'),
    authBlock: $('auth-block'),
    authNotes: $('auth-notes'),
    btnSignin: $('btn-signin'),
    notesList: $('notes-list'),
    status: $('status'),
    openOptions: $('open-options')
  };

  // ---------------------------------------------------------------------------
  // helpers
  // ---------------------------------------------------------------------------

  function base() {
    var b = (el.backendUrl.value || DEFAULT_BACKEND).trim();
    return b.replace(/\/+$/, '');
  }

  function setStatus(msg, kind) {
    el.status.textContent = msg;
    el.status.className = 'pl-status' + (kind ? ' ' + kind : '');
    el.status.classList.remove('pl-hidden');
    if (kind === 'ok') {
      setTimeout(function () { el.status.classList.add('pl-hidden'); }, 2500);
    }
  }
  function clearStatus() { el.status.classList.add('pl-hidden'); }

  function show(node) { node.classList.remove('pl-hidden'); }
  function hide(node) { node.classList.add('pl-hidden'); }

  /** Strip protocol/www and lowercase a hostname for tab<->site matching. */
  function hostOf(urlString) {
    if (!urlString) return '';
    try {
      var u = new URL(urlString);
      return u.hostname.replace(/^www\./i, '').toLowerCase();
    } catch (e) {
      // Bare host fallback.
      return String(urlString).replace(/^https?:\/\//i, '').replace(/^www\./i, '').split('/')[0].toLowerCase();
    }
  }

  function persist() {
    chrome.storage.local.set({
      backendUrl: base(),
      productUrl: el.productUrl.value.trim(),
      selectedSiteIds: state.selectedSiteIds
    });
  }

  /** fetch JSON with friendly error surfacing. Returns parsed data or throws. */
  function apiFetch(path, options) {
    var url = base() + path;
    return fetch(url, options).then(function (resp) {
      return resp.text().then(function (text) {
        var data = null;
        try { data = text ? JSON.parse(text) : null; } catch (e) { data = text; }
        if (!resp.ok) {
          var detail = data && data.detail ? data.detail : (resp.status + ' ' + resp.statusText);
          var err = new Error(detail);
          err.status = resp.status;
          throw err;
        }
        return data;
      });
    }, function (networkErr) {
      var err = new Error('Cannot reach backend at ' + base() + '. Is it running?');
      err.cause = networkErr;
      throw err;
    });
  }

  function disableWhile(button, fn) {
    var orig = button.textContent;
    button.disabled = true;
    return Promise.resolve()
      .then(fn)
      .finally(function () { button.disabled = false; button.textContent = orig; });
  }

  // ---------------------------------------------------------------------------
  // actions: scan
  // ---------------------------------------------------------------------------

  function doScan() {
    var url = el.productUrl.value.trim();
    if (!url) { setStatus('Enter a product URL first.', 'err'); return; }
    persist();
    setStatus('Scanning ' + url + ' …');
    return disableWhile(el.btnScan, function () {
      return apiFetch('/api/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url, force: false })
      }).then(function (product) {
        renderProduct(product);
        setStatus('Scanned: ' + (product.name || url), 'ok');
      }).catch(function (e) {
        setStatus(e.message, 'err');
      });
    });
  }

  function renderProduct(product) {
    if (!product) return;
    el.productName.textContent = product.name || '(unnamed product)';
    el.productTagline.textContent = product.tagline || product.description_short || '';
    var logo = product.assets && product.assets.logo;
    var logoUrl = logo ? (logo.url || logo.local_path) : '';
    if (logoUrl && /^https?:\/\//i.test(logoUrl)) {
      el.productLogo.src = logoUrl;
      show(el.productLogo);
    } else {
      hide(el.productLogo);
    }
    show(el.productCard);
  }

  // ---------------------------------------------------------------------------
  // actions: load sites
  // ---------------------------------------------------------------------------

  function doLoadSites() {
    persist();
    setStatus('Loading launch sites …');
    return disableWhile(el.btnSites, function () {
      return apiFetch('/api/sites', { method: 'GET' }).then(function (data) {
        state.sites = (data && data.sites) || [];
        renderSites();
        updateCurrentMatch();
        setStatus('Loaded ' + state.sites.length + ' sites.', 'ok');
      }).catch(function (e) {
        setStatus(e.message, 'err');
      });
    });
  }

  function renderSites() {
    el.sitesList.innerHTML = '';
    var selected = {};
    state.selectedSiteIds.forEach(function (id) { selected[id] = true; });

    state.sites.forEach(function (site) {
      var row = document.createElement('label');
      row.className = 'pl-site';

      var cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.value = site.id;
      cb.checked = !!selected[site.id];
      cb.addEventListener('change', function () {
        onSiteToggle(site.id, cb.checked);
      });

      var body = document.createElement('div');
      body.className = 'pl-site-body';

      var name = document.createElement('div');
      name.className = 'pl-site-name';
      name.textContent = site.name;

      var meta = document.createElement('div');
      meta.className = 'pl-site-meta';

      var qc = document.createElement('span');
      qc.className = 'pl-chip';
      qc.textContent = (site.question_count != null ? site.question_count : '?') + ' questions';
      meta.appendChild(qc);

      var auth = document.createElement('span');
      auth.className = 'pl-chip pl-chip-auth';
      auth.textContent = site.auth_type || 'auth?';
      meta.appendChild(auth);

      if (site.fee) {
        var fee = document.createElement('span');
        fee.className = 'pl-chip';
        fee.textContent = site.fee;
        meta.appendChild(fee);
      }

      body.appendChild(name);
      body.appendChild(meta);
      row.appendChild(cb);
      row.appendChild(body);
      el.sitesList.appendChild(row);
    });

    el.sitesCount.textContent = state.sites.length + ' total';
    show(el.sitesCard);
  }

  function onSiteToggle(id, checked) {
    var idx = state.selectedSiteIds.indexOf(id);
    if (checked && idx === -1) state.selectedSiteIds.push(id);
    if (!checked && idx !== -1) state.selectedSiteIds.splice(idx, 1);
    persist();
  }

  function setAllChecks(checked) {
    state.selectedSiteIds = checked ? state.sites.map(function (s) { return s.id; }) : [];
    var boxes = el.sitesList.querySelectorAll('input[type="checkbox"]');
    for (var i = 0; i < boxes.length; i++) boxes[i].checked = checked;
    persist();
  }

  // ---------------------------------------------------------------------------
  // actions: generate
  // ---------------------------------------------------------------------------

  function doGenerate() {
    var url = el.productUrl.value.trim();
    if (!url) { setStatus('Enter a product URL first.', 'err'); return; }
    if (!state.selectedSiteIds.length) { setStatus('Select at least one site.', 'err'); return; }
    persist();
    setStatus('Generating answers for ' + state.selectedSiteIds.length + ' site(s) …');
    return disableWhile(el.btnGenerate, function () {
      return apiFetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url, site_ids: state.selectedSiteIds, force_scan: false })
      }).then(function (data) {
        state.generated = (data && data.answer_sets) || [];
        renderGenerated();
        updateCurrentMatch();
        setStatus('Generated ' + state.generated.length + ' answer set(s).', 'ok');
      }).catch(function (e) {
        setStatus(e.message, 'err');
      });
    });
  }

  function renderGenerated() {
    el.generatedList.innerHTML = '';
    state.generated.forEach(function (set) {
      var item = document.createElement('div');
      item.className = 'pl-gen-item';
      var name = document.createElement('span');
      name.textContent = set.site_name || set.site_id;
      var count = document.createElement('span');
      count.className = 'pl-muted';
      var n = (set.fill_plan && set.fill_plan.length) || 0;
      count.textContent = n + ' fields';
      item.appendChild(name);
      item.appendChild(count);
      el.generatedList.appendChild(item);
    });
    el.generatedCount.textContent = state.generated.length + ' ready';
    if (state.generated.length) show(el.generatedCard); else hide(el.generatedCard);
  }

  // ---------------------------------------------------------------------------
  // current tab matching + fill
  // ---------------------------------------------------------------------------

  function loadCurrentTab() {
    if (!chrome.tabs) return Promise.resolve();
    return new Promise(function (resolve) {
      chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
        state.currentTab = (tabs && tabs[0]) || null;
        if (state.currentTab) {
          el.currentHost.textContent = hostOf(state.currentTab.url);
        }
        updateCurrentMatch();
        resolve();
      });
    });
  }

  /** Find the site whose hostname matches the current tab's hostname. */
  function findMatchingSite() {
    if (!state.currentTab || !state.currentTab.url) return null;
    var tabHost = hostOf(state.currentTab.url);
    if (!tabHost) return null;
    for (var i = 0; i < state.sites.length; i++) {
      var siteHost = hostOf(state.sites[i].url);
      if (!siteHost) continue;
      if (tabHost === siteHost || tabHost.endsWith('.' + siteHost) || siteHost.endsWith('.' + tabHost)) {
        return state.sites[i];
      }
    }
    return null;
  }

  function updateCurrentMatch() {
    state.currentMatch = findMatchingSite();
    if (state.currentMatch) {
      el.matchInfo.textContent = 'Matched: ' + state.currentMatch.name;
      el.matchInfo.classList.add('matched');
      el.btnFill.disabled = false;
    } else {
      el.matchInfo.textContent = state.sites.length
        ? 'This tab does not match a known launch site.'
        : 'Load launch sites, then open one in a tab.';
      el.matchInfo.classList.remove('matched');
      el.btnFill.disabled = true;
    }
  }

  function doFill() {
    var site = state.currentMatch;
    if (!site) { setStatus('No matching launch site for this tab.', 'err'); return; }
    var productUrl = el.productUrl.value.trim();
    if (!productUrl) { setStatus('Enter a product URL first.', 'err'); return; }
    persist();
    setStatus('Fetching answers for ' + site.name + ' …');
    hide(el.fillResult);

    return disableWhile(el.btnFill, function () {
      return apiFetch('/api/answers/' + encodeURIComponent(site.id) + '?url=' + encodeURIComponent(productUrl), {
        method: 'GET'
      }).then(function (answerSet) {
        return sendFill(answerSet);
      }).catch(function (e) {
        setStatus(e.message, 'err');
      });
    });
  }

  function sendFill(answerSet) {
    if (!answerSet || !answerSet.fill_plan) {
      setStatus('No fill plan returned for this site.', 'err');
      return;
    }
    renderNotesAndAuth(answerSet);

    if (!state.currentTab || !chrome.tabs) {
      setStatus('No active tab to fill.', 'err');
      return;
    }
    setStatus('Filling the page …');
    return new Promise(function (resolve) {
      chrome.tabs.sendMessage(
        state.currentTab.id,
        { type: 'FILL', fillPlan: answerSet.fill_plan },
        function (resp) {
          if (chrome.runtime.lastError) {
            setStatus('Content script not loaded on this page. Reload the tab and retry.', 'err');
            resolve();
            return;
          }
          if (!resp || !resp.ok) {
            setStatus('Fill failed: ' + ((resp && resp.error) || 'unknown error'), 'err');
            resolve();
            return;
          }
          renderFillResult(resp.summary);
          setStatus('Done. Review the highlighted fields before submitting.', 'ok');
          resolve();
        }
      );
    });
  }

  function renderFillResult(summary) {
    if (!summary) return;
    el.fillResult.innerHTML = '';
    var stats = [
      { num: summary.filled, lbl: 'filled', cls: 'pl-stat-ok' },
      { num: summary.manual_required, lbl: 'manual', cls: 'pl-stat-warn' },
      { num: summary.not_found, lbl: 'not found', cls: 'pl-stat-err' }
    ];
    stats.forEach(function (s) {
      var box = document.createElement('div');
      box.className = 'pl-stat ' + s.cls;
      var num = document.createElement('span');
      num.className = 'pl-stat-num';
      num.textContent = s.num != null ? s.num : 0;
      var lbl = document.createElement('span');
      lbl.className = 'pl-stat-lbl';
      lbl.textContent = s.lbl;
      box.appendChild(num);
      box.appendChild(lbl);
      el.fillResult.appendChild(box);
    });
    show(el.fillResult);
  }

  function renderNotesAndAuth(answerSet) {
    // notes
    el.notesList.innerHTML = '';
    var notes = answerSet.notes || [];
    if (notes.length) {
      notes.forEach(function (n) {
        var li = document.createElement('li');
        li.textContent = n;
        el.notesList.appendChild(li);
      });
      show(el.notesList);
    } else {
      hide(el.notesList);
    }

    // auth
    var auth = answerSet.auth || {};
    state.currentAuth = auth;
    if (auth.type && auth.type !== 'none' && auth.type !== 'email') {
      el.authNotes.textContent = 'Sign-in: ' + auth.type +
        (auth.notes ? ' — ' + auth.notes : '');
      show(el.authBlock);
    } else if (auth.type === 'email') {
      el.authNotes.textContent = 'Email account' + (auth.notes ? ' — ' + auth.notes : '');
      show(el.authBlock);
    } else {
      hide(el.authBlock);
    }
  }

  // ---------------------------------------------------------------------------
  // sign-in assist (DETECT_AUTH then CLICK_AUTH)
  // ---------------------------------------------------------------------------

  function doSignIn() {
    if (!state.currentTab || !chrome.tabs) { setStatus('No active tab.', 'err'); return; }
    setStatus('Looking for a sign-in button …');
    chrome.tabs.sendMessage(state.currentTab.id, { type: 'DETECT_AUTH' }, function (resp) {
      if (chrome.runtime.lastError) {
        setStatus('Content script not loaded. Reload the tab and retry.', 'err');
        return;
      }
      if (!resp || !resp.found) {
        setStatus('No sign-in button detected on this page.', 'err');
        return;
      }
      setStatus('Clicking: ' + (resp.text || 'sign-in') + ' …');
      chrome.tabs.sendMessage(state.currentTab.id, { type: 'CLICK_AUTH' }, function (clickResp) {
        if (chrome.runtime.lastError) { setStatus('Could not click sign-in.', 'err'); return; }
        if (clickResp && clickResp.clicked) {
          setStatus('Sign-in opened. Complete any OAuth / CAPTCHA yourself.', 'ok');
        } else {
          setStatus('Found the button but could not click it.', 'err');
        }
      });
    });
  }

  // ---------------------------------------------------------------------------
  // init
  // ---------------------------------------------------------------------------

  function restore() {
    return new Promise(function (resolve) {
      chrome.storage.local.get(
        { backendUrl: DEFAULT_BACKEND, productUrl: '', selectedSiteIds: [] },
        function (cfg) {
          el.backendUrl.value = cfg.backendUrl || DEFAULT_BACKEND;
          el.productUrl.value = cfg.productUrl || '';
          state.selectedSiteIds = cfg.selectedSiteIds || [];
          state.backendUrl = el.backendUrl.value;
          resolve();
        }
      );
    });
  }

  function wire() {
    el.btnScan.addEventListener('click', doScan);
    el.btnSites.addEventListener('click', doLoadSites);
    el.btnGenerate.addEventListener('click', doGenerate);
    el.btnFill.addEventListener('click', doFill);
    el.btnSignin.addEventListener('click', doSignIn);
    el.btnSelectAll.addEventListener('click', function () { setAllChecks(true); });
    el.btnSelectNone.addEventListener('click', function () { setAllChecks(false); });
    el.productUrl.addEventListener('change', persist);
    el.backendUrl.addEventListener('change', persist);
    el.openOptions.addEventListener('click', function (e) {
      e.preventDefault();
      if (chrome.runtime && chrome.runtime.openOptionsPage) chrome.runtime.openOptionsPage();
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    wire();
    restore()
      .then(loadCurrentTab)
      .then(function () {
        // Auto-load sites so "Fill This Page" can match immediately, but stay
        // quiet about backend errors here — the user can retry explicitly.
        return apiFetch('/api/sites', { method: 'GET' })
          .then(function (data) {
            state.sites = (data && data.sites) || [];
            renderSites();
            updateCurrentMatch();
            clearStatus();
          })
          .catch(function () { /* backend may be down; leave UI ready */ });
      });
  });
})();
