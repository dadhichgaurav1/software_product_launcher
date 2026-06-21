/*
 * fill_engine.js — the pure, unit-testable core of the Software Product Launcher.
 *
 * Exposes a single global object `FillEngine`. It is assigned to globalThis
 * (so it works as a content script in the page / service worker) AND exported
 * via module.exports when running under Node, so the test harness can
 * `require('../fill_engine.js')` and exercise the logic with a fake DOM.
 *
 * Design rule: every piece of DOM access goes through the `root` argument
 * (defaults to `document`) and every optional DOM API is feature-detected, so
 * the logic runs unchanged under a minimal in-memory shim during tests.
 */
(function () {
  'use strict';

  // ---------------------------------------------------------------------------
  // small helpers
  // ---------------------------------------------------------------------------

  /** Truthy interpretation that treats common "false-ish" strings as false. */
  function truthy(value) {
    if (typeof value === 'string') {
      var v = value.trim().toLowerCase();
      if (v === '' || v === 'false' || v === '0' || v === 'no' || v === 'off' || v === 'unchecked') {
        return false;
      }
      return true;
    }
    return !!value;
  }

  /** Lower-case + collapse whitespace, for robust text matching. */
  function normText(s) {
    if (s == null) return '';
    return String(s).replace(/\s+/g, ' ').trim().toLowerCase();
  }

  /** Best-effort dispatch of a bubbling DOM event; no-op under the test shim. */
  function fireEvent(el, type) {
    if (!el || typeof el.dispatchEvent !== 'function') return;
    var evt = null;
    // Prefer the modern Event constructor; fall back gracefully.
    try {
      if (typeof Event === 'function') {
        evt = new Event(type, { bubbles: true, cancelable: true });
      }
    } catch (e) {
      evt = null;
    }
    if (!evt && typeof document !== 'undefined' && document.createEvent) {
      try {
        evt = document.createEvent('Event');
        evt.initEvent(type, true, true);
      } catch (e2) {
        evt = null;
      }
    }
    if (!evt) {
      // Minimal duck-typed event so a shim's dispatchEvent still gets called.
      evt = { type: type, bubbles: true, cancelable: true };
    }
    try {
      el.dispatchEvent(evt);
    } catch (e3) {
      /* ignore — never let event dispatch break a fill */
    }
  }

  // ---------------------------------------------------------------------------
  // element resolution
  // ---------------------------------------------------------------------------

  /**
   * Try each CSS selector in `selectors` (in priority order) against `root`
   * and return the first matching element, or null.
   */
  function resolveElement(root, selectors) {
    root = root || (typeof document !== 'undefined' ? document : null);
    if (!root || typeof root.querySelector !== 'function') return null;
    if (!selectors) return null;
    if (typeof selectors === 'string') selectors = [selectors];
    for (var i = 0; i < selectors.length; i++) {
      var sel = selectors[i];
      if (!sel) continue;
      var el = null;
      try {
        el = root.querySelector(sel);
      } catch (e) {
        el = null; // invalid selector — skip, try the next one
      }
      if (el) return el;
    }
    return null;
  }

  // ---------------------------------------------------------------------------
  // native value setting (so React / Vue controlled inputs notice the change)
  // ---------------------------------------------------------------------------

  /**
   * Set `el.value` using the element's *native* prototype setter so frameworks
   * that track the value internally (React's value tracker, Vue v-model) detect
   * the change, then dispatch bubbling `input` and `change` events.
   *
   * Falls back to a plain `el.value = value` when the native descriptor cannot
   * be found (e.g. under the test shim, or for unusual elements).
   */
  function setNativeValue(el, value) {
    if (!el) return false;
    var tag = (el.tagName || '').toUpperCase();
    var proto = null;

    if (typeof window !== 'undefined') {
      if (tag === 'TEXTAREA' && window.HTMLTextAreaElement) {
        proto = window.HTMLTextAreaElement.prototype;
      } else if (tag === 'SELECT' && window.HTMLSelectElement) {
        proto = window.HTMLSelectElement.prototype;
      } else if (window.HTMLInputElement) {
        proto = window.HTMLInputElement.prototype;
      }
    }

    var set = false;
    if (proto && typeof Object.getOwnPropertyDescriptor === 'function') {
      var desc = null;
      try {
        desc = Object.getOwnPropertyDescriptor(proto, 'value');
      } catch (e) {
        desc = null;
      }
      if (desc && typeof desc.set === 'function') {
        try {
          desc.set.call(el, value);
          set = true;
        } catch (e2) {
          set = false;
        }
      }
    }

    if (!set) {
      // Fallback: works for native elements without a discoverable setter and
      // for the in-memory test shim.
      try {
        el.value = value;
        set = true;
      } catch (e3) {
        set = false;
      }
    }

    fireEvent(el, 'input');
    fireEvent(el, 'change');
    return set;
  }

  // ---------------------------------------------------------------------------
  // <select> handling
  // ---------------------------------------------------------------------------

  /**
   * Pick the best-matching <option> for `value` (case-insensitive: exact value,
   * exact text, then "contains" either way) and select it.
   */
  function selectOption(el, value) {
    if (!el) return false;
    var options = el.options;
    if (!options || typeof options.length !== 'number') {
      // No options collection (shim) — set value directly as a best effort.
      setNativeValue(el, value);
      return true;
    }
    var want = normText(value);
    if (!want) return false;

    var exactValue = -1;
    var exactText = -1;
    var containsIdx = -1;

    for (var i = 0; i < options.length; i++) {
      var opt = options[i];
      if (!opt) continue;
      var ov = normText(opt.value);
      var ot = normText(opt.text != null ? opt.text : opt.textContent);
      if (exactValue === -1 && ov === want) exactValue = i;
      if (exactText === -1 && ot === want) exactText = i;
      if (containsIdx === -1) {
        if ((ov && (ov.indexOf(want) !== -1 || want.indexOf(ov) !== -1)) ||
            (ot && (ot.indexOf(want) !== -1 || want.indexOf(ot) !== -1))) {
          containsIdx = i;
        }
      }
    }

    var chosen = exactValue !== -1 ? exactValue
      : exactText !== -1 ? exactText
        : containsIdx;
    if (chosen === -1) return false;

    try {
      el.selectedIndex = chosen;
    } catch (e) { /* shim may lack selectedIndex */ }
    var chosenOpt = options[chosen];
    if (chosenOpt && chosenOpt.value != null) {
      try { el.value = chosenOpt.value; } catch (e2) { /* ignore */ }
    }
    fireEvent(el, 'input');
    fireEvent(el, 'change');
    return true;
  }

  // ---------------------------------------------------------------------------
  // highlighting (visual feedback in the real page; no-op under the shim)
  // ---------------------------------------------------------------------------

  /**
   * Outline an element green (ok) or orange (manual attention needed). Guards
   * for elements that have no `style` object (test shim).
   */
  function highlight(el, ok) {
    if (!el || !el.style) return;
    var color = ok ? '#2e7d32' : '#ed6c02';
    try {
      el.style.outline = '2px solid ' + color;
      el.style.outlineOffset = '1px';
      el.style.transition = 'outline 0.15s ease-in-out';
      if (el.scrollIntoView && ok) {
        // best effort — bring the first filled field into view
      }
    } catch (e) {
      /* ignore styling failures */
    }
  }

  // ---------------------------------------------------------------------------
  // single step execution
  // ---------------------------------------------------------------------------

  /**
   * Execute one fill_plan step against `root`. Returns a result object:
   *   { question_id, action, status, selector }
   * status is one of: filled | selected | checked | clicked | manual_required | not_found
   */
  function applyStep(root, step) {
    root = root || (typeof document !== 'undefined' ? document : null);
    var result = {
      question_id: step && step.question_id ? step.question_id : '',
      action: step ? step.action : '',
      status: 'not_found',
      selector: null,
      element: null
    };
    if (!step) return result;

    var action = step.action || 'fill';
    var el = resolveElement(root, step.selectors);

    // upload is special: even when the element is found we cannot script it.
    if (action === 'upload') {
      if (!el) {
        result.status = 'not_found';
        return result;
      }
      result.element = el;
      result.selector = matchedSelector(root, step.selectors);
      result.status = 'manual_required';
      result.value = step.value;
      highlight(el, false); // orange — user must attach the file themselves
      return result;
    }

    if (!el) {
      result.status = 'not_found';
      return result;
    }
    result.element = el;
    result.selector = matchedSelector(root, step.selectors);

    switch (action) {
      case 'fill':
        setNativeValue(el, step.value != null ? step.value : '');
        result.status = 'filled';
        break;
      case 'select':
        if (selectOption(el, step.value != null ? step.value : '')) {
          result.status = 'selected';
        } else {
          result.status = 'not_found';
        }
        break;
      case 'check':
        try {
          el.checked = truthy(step.value);
        } catch (e) { /* shim */ }
        fireEvent(el, 'input');
        fireEvent(el, 'change');
        result.status = 'checked';
        break;
      case 'click':
        if (typeof el.click === 'function') {
          try { el.click(); } catch (e) { /* ignore */ }
        }
        result.status = 'clicked';
        break;
      default:
        // Unknown action — treat as a plain fill so nothing is silently lost.
        setNativeValue(el, step.value != null ? step.value : '');
        result.status = 'filled';
        break;
    }
    return result;
  }

  /** Return which selector in the list actually matched (for diagnostics). */
  function matchedSelector(root, selectors) {
    if (!root || typeof root.querySelector !== 'function' || !selectors) return null;
    if (typeof selectors === 'string') selectors = [selectors];
    for (var i = 0; i < selectors.length; i++) {
      try {
        if (selectors[i] && root.querySelector(selectors[i])) return selectors[i];
      } catch (e) { /* skip invalid */ }
    }
    return null;
  }

  // ---------------------------------------------------------------------------
  // whole-plan execution
  // ---------------------------------------------------------------------------

  /**
   * Execute every step in `fillPlan` and aggregate the outcome:
   *   { filled, not_found, manual_required, results:[stepResult, ...] }
   * `filled` counts every successfully actioned step (fill/select/check/click).
   */
  function applyPlan(root, fillPlan) {
    root = root || (typeof document !== 'undefined' ? document : null);
    var summary = { filled: 0, not_found: 0, manual_required: 0, results: [] };
    if (!fillPlan || typeof fillPlan.length !== 'number') return summary;

    for (var i = 0; i < fillPlan.length; i++) {
      var res = applyStep(root, fillPlan[i]);
      summary.results.push(res);
      if (res.status === 'manual_required') {
        summary.manual_required += 1;
      } else if (res.status === 'not_found') {
        summary.not_found += 1;
      } else {
        // filled | selected | checked | clicked
        summary.filled += 1;
      }
    }
    return summary;
  }

  // ---------------------------------------------------------------------------
  // auth button detection
  // ---------------------------------------------------------------------------

  var AUTH_RE = /(sign\s*in\s*with\s*google|continue\s*with\s*google|sign\s*up\s*with\s*google|log\s*in\s*with\s*google|sign\s*in\s*with\s*github|continue\s*with\s*github|continue\s*with\s*twitter|google|github|sign\s*up|sign\s*in|log\s*in|login|register|create\s*account|get\s*started)/i;

  /** Extract human-visible text from an element across DOM and shim shapes. */
  function elementText(el) {
    if (!el) return '';
    var parts = [];
    if (el.textContent) parts.push(el.textContent);
    if (el.innerText) parts.push(el.innerText);
    if (el.value) parts.push(el.value);
    if (typeof el.getAttribute === 'function') {
      var aria = el.getAttribute('aria-label');
      var title = el.getAttribute('title');
      var alt = el.getAttribute('alt');
      if (aria) parts.push(aria);
      if (title) parts.push(title);
      if (alt) parts.push(alt);
    } else {
      if (el['aria-label']) parts.push(el['aria-label']);
      if (el.title) parts.push(el.title);
    }
    return normText(parts.join(' '));
  }

  /**
   * Scan buttons / links / role=button elements and return the first whose
   * visible text looks like an OAuth or sign-in control. Google/GitHub matches
   * are preferred over generic "sign in".
   */
  function detectAuthButton(root) {
    root = root || (typeof document !== 'undefined' ? document : null);
    if (!root || typeof root.querySelectorAll !== 'function') {
      // Shim path: fall back to querySelector over a known candidate set.
      return detectAuthButtonFallback(root);
    }

    var candidates = [];
    var selectorGroups = [
      'button', 'a', '[role="button"]', 'input[type="submit"]',
      'input[type="button"]', '[data-provider]', '.btn', '.button'
    ];
    for (var g = 0; g < selectorGroups.length; g++) {
      var nodes;
      try {
        nodes = root.querySelectorAll(selectorGroups[g]);
      } catch (e) {
        nodes = null;
      }
      if (!nodes) continue;
      for (var i = 0; i < nodes.length; i++) {
        if (candidates.indexOf(nodes[i]) === -1) candidates.push(nodes[i]);
      }
    }

    var generic = null;
    for (var c = 0; c < candidates.length; c++) {
      var el = candidates[c];
      var text = elementText(el);
      if (!text) continue;
      if (/google|github/.test(text)) {
        return el; // strongest signal — OAuth provider button
      }
      if (!generic && AUTH_RE.test(text)) {
        generic = el; // remember the first generic sign-in control
      }
    }
    return generic;
  }

  /** Minimal fallback used when querySelectorAll is unavailable (test shim). */
  function detectAuthButtonFallback(root) {
    if (!root || typeof root.querySelector !== 'function') return null;
    var probes = [
      'button', 'a', '[role="button"]', 'input[type="submit"]',
      '.google-signin', '#google-signin'
    ];
    for (var i = 0; i < probes.length; i++) {
      var el;
      try { el = root.querySelector(probes[i]); } catch (e) { el = null; }
      if (el && AUTH_RE.test(elementText(el))) return el;
    }
    return null;
  }

  // ---------------------------------------------------------------------------
  // export
  // ---------------------------------------------------------------------------

  var FillEngine = {
    resolveElement: resolveElement,
    setNativeValue: setNativeValue,
    selectOption: selectOption,
    applyStep: applyStep,
    applyPlan: applyPlan,
    highlight: highlight,
    detectAuthButton: detectAuthButton,
    elementText: elementText,
    truthy: truthy,
    normText: normText,
    AUTH_RE: AUTH_RE
  };

  // Browser / service-worker global.
  if (typeof globalThis !== 'undefined') {
    globalThis.FillEngine = FillEngine;
  }
  if (typeof window !== 'undefined') {
    window.FillEngine = FillEngine;
  }
  // Node (tests).
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = FillEngine;
  }
})();
