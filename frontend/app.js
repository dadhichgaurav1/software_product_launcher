/* Software Product Launcher — web UI logic (vanilla JS, same-origin API). */
const API = ""; // same origin as the FastAPI server
const $ = (id) => document.getElementById(id);

const state = {
  product: null,
  sites: [],
  selected: new Set(),
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

// ---- step 4: generate -----------------------------------------------------
async function doGenerate() {
  if (!state.product) { setStatus("generate-status", "Scan a product first.", "err"); return; }
  if (!state.selected.size) { setStatus("generate-status", "Select at least one launch site.", "err"); return; }
  setBusy("generate-btn", true);
  setStatus("generate-status", `Generating best-practice answers for ${state.selected.size} site(s)…`);
  try {
    const body = JSON.stringify({ url: state.product.url, site_ids: [...state.selected] });
    const { answer_sets } = await api("/api/generate", { method: "POST", body });
    renderAnswers(answer_sets);
    setStatus("generate-status", `Generated ${answer_sets.length} submission draft(s).`, "ok");
    $("answers-card").classList.remove("hidden");
    $("answers-card").scrollIntoView({ behavior: "smooth" });
  } catch (e) {
    setStatus("generate-status", "Generation failed: " + e.message, "err");
  } finally {
    setBusy("generate-btn", false);
  }
}

function renderAnswers(sets) {
  const wrap = $("answers");
  wrap.innerHTML = "";
  sets.forEach((set, idx) => {
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
        ${set.answers.map((a) => `
          <div class="qa">
            <div class="q">${esc(a.label)}
              ${a.source === "best_practice" ? '<span class="badge">best-practice</span>' : ""}
              ${a.truncated ? '<span class="badge trunc">trimmed to fit</span>' : ""}
              ${a.type === "file" ? '<span class="badge">file</span>' : ""}
            </div>
            <div class="a ${a.value ? "" : "empty"}">${a.value ? esc(a.value) : "— fill manually —"}</div>
          </div>`).join("")}
        ${site.url ? `<p class="hint">Open <a href="${esc(site.url)}" target="_blank">${esc(site.name)}</a>, then use the Chrome extension's “Fill This Page”.</p>` : ""}
      </div>`;
    div.querySelector(".answer-head").addEventListener("click", (e) => {
      if (e.target.classList.contains("copy-btn")) return;
      div.classList.toggle("open");
    });
    div.querySelector(".copy-btn").addEventListener("click", () => {
      const text = set.answers.filter((a) => a.value).map((a) => `${a.label}:\n${a.value}`).join("\n\n");
      navigator.clipboard.writeText(text);
      div.querySelector(".copy-btn").textContent = "Copied!";
      setTimeout(() => (div.querySelector(".copy-btn").textContent = "Copy all"), 1500);
    });
    wrap.appendChild(div);
  });
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
boot();
