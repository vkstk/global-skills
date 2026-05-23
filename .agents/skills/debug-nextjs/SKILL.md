---
name: debug-nextjs
description: >
  Next.js-specific debugging skill. Use when diagnosing hydration mismatches, missing
  OpenTelemetry spans in App Router or Pages Router, slow fetch() calls between Next.js
  and downstream APIs, Edge runtime tracing issues, or SSR/client rendering divergence.
  Covers @vercel/otel, instrumentation.ts patterns, undici tracing, and the hydration
  diff workflow.
---

# Debugging Next.js

## 1 — OTel bootstrap (App Router)

Next.js supports `instrumentation.ts` at the project root (or `src/instrumentation.ts`).

```ts
// instrumentation.ts — loaded automatically by Next.js for both Node and Edge
export async function register() {
  if (process.env.NEXT_RUNTIME === 'nodejs') {
    await import('./instrumentation.node');
  }
  if (process.env.NEXT_RUNTIME === 'edge') {
    const { registerEdge } = await import('./instrumentation.edge');
    registerEdge();
  }
}
```

```ts
// instrumentation.node.ts — Node.js runtime only
import { NodeSDK } from '@opentelemetry/sdk-node';
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { UndiciInstrumentation } from '@opentelemetry/instrumentation-undici';

const sdk = new NodeSDK({
  traceExporter: new OTLPTraceExporter({
    url: process.env.OTEL_EXPORTER_OTLP_ENDPOINT ?? 'http://localhost:4318/v1/traces',
  }),
  instrumentations: [
    getNodeAutoInstrumentations(),
    new UndiciInstrumentation(),   // captures fetch() calls to downstream APIs
  ],
});
sdk.start();
```

```ts
// instrumentation.edge.ts — Edge runtime (Vercel / Cloudflare Workers)
import { registerOTel } from '@vercel/otel';

export function registerEdge() {
  registerOTel({ serviceName: process.env.OTEL_SERVICE_NAME ?? 'nextjs-edge' });
}
```

Enable in `next.config.ts`:
```ts
const nextConfig = {
  experimental: { instrumentationHook: true },
};
```

## 2 — Capturing fetch() spans between Next.js and APIs

`@opentelemetry/instrumentation-undici` patches the global `fetch` used in the Node.js runtime.
Without it, calls from Server Components and Route Handlers to downstream services produce no spans.

Verify it works:
```bash
NODE_OPTIONS='--enable-source-maps' pnpm dev
# then check OpenObserve for spans with operation_name LIKE 'HTTP GET%'
```

## 3 — Hydration mismatch debugging

**Rule: always reproduce in a production build.** Dev mode suppresses timing issues.

```bash
pnpm build && pnpm start
```

**Deterministic workflow:**

1. View-source the page HTML (`curl http://localhost:3000/path > server.html`).
2. In DevTools console: `copy(document.body.innerHTML)` → paste to `client.html`.
3. Diff the two files (diffchecker.com or `diff server.html client.html`).
4. Binary-search the component tree: replace half the tree with `<div>placeholder</div>`, confirm
   which half contains the mismatch, recurse.

**Common causes and fixes:**

| Cause | Fix |
|---|---|
| `new Date().toLocaleString()` | Parse in Server Component / loader; pass formatted string as prop |
| `Math.random()` or `Date.now()` in render | Use `useId()` for stable IDs; move random to `useEffect` |
| `typeof window !== 'undefined'` branch in render body | `dynamic(() => ..., { ssr: false })` or `useEffect` |
| Browser extension injecting DOM nodes | Test in Incognito / clean profile |
| CDN HTML minification (Cloudflare Auto Minify) | Disable Auto Minify for HTML |
| CSS-in-JS double-render (styled-components, emotion) | Use `ServerStyleSheet` pattern or switch to CSS Modules |

**`suppressHydrationWarning`** is a leaf-node escape hatch only. Use for timestamps/user-specific
content that can't be SSR'd. Do not apply to layout elements.

```tsx
// correct usage — leaf node with inherently client-only content
<time suppressHydrationWarning>{new Date().toLocaleTimeString()}</time>
```

## 4 — Client-only components (stable pattern)

```tsx
// For content that must differ between server and client
import dynamic from 'next/dynamic';

const ClientOnlyChart = dynamic(() => import('@/components/Chart'), { ssr: false });
```

For stable IDs (avoid `Math.random()`):
```tsx
import { useId } from 'react';
const id = useId(); // stable across server and client
```

## 5 — Source maps in production traces

```bash
# .env.local
NODE_OPTIONS='--enable-source-maps'
```

Upload source maps to Sentry in CI:
```bash
npx @sentry/cli sourcemaps inject .next
npx @sentry/cli sourcemaps upload .next --org=<org> --project=<project>
```

Or use `@sentry/nextjs` which handles this automatically via `withSentryConfig` in `next.config.ts`.

## 6 — OTel pipeline verification

When "spans don't appear in OpenObserve":

```bash
# Step 1 — verify SDK emits spans at all
# Add ConsoleSpanExporter temporarily to instrumentation.node.ts
import { ConsoleSpanExporter } from '@opentelemetry/sdk-trace-base';
# If you see JSON in server stdout, the app is fine.

# Step 2 — verify Collector receives them
curl http://localhost:8888/metrics | grep otelcol_receiver_accepted_spans
# non-zero = Collector is getting them

# Step 3 — check port/protocol
# 4317 = gRPC, 4318 = HTTP/protobuf
# OTLP HTTP exporter needs url ending in /v1/traces
# gRPC exporter endpoint should NOT have a path
```

## 7 — Common Next.js OTel gotchas

| Symptom | Likely cause | Fix |
|---|---|
| Spans missing for Server Components | `instrumentation.ts` not found | Check `experimental.instrumentationHook: true` and file location |
| Edge spans missing | `@vercel/otel` not called | Add `instrumentation.edge.ts` with `registerEdge()` |
| `fetch()` to API not traced | `UndiciInstrumentation` absent | Add to `instrumentations` in `instrumentation.node.ts` |
| Hydration warning in dev but not prod | Timing-dependent — dev masks it | Always test in `pnpm build && pnpm start` |
| `useId` mismatch | React < 18 | Upgrade or use a stable string constant |

## 8 — Stop-hook commands

```bash
pnpm typecheck    # tsc --noEmit
pnpm lint:json    # eslint . --format json
pnpm test         # vitest run --reporter=basic --no-watch
pnpm build        # catches RSC / bundling errors that tsc misses
```
