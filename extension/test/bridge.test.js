/*
 * bridge.test.js — exercises the background worker's web<->extension message
 * protocol (LAUNCH_FILL -> GET_TASK -> FETCH_ANSWERS -> CLEAR_TASK) with a
 * mocked `chrome` + `fetch`. Run: node test/bridge.test.js
 */
'use strict';

var failures = 0;
function ok(cond, name) {
  if (cond) { console.log('  ✓ ' + name); }
  else { console.log('  ✗ ' + name); failures++; }
}

// --- minimal chrome + fetch mocks ------------------------------------------
var store = { local: {}, session: {} };
function area(name) {
  return {
    get: function (defaults, cb) {
      var out = {}, d = (defaults && typeof defaults === 'object') ? defaults : {};
      Object.keys(d).forEach(function (k) { out[k] = (k in store[name]) ? store[name][k] : d[k]; });
      cb(out);
    },
    set: function (obj, cb) { Object.assign(store[name], obj); if (cb) cb(); }
  };
}
var msgListener = null;
global.chrome = {
  runtime: {
    id: 'testid', lastError: null,
    onInstalled: { addListener: function () {} },
    onMessage: { addListener: function (fn) { msgListener = fn; } },
    getManifest: function () { return { version: '9.9.9' }; },
    sendMessage: function () {}
  },
  storage: { local: area('local'), session: area('session') },
  tabs: { create: function (opts, cb) { if (cb) cb({ id: 7, url: opts.url }); } }
};
var lastFetchUrl = null;
global.fetch = function (url) {
  lastFetchUrl = url;
  return Promise.resolve({
    ok: true, status: 200,
    text: function () {
      return Promise.resolve(JSON.stringify({
        site_id: 'devhunt',
        fill_plan: [{ selectors: ['#name'], action: 'fill', value: 'TaskPilot', question_id: 'name' }]
      }));
    }
  });
};

var bgMod = require('../background.js');

function send(msg) {
  return new Promise(function (resolve) {
    var kept = msgListener(msg, {}, resolve);
    if (kept !== true) resolve(undefined);
  });
}

(async function run() {
  // hostOf normalises www + paths
  ok(bgMod.hostOf('https://www.devhunt.org/tool/new') === 'devhunt.org', 'hostOf strips www + path');

  // LAUNCH_FILL arms a task and "opens" a tab
  var launch = await send({
    type: 'LAUNCH_FILL',
    payload: {
      backend: 'http://127.0.0.1:8000', product_url: 'https://taskpilot.ai',
      site_id: 'devhunt', site_name: 'DevHunt', site_url: 'https://devhunt.org/tool/new'
    }
  });
  ok(launch && launch.ok === true, 'LAUNCH_FILL returns ok');
  ok(launch.host === 'devhunt.org', 'LAUNCH_FILL reports the host');
  ok(store.local.backendUrl === 'http://127.0.0.1:8000', 'config synced to storage.local');
  ok(store.local.productUrl === 'https://taskpilot.ai', 'product url synced to storage.local');

  // GET_TASK returns the armed task (www-insensitive)
  var got = await send({ type: 'GET_TASK', host: 'www.devhunt.org' });
  ok(got && got.task && got.task.site_id === 'devhunt', 'GET_TASK returns the armed task');
  ok(got.task.product_url === 'https://taskpilot.ai', 'task carries the product url');

  // unknown host -> no task
  var none = await send({ type: 'GET_TASK', host: 'example.com' });
  ok(none && none.task === null, 'GET_TASK returns null for an un-armed host');

  // FETCH_ANSWERS proxies to the backend answers endpoint
  var fetched = await send({ type: 'FETCH_ANSWERS', backend: 'http://127.0.0.1:8000', site_id: 'devhunt', product_url: 'https://taskpilot.ai' });
  ok(fetched && fetched.ok && fetched.data && fetched.data.fill_plan.length === 1, 'FETCH_ANSWERS returns the draft');
  ok(/\/api\/answers\/devhunt\?url=https%3A/.test(lastFetchUrl), 'FETCH_ANSWERS builds the correct URL');

  // SYNC_CONFIG updates stored config
  await send({ type: 'SYNC_CONFIG', payload: { backend: 'http://localhost:9000/', product_url: 'https://x.co' } });
  ok(store.local.backendUrl === 'http://localhost:9000', 'SYNC_CONFIG normalises + stores backend');
  ok(store.local.productUrl === 'https://x.co', 'SYNC_CONFIG stores product url');

  // CLEAR_TASK removes it
  await send({ type: 'CLEAR_TASK', host: 'devhunt.org' });
  var cleared = await send({ type: 'GET_TASK', host: 'devhunt.org' });
  ok(cleared && cleared.task === null, 'CLEAR_TASK removes the task');

  if (failures) { console.log('\nbridge tests FAILED: ' + failures); process.exit(1); }
  console.log('\nbridge tests passed: all checks');
})();
