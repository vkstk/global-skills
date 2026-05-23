#!/usr/bin/env node
// capture.mjs — Headless browser capture for debugging
// Captures: console errors, network failures, screenshot, post-hydration HTML
//
// Usage:
//   node capture.mjs <url>
//   AUTH_COOKIE="session=abc123" node capture.mjs <url>
//
// Output: .agent/browser-capture/ (created if absent)

import { chromium } from 'playwright';
import { writeFileSync, mkdirSync } from 'fs';
import { join } from 'path';

const url = process.argv[2];
if (!url) {
  console.error('Usage: node capture.mjs <url>');
  process.exit(1);
}

const outDir = '.agent/browser-capture';
mkdirSync(outDir, { recursive: true });

const consoleErrors = [];
const networkFailures = [];

const browser = await chromium.launch({ headless: true });

const context = await browser.newContext({
  ignoreHTTPSErrors: true,
  // Inject an auth cookie if provided via env var
  ...(process.env.AUTH_COOKIE
    ? {
        storageState: {
          cookies: parseCookieString(process.env.AUTH_COOKIE, new URL(url).hostname),
          origins: [],
        },
      }
    : {}),
});

const page = await context.newPage();

// Capture console errors and warnings
page.on('console', (msg) => {
  if (msg.type() === 'error' || msg.type() === 'warning') {
    consoleErrors.push({
      type: msg.type(),
      text: msg.text(),
      location: msg.location(),
      args: msg.args().map((a) => a.toString()),
    });
  }
});

// Capture network failures (4xx/5xx and aborted)
page.on('requestfailed', (req) => {
  networkFailures.push({
    url: req.url(),
    method: req.method(),
    failure: req.failure()?.errorText ?? 'unknown',
  });
});

page.on('response', async (res) => {
  if (res.status() >= 400) {
    let body = '';
    try {
      body = await res.text();
    } catch {
      body = '<unreadable>';
    }
    networkFailures.push({
      url: res.url(),
      method: res.request().method(),
      status: res.status(),
      body: body.slice(0, 500),
    });
  }
});

// Navigate and wait for network to settle
await page.goto(url, { waitUntil: 'networkidle', timeout: 30_000 });

// Capture post-hydration HTML
const html = await page.content();

// Full-page screenshot
await page.screenshot({ path: join(outDir, 'screenshot.png'), fullPage: true });

await browser.close();

// Write outputs
writeFileSync(join(outDir, 'console-errors.json'), JSON.stringify(consoleErrors, null, 2));
writeFileSync(join(outDir, 'network-failures.json'), JSON.stringify(networkFailures, null, 2));
writeFileSync(join(outDir, 'page.html'), html);

const summary = {
  url,
  capturedAt: new Date().toISOString(),
  consoleErrorCount: consoleErrors.length,
  networkFailureCount: networkFailures.length,
  consoleErrors,
  networkFailures,
};
writeFileSync(join(outDir, 'summary.json'), JSON.stringify(summary, null, 2));

// Print summary to stdout for agent consumption
console.log(JSON.stringify(summary, null, 2));

// ---- helpers ----

/**
 * Parse a semicolon-delimited cookie string into Playwright cookie objects.
 * e.g. "session=abc123; Path=/; HttpOnly"
 */
function parseCookieString(cookieStr, domain) {
  const parts = cookieStr.split(';').map((s) => s.trim());
  const [nameValue, ...attributes] = parts;
  const eqIdx = nameValue.indexOf('=');
  const name = nameValue.slice(0, eqIdx).trim();
  const value = nameValue.slice(eqIdx + 1).trim();

  const attrMap = Object.fromEntries(
    attributes.map((a) => {
      const i = a.indexOf('=');
      return i >= 0 ? [a.slice(0, i).trim().toLowerCase(), a.slice(i + 1).trim()] : [a.toLowerCase(), true];
    })
  );

  return [
    {
      name,
      value,
      domain,
      path: attrMap.path ?? '/',
      httpOnly: 'httponly' in attrMap,
      secure: 'secure' in attrMap,
      sameSite: attrMap.samesite ?? 'Lax',
    },
  ];
}
