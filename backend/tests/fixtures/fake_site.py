"""A small fake multi-page product website + an offline fetcher.

Reused across scanner, analyzer, store and end-to-end tests so the whole
pipeline can run without any network access.
"""
from __future__ import annotations

from app.scanner.crawler import FetchResult

BASE = "https://taskpilot.ai"

PAGES = {
    BASE: """
    <html><head>
      <title>TaskPilot — AI task manager for developers</title>
      <meta name="description" content="TaskPilot is an AI task manager that helps
        developers and engineering teams automate their workflow and ship faster.">
      <meta property="og:site_name" content="TaskPilot">
      <meta property="og:description" content="AI task manager for developers.">
      <meta property="og:image" content="/img/og.png">
      <link rel="canonical" href="https://taskpilot.ai/">
      <link rel="icon" href="/favicon.ico">
    </head><body>
      <header><img src="/img/logo.svg" class="logo" alt="TaskPilot logo"></header>
      <h1>AI task manager for developers</h1>
      <p>TaskPilot uses AI to plan your sprints automatically so your team ships
         faster and saves time on manual planning. Built for engineering teams.</p>
      <h2>Features</h2>
      <ul>
        <li>Automated sprint planning powered by AI</li>
        <li>GitHub and GitLab API integration</li>
        <li>Smart prioritisation that reduces busywork</li>
      </ul>
      <video src="/media/demo.mp4"></video>
      <a href="/features">Features</a> <a href="/pricing">Pricing</a>
      <a href="https://twitter.com/taskpilot">Twitter</a>
      <a href="https://github.com/taskpilot">GitHub</a>
    </body></html>
    """,
    BASE + "/features": """
    <html><head><title>Features — TaskPilot</title>
      <meta name="description" content="Everything TaskPilot can do for your team."></head>
    <body>
      <h1>Features</h1>
      <ul>
        <li>One-click sprint automation</li>
        <li>AI standup summaries that save time every morning</li>
        <li>Slack and Linear integrations</li>
      </ul>
      <p>TaskPilot integrates with the tools developers already use, so you can
         automate status updates and reduce meetings effortlessly.</p>
      <img src="/img/screenshot1.png" alt="dashboard screenshot">
    </body></html>
    """,
    BASE + "/pricing": """
    <html><head><title>Pricing — TaskPilot</title>
      <meta name="description" content="Simple pricing. Free for open source."></head>
    <body>
      <h1>Pricing</h1>
      <p>TaskPilot is free forever for open source teams. Paid plans start at
         $12/month for private projects.</p>
    </body></html>
    """,
}


def fake_fetcher(url: str) -> FetchResult:
    """Offline fetcher: serves the fixture pages, 404 otherwise."""
    key = url.rstrip("/") if url.rstrip("/") in PAGES else url
    if key not in PAGES and url in PAGES:
        key = url
    # normalise trailing slash on base
    if key not in PAGES:
        for k in PAGES:
            if k.rstrip("/") == url.rstrip("/"):
                key = k
                break
    if key in PAGES:
        return FetchResult(url=key, status=200, html=PAGES[key], content_type="text/html")
    return FetchResult(url=url, status=404, html="", content_type="text/html")
