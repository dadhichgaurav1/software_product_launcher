# Use-Case Description — Software Product Launcher

This describes the agent's use case so Synap can generate an optimal memory
architecture. It is filled to match the **actual implementation** in this repo
(`backend/app/memory/`), so the generated architecture lines up with how the code
ingests and recalls memory.

## Agent Objective

The **Software Product Launcher** is an agentic system that takes the URL of a
software product, understands it, and prepares best-practice submissions across
~20 launch directories (BetaList, DevHunt, Show HN, Uneed, Peerlist, SaaSHub,
AlternativeTo, …) — leaving each form filled and ready for the user to review and
submit. It scans the product site, extracts a structured understanding
(positioning, ICP, target group, categories, features, benefits, pricing,
assets), generates per-platform answers that respect each field's length limit,
and fills the forms via a Chrome extension.

Synap's role is to make the launcher **stateful and compounding** rather than
one-shot. It remembers three things and recalls them to ground future work:
1. **The product** — its understanding and identity.
2. **The founder's voice/style preferences** — every inline edit and every
   agent-chat instruction (e.g. "always lead with the benefit", "say 'AI
   teammate', never 'AI tool'", "add one emoji", "keep it formal").
3. **Post-launch learnings** — after-action insights derived from each launch's
   measured outcome (upvotes, rank, signups, approval), per platform.

So a preference stated once is applied across all 20 sites and across future
launches, and each launch's result improves the next.

## Target Users

Software **founders, indie hackers, and product marketers** launching a product
across many directories. Technical level varies (engineers to non-technical
marketers). Usage is **repeat and longitudinal**: a user typically launches the
same product to many sites in one sitting, returns for incremental launches, and
may launch **multiple products** over time. They expect the agent to remember
their voice, their product, and what worked last time — without re-explaining.

They interact through three surfaces that share one backend session: a **web
page** (scan → review → select sites → review/refine answers → log outcomes), an
**agent chat** (iterate on drafts across sites), and a **Chrome extension** (fill
the forms). All three read/write the same per-product memory.

## Task Examples

- **User**: *(enters a product URL and clicks Scan)*
  **Agent**: Crawls the site, extracts the structured understanding, stores it,
  and **remembers the product** (name, tagline, positioning, ICP, categories,
  benefits) so later steps and future launches are grounded in it.

- **User**: "Make all the taglines lead with the time-saving benefit, and never
  call it an 'AI tool' — it's an 'AI teammate'."
  **Agent**: Revises the drafts across the selected sites **and remembers this as
  a durable style preference**, so every future field generation for this product
  applies it automatically (recall injects it into the generation prompt).

- **User**: *(edits the DevHunt tagline inline to a punchier version)*
  **Agent**: Saves the edit and **remembers it as a preference/episode**; the
  founder's revised phrasing informs future generations rather than being
  overwritten.

- **User**: "DevHunt: we got featured, #3 of the day, 150 upvotes, but only 4
  signups." *(logs an outcome)*
  **Agent**: Runs after-action reasoning to derive 1–3 **learnings** (e.g.
  "benefit-led taglines performed well on DevHunt; upvotes didn't convert —
  strengthen the website's first-line hook"), **remembers** them, and **feeds
  them into the best-practices** that ground the next launch on that platform.

- **User**: *(comes back weeks later to launch a new feature / new product)*
  **Agent**: On generation, **recalls** the founder's voice preferences and the
  relevant per-platform learnings and applies them from the first draft —
  resolving "the product" / its name / "it" to the same entity across sessions.

## Behavioral Guidelines

**Do's**
- Remember and consistently apply the founder's **voice/style preferences**
  across all selected sites and across future launches.
- Resolve references to the product (its name, "the product", "it", "our app")
  to a **single entity**.
- Ground all generated copy in **facts from the product's own site**; respect
  each platform's exact field length limit.
- Keep memory **isolated per product and per account** (no cross-leakage).
- Support **deletion** — when a product is deleted, its memories should be
  deletable too (the app already cascade-deletes its drafts + launch book).
- Apply **temporal decay / conscious forgetting** to platform learnings: launch
  directories change their algorithms, so stale "what works" insights should fade
  and newer, contradicting outcomes should win.

**Don'ts**
- **Never auto-submit** a launch form — the product always leaves it ready for
  the user to review and submit manually.
- **Never store credentials, passwords, OAuth tokens, or payment data.** Sign-in
  is user-completed OAuth/CAPTCHA; the extension never handles credentials.
- **Never leak** one product's or one founder's memory into another's generation.
- Don't broadcast a **field-specific** instruction to unrelated fields (the chat
  already detects field focus; memory should preserve that specificity).

## Role Descriptions

- **Client** (the company operating the agent): **Maximem** — operates the
  Software Product Launcher.
- **Customer** (the tenant/account using the launcher): one per organization/
  account running launches. In code this is `customer_id`, default
  `software-product-launcher`; in a multi-tenant deployment, one Customer per
  founder's company / agency.
- **User** (the memory subject): **the product being launched**, keyed by a
  normalized hash of its URL (`user_id = product_key(url)`). We model the "user"
  as the product/founder identity (each product has one founder voice), so
  per-product memory holds the product facts **and** the founder's voice
  preferences and learnings for it.

> Recommended scoping nuance: **cross-product, same-platform launch wisdom**
> (e.g. "Tuesday launches outperform on DevHunt") is most useful at the
> **Customer** or **Client/global** scope so it benefits every product. Today the
> app also keeps a local global-learnings store for this; if Synap can carry
> global/Customer-scope learnings forward across products, we'd lean on that.

## Compliance & Data Sensitivity

- **Mostly public data.** The product understanding is extracted from the
  product's own public marketing site.
- **PII:** the maker/founder email may be inferred from the site — treat as
  sensitive and **deletable on request**. No other personal data is stored.
- **No secrets:** no credentials, tokens, or payment data are ever sent to
  memory (by design).
- **Right to erasure:** memories must be deletable per **product** and per
  **account** (GDPR-style). The app cascade-deletes a product's drafts + launch
  book on delete; memory deletion should follow.
- **Retention:** learnings should be **time-aware** — decay stale platform
  insights; let newer outcomes supersede older, contradicting ones.

## Memory Priorities

Mapped to Synap's memory types:

- **High priority**
  - **Preferences** — the founder's voice/style: tone, emoji usage, "lead with
    the benefit", preferred terminology ("AI teammate" not "AI tool"), formality.
    These are the single most valuable thing to remember and recall.
  - **Facts** — product positioning, ICP, target group, category, key
    features/benefits (the durable understanding).
  - **Post-launch learnings** — per-platform "what worked" (copy angle, category,
    timing) derived from outcomes.
- **Medium priority**
  - The specific **copy submitted per platform** (so learnings can attribute to
    it) and any learned platform-specific field constraints.
- **Temporal (important)**
  - **Outcomes over time** — rank/points/signups trajectory per launch; use
    temporal events + decay so stale platform learnings fade.
- **Low priority / candidate to disable**
  - **Emotion tracking** — not central to this use case (copy/marketing, not
    interpersonal support). Low priority; fine to disable if it reduces noise.

## Additional Context (technical — how the code uses Synap)

Implemented in `backend/app/memory/` against `maximem-synap` (async SDK), bridged
to the sync FastAPI backend via a dedicated event-loop thread with **bounded
timeouts** and **graceful degradation** (a NullMemory default; a slow/unavailable
backend never blocks a launch).

**Scoping (as implemented):**
- `customer_id` = the account/tenant (default `software-product-launcher`)
- `user_id` = `product_key(url)` (per-product / per-founder)
- `conversation_id` = `launch:<product_key>` (the product's launch thread, spanning
  scans, edits, chats, and launches over time)
- `metadata` carries `{kind, site_id}` where `kind ∈ {product, edit, instruction,
  outcome, learning}` and `site_id` is the launch directory.

**Ingest:**
- `sdk.conversation.record_message(role="user", content=…, user_id, customer_id,
  conversation_id, metadata)` for product understanding, inline edits, and chat
  style-instructions (episodes/preferences/facts).
- `sdk.memories.create(document=…, user_id, customer_id, metadata={kind, site_id})`
  for post-launch outcomes and derived learnings.

**Recall:**
- `sdk.fetch(conversation_id, user_id, customer_id, search_query=[query],
  max_results, include_conversation_context=True)` → `format_for_prompt()`, whose
  lines are injected into the generator's per-site best-practices that ground LLM
  copy generation. Recall query is roughly `"{site_name} {product_tagline}"`.

**Scale & shape:** ~20 launch directories per product; a founder may run multiple
products; recall is per-product within an account. We rely most on **entity
resolution** (one product entity), **preferences**, **facts**, and **temporal**
learnings. We do **not** use LangChain/LlamaIndex wrappers — we call the SDK
directly. Network egress to `synap-cloud-prod.maximem.ai` must be allowed for the
backend to reach Synap.
