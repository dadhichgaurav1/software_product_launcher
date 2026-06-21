/*
 * Self-contained Node test for fill_engine.js — no external dependencies.
 *
 * It builds a deliberately minimal fake DOM: each element carries a tagName,
 * value, a `_listeners` map, addEventListener / dispatchEvent (which invokes
 * listeners AND records the events it saw), setAttribute, a `style` object and
 * a classList stub. A tiny `FakeRoot` implements querySelector over a registry
 * keyed by the exact selector string.
 *
 * Because the fake elements have no real prototypes, fill_engine's
 * Object.getOwnPropertyDescriptor lookup finds nothing and setNativeValue falls
 * back to `el.value = value` — which is exactly the behaviour we assert here.
 */
'use strict';

var FillEngine = require('../fill_engine.js');

// ---------------------------------------------------------------------------
// minimal fake DOM
// ---------------------------------------------------------------------------

function FakeElement(tagName, props) {
  this.tagName = (tagName || 'INPUT').toUpperCase();
  this.value = '';
  this.checked = false;
  this.textContent = '';
  this._attrs = {};
  this._listeners = {};
  this.events = []; // record of dispatched event types, for assertions
  this.clicked = 0;
  this.style = {}; // present so highlight() can write to it
  this.classList = {
    _set: {},
    add: function (c) { this._set[c] = true; },
    remove: function (c) { delete this._set[c]; },
    contains: function (c) { return !!this._set[c]; }
  };
  if (props) {
    for (var k in props) {
      if (Object.prototype.hasOwnProperty.call(props, k)) this[k] = props[k];
    }
  }
}
FakeElement.prototype.addEventListener = function (type, fn) {
  if (!this._listeners[type]) this._listeners[type] = [];
  this._listeners[type].push(fn);
};
FakeElement.prototype.dispatchEvent = function (evt) {
  var type = evt && evt.type;
  this.events.push(type);
  var fns = this._listeners[type] || [];
  for (var i = 0; i < fns.length; i++) {
    try { fns[i].call(this, evt); } catch (e) { /* ignore */ }
  }
  return true;
};
FakeElement.prototype.setAttribute = function (name, val) {
  this._attrs[name] = val;
};
FakeElement.prototype.getAttribute = function (name) {
  return Object.prototype.hasOwnProperty.call(this._attrs, name) ? this._attrs[name] : null;
};
FakeElement.prototype.click = function () { this.clicked += 1; };

function FakeRoot() {
  this._registry = {}; // selector string -> FakeElement
}
FakeRoot.prototype.register = function (selector, el) {
  this._registry[selector] = el;
  return el;
};
FakeRoot.prototype.querySelector = function (selector) {
  return Object.prototype.hasOwnProperty.call(this._registry, selector)
    ? this._registry[selector]
    : null;
};
FakeRoot.prototype.querySelectorAll = function (selector) {
  // Good enough for detectAuthButton: return the single registered match (if any)
  // wrapped in an array-like.
  var el = this.querySelector(selector);
  return el ? [el] : [];
};

// ---------------------------------------------------------------------------
// tiny assertion harness
// ---------------------------------------------------------------------------

var passed = 0;
function fail(name, msg) {
  console.error('FAILED: ' + name + ' -> ' + msg);
  process.exit(1);
}
function ok(name, cond, msg) {
  if (!cond) fail(name, msg || 'assertion failed');
  passed += 1;
}
function eq(name, actual, expected) {
  if (actual !== expected) {
    fail(name, 'expected ' + JSON.stringify(expected) + ' but got ' + JSON.stringify(actual));
  }
  passed += 1;
}

// ---------------------------------------------------------------------------
// tests
// ---------------------------------------------------------------------------

// 1. setNativeValue sets value and fires input + change
(function testSetNativeValue() {
  var el = new FakeElement('INPUT');
  FillEngine.setNativeValue(el, 'hello world');
  eq('setNativeValue value', el.value, 'hello world');
  ok('setNativeValue fired input', el.events.indexOf('input') !== -1, 'input not dispatched');
  ok('setNativeValue fired change', el.events.indexOf('change') !== -1, 'change not dispatched');
})();

// 2. applyStep fill on a found input -> status "filled" and value set
(function testApplyStepFillFound() {
  var root = new FakeRoot();
  var input = new FakeElement('INPUT');
  root.register('#name', input);
  var res = FillEngine.applyStep(root, {
    selectors: ['#missing', '#name'],
    action: 'fill',
    value: 'Acme',
    question_id: 'name'
  });
  eq('applyStep fill status', res.status, 'filled');
  eq('applyStep fill value applied', input.value, 'Acme');
  eq('applyStep fill question_id', res.question_id, 'name');
  eq('applyStep fill matched selector', res.selector, '#name');
})();

