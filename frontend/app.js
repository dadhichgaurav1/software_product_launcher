/* Software Product Launcher — web UI logic (vanilla JS, same-origin API). */
const API = ""; // same origin as the FastAPI server
const $ = (id) => document.getElementById(id);

const state = {
  product: null,
  sites: [],
  selected: new Set(),
  answerSets: [],
  chat: [],
};

// ---- helpers --------------------------------------------------------------
async function api(path, opts) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const hostname = (u) => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return ""; } };

// ---- boot -----------------------------------------------------------------
async function boot() {
  try {
    const h = await api("/api/health");
    $("provider-badge").textContent = `LLM: ${h.provider} · ${h.sites} sites`;
    $("health-foot").textContent = `provider=${h.provider} · model=${h.model}`;
  } catch (e) {
    $("provider-badge").textContent = "backend offline";
  }
  await loadRecent();
}

async function loadRecent() {
  try {
    const { products } = await api("/api/products");
    if (!products.length) { $("recent").innerHTML = ""; return; }
    $("recent").innerHTML = "Recent: " + products.map((p) =>
      `<a href="#" data-url="${esc(p.url)}" class="chip">${esc(p.name || p.url)} v${p.version}</a>`).join(" ");
    $("recent").querySelectorAll("a").forEach((a) =>
      a.addEventListener("click", (e) => { e.preventDefault(); $("url").value = a.dataset.url; doScan(false); }));
  } catch (_) {}
}

// ---- step 1: scan ---------------------------------------------------------
async function doScan(forceFromBtn) {
  const url = $("url").value.trim();
  if (!url) { setStatus("scan-status", "Enter a product URL first.", "err"); return; }
  const force = forceFromBtn !== undefined ? forceFromBtn : $("force").checked;
  setBusy("scan-btn", true);
  setStatus("scan-status", force ? "Re-scanning (force refresh)…" : "Scanning & understanding the product…");
  try {
    const product = await api("/api/scan", { method: "POST", body: JSON.stringify({ url, force }) });
    state.product = product;
    renderProduct(product);
    setStatus("scan-status", `Understood "${product.name}" — stored as JSON v${product.version}.`, "ok");
    await ensureSites();
    $("sites-card").classList.remove("hidden");
    await loadRecent();
    await restoreDrafts();
  } catch (e) {
    setStatus("scan-status", "Scan failed: " + e.message, "err");
  } finally {
    setBusy("scan-btn", false);
  }
}

function renderProduct(p) {
  $("product-card").classList.remove("hidden");
  $("product-version").textContent = "JSON v" + p.version;
  $("product-source").textContent = "via " + p.analyzed_by;
  const social = Object.entries(p.social_links || {})
    .map(([k, v]) => `<a class="chip" href="${esc(v)}" target="_blank">${esc(k)}</a>`).join(" ");
  $("product-main").innerHTML = `
    <h3>${esc(p.name)}</h3>
    <p class="tagline">${esc(p.tagline)}</p>
    <dl class="kv">
      <dt>Positioning</dt><dd>${esc(p.positioning)}</dd>
      <dt>ICP</dt><dd>${esc(p.icp)}</dd>
      <dt>Target group</dt><dd>${esc(p.target_group)}</dd>
      <dt>Pricing</dt><dd>${esc(p.pricing) || "—"}</dd>
      <dt>Categories</dt><dd><div class="chips">${(p.categories || []).map((c) => `<span class="chip">${esc(c)}</span>`).join("")}</div></dd>
      <dt>Tags</dt><dd><div class="chips">${(p.topics_tags || []).map((c) => `<span class="chip">${esc(c)}</span>`).join("")}</div></dd>
      <dt>Description</dt><dd>${esc(p.description_long || p.description_short)}</dd>
      ${p.features?.length ? `<dt>Features</dt><dd><ul class="feature-list">${p.features.map((f) => `<li>${esc(f.title)}</li>`).join("")}</ul></dd>` : ""}
      ${p.benefits?.length ? `<dt>Benefits</dt><dd><ul class="benefit-list">${p.benefits.map((b) => `<li>${esc(b)}</li>`).join("")}</ul></dd>` : ""}
      ${social ? `<dt>Social</dt><dd><div class="chips">${social}</div></dd>` : ""}
    </dl>`;
  renderAssets(p.assets || {});
}

