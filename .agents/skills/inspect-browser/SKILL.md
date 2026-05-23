---
name: inspect-browser
description: >
  Browser inspection skill using Playwright. Use when debugging client-side errors,
  network failures, hydration mismatches, or visual regressions. Captures console
  errors (source-mapped), failed network requests, a screenshot, and page HTML in one
  pass. Run capture.mjs with a URL; output is structured JSON + screenshot.
  Use before asking "what's the client-side error?" — the agent reads it directly.
---

# Browser Inspection with Playwright

## Setup

```bash
# One-time install (from project root or global)
npm install -g playwright
npx playwright install chromium
```

## Usage

```bash
# Capture console errors, network failures, HTML, and screenshot
node capture.mjs https://localhost:3000/path

# With auth cookie (paste from DevTools → Application → Cookies)
AUTH_COOKIE="session=abc123; Path=/; HttpOnly" node capture.mjs https://localhost:3000/dashboard

# Output is written to .agent/browser-capture/ and summary printed to stdout
```

## What it captures

- `console-errors.json` — all `console.error` and `console.warn` messages
- `network-failures.json` — all requests with HTTP 4xx/5xx or network errors
- `screenshot.png` — full-page screenshot at time of capture
- `page.html` — full DOM HTML after hydration (differs from view-source for React/Remix/Next)
- `summary.json` — combined structured output for agent consumption

## Interpreting output

**Console errors** contain the source-mapped stack if `--enable-source-maps` is set server-side
and source maps are uploaded to Sentry / OpenObserve.

**Network failures** show the request URL, status, and response body — useful for identifying
which API call is causing a client-side blank screen or loading spinner.

**page.html vs view-source** — if they differ, there is a hydration issue. Diff them:

```bash
curl http://localhost:3000/path > .agent/browser-capture/server.html
diff .agent/browser-capture/server.html .agent/browser-capture/page.html
```

## When to use this vs Chrome DevTools MCP

- **This skill** — fast, headless, one-shot capture; good for CI and agent loops
- **Chrome DevTools MCP** (`chrome-devtools-mcp`) — interactive; agent can navigate, click, fill
  forms, and read live console in a connected browser session (Chrome 146+)
