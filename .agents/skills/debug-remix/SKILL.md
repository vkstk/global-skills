---
name: debug-remix
description: >
  Remix-specific debugging skill. Use when diagnosing hydration mismatches, ErrorBoundary
  rendering without styles, loader errors, missing HydrateFallback, locale/timezone
  divergence between server and client, or client-side error capture setup.
  Covers the hydration diff workflow, Remix-specific gotchas, and @sentry/remix setup.
---

# Debugging Remix

## Forwood One (`ehs-ai-platform`) — ports

| What | Port / host |
| --- | --- |
| Web (browser) | **5173** — `https://<tenant>.dev.platform.forwoodsafety.com:5173` or `http://localhost:5173` |
| API (direct) | **4000** — `http://localhost:4000/api` (`API_BASE_URL` / `VITE_API_PORT`) |
| OTLP / OpenObserve | **`http://o2.central.forwoodsafety.com`** — `otel-investigate` skill; export: `web/.env` `OTEL_EXPORTER_OTLP_ENDPOINT`; `web/app/services/observability/otel.server.ts` |

Build for hydration repro: `pnpm --filter @forwood/ehs-web build && pnpm --filter @forwood/ehs-web start` (not generic `pnpm build` at repo root).

## 1 — Hydration mismatches

**Rule: always reproduce in a production build.** Remix dev mode masks timing issues.

```bash
pnpm --filter @forwood/ehs-web build && pnpm --filter @forwood/ehs-web start
```

**Deterministic workflow:**

1. `curl -k https://devtenant1.dev.platform.forwoodsafety.com:5173/path > server.html` (or `http://localhost:5173/path`) — server HTML.
2. In DevTools console: `copy(document.body.innerHTML)` — capture client HTML after hydration.
3. Diff the two (`diff server.html client.html` or diffchecker.com).
4. Binary-search the route component tree: replace halves with `<div>placeholder</div>` until the
   mismatching subtree is isolated.

**Common Remix-specific causes:**

| Cause | Fix |
|---|---|
| `new Date().toLocaleString()` in render | Format in loader; pass formatted string via `useLoaderData()` |
| Locale / timezone drift | Normalize in loader using `Intl.DateTimeFormat` with explicit locale |
| `Math.random()` for keys/IDs | Replace with deterministic ID from server data |
| `typeof window !== 'undefined'` in render | Wrap component in `<ClientOnly>` from `remix-utils` |
| Browser extension DOM injection | Reproduce in Incognito |

## 2 — ErrorBoundary renders without styles (loader-thrown responses)

Remix bug: when a loader throws a `Response`, the `ErrorBoundary` can render without CSS.
Tracked in remix-run/remix issues #8764 and #9610.

**Workaround: add `HydrateFallback` to every route that has an ErrorBoundary.**

```tsx
// routes/dashboard.tsx
export function HydrateFallback() {
  return <div>Loading...</div>;
}

export function ErrorBoundary() {
  const error = useRouteError();
  return (
    <div className="error-page">
      {isRouteErrorResponse(error)
        ? <h1>{error.status} {error.statusText}</h1>
        : <h1>Unexpected Error</h1>}
    </div>
  );
}
```

## 3 — Client-only content

```tsx
import { ClientOnly } from 'remix-utils/client-only';

export default function Dashboard() {
  return (
    <div>
      <ServerChart data={data} />
      <ClientOnly fallback={<div>Loading chart...</div>}>
        {() => <InteractiveChart data={data} />}
      </ClientOnly>
    </div>
  );
}
```

## 4 — Locale / timezone normalization in loaders

Move all date formatting to the loader so server and client agree:

```ts
// routes/orders.tsx
export async function loader({ request }: LoaderFunctionArgs) {
  const orders = await db.order.findMany();
  return {
    orders: orders.map((o) => ({
      ...o,
      createdAtFormatted: new Intl.DateTimeFormat('en-AU', {
        timeZone: 'Australia/Sydney',
        dateStyle: 'medium',
      }).format(o.createdAt),
    })),
  };
}
```

Never call `toLocaleString()` / `toLocaleDateString()` in the component body.

## 5 — Error capture with source-mapped stacks

```bash
pnpm add @sentry/remix
```

```ts
// entry.server.tsx
import * as Sentry from '@sentry/remix';

Sentry.init({
  dsn: process.env.SENTRY_DSN,
  tracesSampleRate: 1.0,
});

export const handleError = Sentry.wrapRemixHandleError;
```

```ts
// entry.client.tsx
import * as Sentry from '@sentry/remix';
import { useLocation, useMatches } from '@remix-run/react';

Sentry.init({
  dsn: process.env.SENTRY_DSN,
  integrations: [
    Sentry.browserTracingIntegration({
      useEffect, useLocation, useMatches,
    }),
  ],
});
```

Upload source maps in CI:
```bash
npx @sentry/cli sourcemaps inject build/
npx @sentry/cli sourcemaps upload build/ --org=<org> --project=<project>
```

## 6 — Loader error patterns

```ts
// Throw typed responses — Remix catches and renders ErrorBoundary
export async function loader({ params }: LoaderFunctionArgs) {
  const item = await db.item.findUnique({ where: { id: params.id } });
  if (!item) throw new Response('Not Found', { status: 404 });
  return json(item);
}

// Catch in ErrorBoundary
export function ErrorBoundary() {
  const error = useRouteError();
  if (isRouteErrorResponse(error) && error.status === 404) {
    return <NotFoundPage />;
  }
  throw error; // re-throw unexpected errors to parent boundary
}
```

## 7 — OTel for Remix (Node.js adapter)

Remix runs on a Node.js server. Wire OTel the same way as a NestJS/Express app — via `instrumentation.ts` loaded with `-r`:

```ts
// instrumentation.ts (same as Node.js pattern)
import { NodeSDK } from '@opentelemetry/sdk-node';
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';
import { PinoInstrumentation } from '@opentelemetry/instrumentation-pino';

const sdk = new NodeSDK({
  instrumentations: [getNodeAutoInstrumentations(), new PinoInstrumentation()],
});
sdk.start();
```

Start server:
```bash
node -r ./instrumentation.js ./build/server/index.js
```

## 8 — Stop-hook commands

```bash
pnpm --filter @forwood/ehs-web typecheck
pnpm --filter @forwood/ehs-web test -- <focused-test>
pnpm --filter @forwood/ehs-web build   # catches route/loader issues tsc misses
```

## 9 — Remix-specific gotchas

| Symptom | Likely cause | Fix |
|---|---|
| ErrorBoundary missing styles | Loader throws Response | Add `HydrateFallback` export |
| Hydration warning only in prod | Locale/timezone drift | Normalize in loader |
| Client-side import of Node module | Missing `"browser"` field or wrong import | Use `ClientOnly` wrapper |
| Loader data not typed | Missing `typeof loader` inference | Use `useLoaderData<typeof loader>()` |
| Double data fetch | `useFetcher` vs `useLoaderData` confusion | `useLoaderData` is for route data; `useFetcher` for imperative fetches |