function renderAssets(a) {
  const box = (asset, label) => asset ?
    `<div class="asset-box"><img src="${esc(asset.local_path ? "/assets/" + asset.local_path.split("/").pop() : asset.url)}"
       alt="${esc(label)}" onerror="this.style.display='none'"/><div class="label">${esc(label)}</div></div>` : "";
  let html = box(a.logo, "Logo") + box(a.favicon, "Favicon");
  if (a.images?.length) html += `<div class="asset-count">${a.images.length} image asset(s)</div>` + box(a.images[0], "Image");
  if (a.videos?.length) html += `<div class="asset-count">🎬 ${a.videos.length} video asset(s)</div>`;
  $("assets").innerHTML = html || `<div class="asset-count">No assets detected.</div>`;
}

// ---- step 3: sites --------------------------------------------------------
async function ensureSites() {
  if (state.sites.length) return;
  const { sites } = await api("/api/sites");
  state.sites = sites;
  renderSites();
}

function renderSites() {
  const filter = ($("site-filter").value || "").toLowerCase();
  const grid = $("sites-grid");
  grid.innerHTML = "";
  state.sites
    .filter((s) => !filter || s.name.toLowerCase().includes(filter) || (s.tags || []).join(" ").includes(filter))
    .forEach((s) => {
      const el = document.createElement("div");
      el.className = "site" + (state.selected.has(s.id) ? " selected" : "");
      el.innerHTML = `
        <div class="name">${esc(s.name)} <input type="checkbox" ${state.selected.has(s.id) ? "checked" : ""}/></div>
        <div class="desc">${esc(s.description)}</div>
        <div class="meta">
          <span class="tag fee">${esc(s.fee)}</span>
          <span class="tag auth">${esc(s.auth_type)}</span>
          <span class="tag">${s.question_count} fields</span>
          ${s.do_follow ? '<span class="tag">do-follow</span>' : ""}
        </div>`;
      el.addEventListener("click", (e) => {
        if (e.target.tagName !== "INPUT") el.querySelector("input").checked = !el.querySelector("input").checked;
        toggleSite(s.id, el.querySelector("input").checked, el);
      });
      grid.appendChild(el);
    });
}

function toggleSite(id, on, el) {
  if (on) state.selected.add(id); else state.selected.delete(id);
  el.classList.toggle("selected", on);
  $("selected-count").textContent = `${state.selected.size} selected`;
}

// ---- step 4: generate, edit & chat ---------------------------------------
async function doGenerate() {
  if (!state.product) { setStatus("generate-status", "Scan a product first.", "err"); return; }
  if (!state.selected.size) { setStatus("generate-status", "Select at least one launch site.", "err"); return; }
  setBusy("generate-btn", true);
  setStatus("generate-status", `Generating best-practice answers for ${state.selected.size} site(s)…`);
  try {
    const body = JSON.stringify({ url: state.product.url, site_ids: [...state.selected] });
    const { answer_sets } = await api("/api/generate", { method: "POST", body });
    state.answerSets = answer_sets;
    await loadChat();
    showReview();
    setStatus("generate-status", `Generated ${answer_sets.length} submission draft(s). Edit inline or use the agent chat.`, "ok");
    $("answers-card").scrollIntoView({ behavior: "smooth" });
  } catch (e) {
    setStatus("generate-status", "Generation failed: " + e.message, "err");
  } finally {
    setBusy("generate-btn", false);
  }
}

function showReview() {
  $("answers-card").classList.remove("hidden");
  renderAnswers();
  populateScope();
  renderChat();
}

function setOf(id) { return state.answerSets.find((s) => s.site_id === id); }