// 3. applyStep fill on a missing selector -> not_found
(function testApplyStepFillMissing() {
  var root = new FakeRoot();
  var res = FillEngine.applyStep(root, {
    selectors: ['#nope', '.also-nope'],
    action: 'fill',
    value: 'x',
    question_id: 'q'
  });
  eq('applyStep missing status', res.status, 'not_found');
})();

// 4. applyStep upload -> manual_required (even when element exists)
(function testApplyStepUpload() {
  var root = new FakeRoot();
  var fileInput = new FakeElement('INPUT', { type: 'file' });
  root.register("input[type='file']", fileInput);
  var res = FillEngine.applyStep(root, {
    selectors: ["input[type='file']"],
    action: 'upload',
    value: '/tmp/logo.png',
    question_id: 'logo'
  });
  eq('applyStep upload status', res.status, 'manual_required');
})();

// 5. applyStep select -> picks the matching option (case-insensitive contains)
(function testApplyStepSelect() {
  var root = new FakeRoot();
  var select = new FakeElement('SELECT');
  select.options = [
    { value: 'dev-tools', text: 'Developer Tools' },
    { value: 'productivity', text: 'Productivity' },
    { value: 'ai', text: 'Artificial Intelligence' }
  ];
  select.selectedIndex = -1;
  root.register('#cat', select);
  var res = FillEngine.applyStep(root, {
    selectors: ['#cat'],
    action: 'select',
    value: 'productivity',
    question_id: 'category'
  });
  eq('applyStep select status', res.status, 'selected');
  eq('applyStep select index', select.selectedIndex, 1);
})();

// 6. applyStep check -> sets checked from truthy value
(function testApplyStepCheck() {
  var root = new FakeRoot();
  var box = new FakeElement('INPUT', { type: 'checkbox' });
  root.register('#tos', box);
  var res = FillEngine.applyStep(root, {
    selectors: ['#tos'], action: 'check', value: 'true', question_id: 'tos'
  });
  eq('applyStep check status', res.status, 'checked');
  eq('applyStep check checked', box.checked, true);
})();

// 7. applyPlan aggregates counts correctly
(function testApplyPlan() {
  var root = new FakeRoot();
  root.register('#a', new FakeElement('INPUT'));            // will be filled
  root.register('#b', new FakeElement('TEXTAREA'));         // will be filled
  root.register("input[type='file']", new FakeElement('INPUT', { type: 'file' })); // manual
  // '#missing' intentionally not registered -> not_found
  var plan = [
    { selectors: ['#a'], action: 'fill', value: '1', question_id: 'a' },
    { selectors: ['#b'], action: 'fill', value: '2', question_id: 'b' },
    { selectors: ["input[type='file']"], action: 'upload', value: 'f', question_id: 'logo' },
    { selectors: ['#missing'], action: 'fill', value: '3', question_id: 'm' }
  ];
  var summary = FillEngine.applyPlan(root, plan);
  eq('applyPlan filled', summary.filled, 2);
  eq('applyPlan manual_required', summary.manual_required, 1);
  eq('applyPlan not_found', summary.not_found, 1);
  eq('applyPlan results length', summary.results.length, 4);
})();

// 8. detectAuthButton finds a "Sign in with Google" button
(function testDetectAuth() {
  var root = new FakeRoot();
  var btn = new FakeElement('BUTTON');
  btn.textContent = 'Sign in with Google';
  root.register('button', btn);
  var found = FillEngine.detectAuthButton(root);
  ok('detectAuthButton found', found === btn, 'did not return the Google button');
  eq('detectAuthButton text', FillEngine.elementText(found), 'sign in with google');
})();

// 9. detectAuthButton returns null when there is no auth control
(function testDetectAuthNone() {
  var root = new FakeRoot();
  var btn = new FakeElement('BUTTON');
  btn.textContent = 'Add to cart';
  root.register('button', btn);
  var found = FillEngine.detectAuthButton(root);
  ok('detectAuthButton none', !found, 'unexpectedly matched a non-auth button');
})();

// ---------------------------------------------------------------------------
// done
// ---------------------------------------------------------------------------
console.log('fill_engine tests passed: ' + passed);
process.exit(0);
