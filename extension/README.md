# Software Product Launcher — Chrome Extension (Manifest V3)

An agentic browser extension that auto-fills software-product submission forms
across ~20 launch directories (BetaList, Fazier, Uneed, Peerlist, …) and assists
with Google / GitHub sign-in. It talks to a local backend that scans your
product site, understands it, and generates best-practice answers plus a concrete
**fill plan** per launch site. The extension executes that plan in the page and
leaves every form ready for you to review and submit.

## What's in here

| File | Purpose |
| --- | --- |
| `manifest.json` | MV3 manifest. |
| `fill_engine.js` | **Core**, pure & unit-tested. Resolves selectors, sets native input values (so React/Vue notice), runs the fill plan, detects auth buttons. |
| `content.js` | Page-side message handler (`FILL`, `DETECT_AUTH`, `CLICK_AUTH`, `PING`) **and the in-page Fill panel** shown when the web page arms a task. Delegates DOM work to `FillEngine`. |
| `bridge.js` | Content script injected into the **web app** (localhost). Announces the extension to the page and relays `SYNC_CONFIG` / `LAUNCH_FILL` to the worker — this is what lets the web page trigger the extension. |
| `background.js` | MV3 service worker. Seeds config; backend-fetch proxy (CORS-safe); arms/serves per-site fill **tasks** in session storage. |
| `popup.html/.js/.css` | Manual-fallback UI: scan, load sites, generate, fill current page, sign-in assist. |
| `options.html/.js` | Settings: Backend Base URL and default Product URL. |
| `test/fill_engine.test.js` | Self-contained Node test for the core engine. |
| `test/bridge.test.js` | Node test for the web↔extension message protocol (mocked `chrome`). |
| `icons/` | Place real PNG icons here (optional — Chrome shows a default without them). |

## Install (load unpacked)

1. Make sure the backend is running (default `http://127.0.0.1:8000`):
   from the repo root, start the FastAPI server (see the backend README).
2. Open `chrome://extensions` in Chrome (or any Chromium browser).
3. Toggle **Developer mode** on (top-right).
4. Click **Load unpacked** and select this `extension/` folder.
5. Pin the extension and click its icon to open the popup.

## Configure the backend URL

- Open the popup → the **Backend URL** field (default `http://127.0.0.1:8000`).
- Or click the ⚙ gear → the **Options** page to set the Backend Base URL and a
  default Product URL. Both are stored in `chrome.storage.local` and shared by
  the popup, options page and service worker.

## Recommended flow — triggered from the web page (no popup)

Once the extension is loaded, the web app (`http://127.0.0.1:8000`) detects it and
shows **“Extension connected.”** The page and extension then share the session
automatically — you never re-enter the product URL or backend in the extension.

1. In the **web page**, Scan → Generate your drafts as usual.
2. Click **“Open & Fill”** on a site (or **“Open & fill all”**). The page tells the
   extension which product + site, and the extension opens that launch site.
3. The launch-site tab shows a small **Product Launcher panel** (bottom-right):
   - **Help me sign in** — detects & clicks the Google/GitHub sign-in button.
   - **Fill this page** — pulls the *same* draft from your backend and fills every
     field (green = filled, orange = needs you, e.g. file uploads).
4. Review and **submit** yourself.

No popup, no copy-paste — the web page drives the whole thing.

## Manual fallback flow (popup)

1. Enter your **Product URL** and click **Scan & Understand**
   (`POST /api/scan`) — the popup shows the product name, tagline and logo.
2. Click **Load Launch Sites** (`GET /api/sites`) — pick the directories you want
   to submit to (each row shows its question count and auth type).
3. Click **Generate Answers** (`POST /api/generate`) — the backend produces an
   answer set + fill plan per selected site.
4. Open one of the launch sites in a tab. The popup matches the tab's hostname to
   a known site; click **Fill This Page**. It fetches
   `GET /api/answers/{site_id}?url=…` and sends the fill plan to the page.
   Filled fields are outlined green; fields needing manual attention (file
   uploads) are outlined orange. You then **review and submit** yourself.
5. If the site needs Google / GitHub sign-in, use **Help me sign in** — the
   extension detects and clicks the sign-in button; you complete OAuth/CAPTCHA.

## Security notes

### Broad `https://*/*` host permission
Launch directories live on many different domains (and new ones are added over
time), so the content script and host permission use `https://*/*`. This is what
lets the fill engine run on *any* launch site without shipping a hard-coded
allow-list. The extension only acts when **you** click a button in the popup; it
does not exfiltrate page data — fill plans flow one way, from your local backend
into the page. If you prefer a tighter scope, replace `https://*/*` in
`manifest.json` (both `host_permissions` and `content_scripts[].matches`) with the
explicit list of launch-site origins.

### File uploads are never scripted
Browsers forbid pages and extensions from setting the value of
`<input type="file">` for security reasons. For `upload` steps the engine
therefore **cannot** attach the file; it highlights the field orange and reports
`manual_required`. The popup shows the suggested asset path in the notes, and you
attach the file with a single click. This is by design and cannot be bypassed.

### Sign-in is assisted, not automated
Google / Gmail account creation and login (and GitHub OAuth) are **assisted**:
the extension detects the provider button and can click it for you, but you
complete any OAuth consent, password entry, 2FA and CAPTCHA **manually**.
The extension never handles your credentials.

## Running the core test

```bash
cd extension
node test/fill_engine.test.js   # fill engine: selectors, native values, plan outcomes
node test/bridge.test.js        # web<->extension protocol: LAUNCH_FILL/GET_TASK/FETCH_ANSWERS
```

The first builds a minimal in-memory DOM and asserts the fill engine's behaviour;
the second mocks `chrome` + `fetch` and verifies the background worker arms tasks,
serves them to the launch-site tab, and proxies the backend answers fetch. Both
print a pass line and exit 0.

## Notes / limitations

- No build step, no npm, no frameworks — plain vanilla JS, valid for Chrome MV3.
- Live account creation / submission on real sites depends on each site's ToS,
  CAPTCHA and your credentials and is intentionally left to the user.