function renderAnswers() {
  const wrap = $("answers");
  wrap.innerHTML = "";
  state.answerSets.forEach((set, idx) => {
    const site = state.sites.find((s) => s.id === set.site_id) || {};
    const filled = set.answers.filter((a) => a.value).length;
    const div = document.createElement("div");
    div.className = "answer-site" + (idx === 0 ? " open" : "");
    div.innerHTML = `
      <div class="answer-head">
        <h3>${esc(set.site_name)}</h3>
        <div class="right">
          <span class="pill">${filled}/${set.answers.length} filled</span>
          <span class="pill alt">${esc(set.auth.type)} sign-in</span>
          <button class="copy-btn ghost">Copy all</button>
        </div>
      </div>
      <div class="answer-body">
        ${set.notes?.length ? `<div class="notes"><strong>Before you submit:</strong><ul>${set.notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul></div>` : ""}
        ${set.answers.map((a) => answerRow(set.site_id, a)).join("")}
        ${site.url ? `<p class="hint">Open <a href="${esc(site.url)}" target="_blank">${esc(site.name)}</a>, then use the extension's “Fill This Page”.</p>` : ""}
      </div>`;
    div.querySelector(".answer-head").addEventListener("click", (e) => {
      if (e.target.classList.contains("copy-btn")) return;
      div.classList.toggle("open");
    });
    div.querySelector(".copy-btn").addEventListener("click", () => copyAll(set, div));
    div.querySelectorAll("textarea.a-edit").forEach(wireEditor);
    wrap.appendChild(div);
  });
}

function answerRow(siteId, a) {
  const over = a.max_length && a.value.length > a.max_length;
  const counter = a.max_length
    ? `<span class="counter ${over ? "over" : ""}" data-counter>${a.value.length}/${a.max_length}</span>` : "";
  return `
    <div class="qa" data-site="${esc(siteId)}" data-q="${esc(a.question_id)}">
      <div class="q">${esc(a.label)}
        ${a.source === "best_practice" ? '<span class="badge">best-practice</span>' : ""}
        ${a.source === "llm" ? '<span class="badge edited">revised</span>' : ""}
        ${a.edited ? '<span class="badge edited">edited</span>' : ""}
        ${a.truncated ? '<span class="badge trunc">trimmed to fit</span>' : ""}
        ${a.type === "file" ? '<span class="badge">file</span>' : ""}
        ${counter}
      </div>
      <textarea class="a-edit" rows="1" data-site="${esc(siteId)}" data-q="${esc(a.question_id)}"
        data-max="${a.max_length || ""}" placeholder="— fill manually —">${esc(a.value)}</textarea>
    </div>`;
}

function wireEditor(ta) {
  const autosize = () => { ta.style.height = "auto"; ta.style.height = ta.scrollHeight + "px"; };
  setTimeout(autosize, 0);
  ta.addEventListener("input", () => {
    autosize();
    const max = parseInt(ta.dataset.max, 10);
    const c = ta.closest(".qa").querySelector("[data-counter]");
    if (c && max) { c.textContent = `${ta.value.length}/${max}`; c.classList.toggle("over", ta.value.length > max); }
  });
  ta.addEventListener("change", () => saveEdit(ta.dataset.site, ta.dataset.q, ta.value, ta));
}

async function saveEdit(siteId, qId, value, ta) {
  ta.classList.add("saving");
  try {
    const aset = await api("/api/draft/answer", {
      method: "PATCH",
      body: JSON.stringify({ url: state.product.url, site_id: siteId, question_id: qId, value }),
    });
    const i = state.answerSets.findIndex((s) => s.site_id === siteId);
    if (i >= 0) state.answerSets[i] = aset;
    ta.classList.remove("saving"); ta.classList.add("saved");
    setTimeout(() => ta.classList.remove("saved"), 1200);
    const q = ta.closest(".qa").querySelector(".q");
    if (q && !q.querySelector(".badge.edited")) q.insertAdjacentHTML("beforeend", ' <span class="badge edited">edited</span>');
  } catch (e) {
    ta.classList.remove("saving");
    setStatus("generate-status", "Save failed: " + e.message, "err");
  }
}

function copyAll(set, div) {
  const text = set.answers.filter((a) => a.value).map((a) => `${a.label}:\n${a.value}`).join("\n\n");
  navigator.clipboard.writeText(text);
  const btn = div.querySelector(".copy-btn");
  btn.textContent = "Copied!";
  setTimeout(() => (btn.textContent = "Copy all"), 1500);
}

// ---- agent chat -----------------------------------------------------------
const SUGGESTIONS = [
  "Shorten the taglines", "Make it more professional", "Add an emoji",
  "Lead with the benefit", "Add keywords for SEO",
];

function populateScope() {
  const sel = $("chat-scope");
  sel.innerHTML = `<option value="">All ${state.answerSets.length} drafts</option>` +
    state.answerSets.map((s) => `<option value="${esc(s.site_id)}">${esc(s.site_name)}</option>`).join("");
  const sug = $("chat-suggestions");
  sug.innerHTML = SUGGESTIONS.map((s) => `<span class="sug">${esc(s)}</span>`).join("");
  sug.querySelectorAll(".sug").forEach((el) =>
    el.addEventListener("click", () => { $("chat-text").value = el.textContent; sendChat(); }));
}

function renderChat() {
  const log = $("chat-log");
  if (!state.chat.length) {
    log.innerHTML = `<div class="chat-empty">Ask me to refine the drafts — e.g. “shorten the
      taglines”, “make it more professional”, “lead with the benefit”, or set a specific
      field: “set the demo URL to https://…”.</div>`;
    return;
  }
  log.innerHTML = state.chat.map((m) => `
    <div class="msg ${m.role === "user" ? "user" : "assistant"}">${esc(m.content)}
      ${m.scope ? `<span class="scope-tag">↳ ${esc(m.scope)}</span>` : ""}</div>`).join("");
  log.scrollTop = log.scrollHeight;
}

async function loadChat() {
  try { state.chat = (await api(`/api/chat/history?url=${encodeURIComponent(state.product.url)}`)).chat || []; }
  catch (_) { state.chat = []; }
}

async function sendChat() {
  const text = $("chat-text").value.trim();
  if (!text || !state.product) return;
  const scope = $("chat-scope").value;
  const site_ids = scope ? [scope] : state.answerSets.map((s) => s.site_id);
  $("chat-text").value = "";
  state.chat.push({ role: "user", content: text, scope: scope ? (setOf(scope)?.site_name || scope) : "all drafts" });
  renderChat();
  const log = $("chat-log");
  log.insertAdjacentHTML("beforeend", '<div class="msg assistant chat-thinking" id="thinking">Thinking…</div>');
  log.scrollTop = log.scrollHeight;
  setBusy("chat-send", true);
  try {
    const res = await api("/api/chat", {
      method: "POST", body: JSON.stringify({ url: state.product.url, instruction: text, site_ids }),
    });
    // merge updated sets back into state
    (res.answer_sets || []).forEach((aset) => {
      const i = state.answerSets.findIndex((s) => s.site_id === aset.site_id);
      if (i >= 0) state.answerSets[i] = aset; else state.answerSets.push(aset);
    });
    state.chat = res.chat || state.chat;
    renderAnswers();
    renderChat();
  } catch (e) {
    document.getElementById("thinking")?.remove();
    state.chat.push({ role: "assistant", content: "Sorry — that failed: " + e.message });
    renderChat();
  } finally {
    setBusy("chat-send", false);
  }
}

async function restoreDrafts() {
  try {
    const bundle = await api(`/api/drafts?url=${encodeURIComponent(state.product.url)}`);
    const sets = Object.values(bundle.answer_sets || {});
    if (!sets.length) return;
    state.answerSets = sets;
    state.chat = bundle.chat || [];
    sets.forEach((s) => state.selected.add(s.site_id));
    renderSites();
    $("selected-count").textContent = `${state.selected.size} selected`;
    showReview();
    setStatus("generate-status", `Restored ${sets.length} saved draft(s).`, "ok");
  } catch (_) {}
}

// ---- ui utils -------------------------------------------------------------
function setStatus(id, msg, cls) { const el = $(id); el.textContent = msg; el.className = "hint" + (cls ? " " + cls : ""); }
function setBusy(id, busy) { $(id).disabled = busy; }

// ---- wire up --------------------------------------------------------------
$("scan-btn").addEventListener("click", () => doScan());
$("url").addEventListener("keydown", (e) => { if (e.key === "Enter") doScan(); });
$("generate-btn").addEventListener("click", doGenerate);
$("site-filter").addEventListener("input", renderSites);
$("select-all").addEventListener("click", () => { state.sites.forEach((s) => state.selected.add(s.id)); renderSites(); $("selected-count").textContent = `${state.selected.size} selected`; });
$("select-none").addEventListener("click", () => { state.selected.clear(); renderSites(); $("selected-count").textContent = "0 selected"; });
$("chat-form").addEventListener("submit", (e) => { e.preventDefault(); sendChat(); });
$("chat-text").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); sendChat(); }
});
boot();
