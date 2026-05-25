---
name: debug-nodejs
description: >
  Node.js and TypeScript core debugging skill. Use when diagnosing crashes, memory leaks,
  CPU hotspots, event loop lag, remote/containerised process issues, or needing to attach
  a debugger to a running Node.js process. Covers the inspector protocol, clinic.js,
  heap profiling, diagnostic reports, source maps, and git bisect. Framework-agnostic —
  applies to NestJS, Remix, Next.js, and standalone Node apps equally.
---

# Debugging Node.js / TypeScript

## Forwood One (`ehs-ai-platform`) — ports

| What | Port |
| --- | --- |
| Web | **5173** |
| API | **4000** (devcontainer); **3000** only if `api/.env` `API_PORT=3000` outside compose |
| OTLP gRPC | **4317** (not 4318 unless using HTTP OTLP deliberately) |
| OpenObserve | **HTTPS** remote — no local `:8888` collector unless you run one |
| Inspector | **9229** |

Load test API: `autocannon -c 100 -d 30 http://localhost:4000/api/health` (adjust path).

## 1 — Debugger attach hierarchy (choose the right level)

| Situation | Approach |
|---|---|
| Local `pnpm dev` | VS Code Auto Attach — enable in settings, just run `pnpm dev` |
| Docker container | `node --inspect=0.0.0.0:9229`; map `127.0.0.1:9229:9229` |
| Already-running container (no restart) | `docker exec <container> kill -SIGUSR1 1` |
| Kubernetes pod | `kubectl exec <pod> -- kill -SIGUSR1 1` then `kubectl port-forward pod/<pod> 9229:9229` |
| Remote staging VM | `ssh -L 9229:127.0.0.1:9229 user@host` — **never** expose 9229 publicly (zero auth) |

**VS Code `launch.json` attach config:**

```json
{
  "type": "node",
  "request": "attach",
  "name": "Attach Node",
  "port": 9229,
  "address": "localhost",
  "remoteRoot": "/app",
  "localRoot": "${workspaceFolder}",
  "sourceMaps": true,
  "skipFiles": ["<node_internals>/**"]
}
```

## 2 — Conditional breakpoints and logpoints

Right-click the VS Code gutter:
- **Conditional breakpoint** — expression like `req.userId === 'abc123'`; only pauses when true.
- **Logpoint** — emits a message without stopping (`"userId: {req.userId}, path: {req.path}"`).
  Use instead of temporary `console.log` when you can't reproduce reliably — no heisenbugs.

## 3 — Performance profiling with clinic.js

Always start with `doctor` for categorical diagnosis, then drill down.

```bash
# Categorical diagnosis — CPU / I-O / memory / event loop
clinic doctor -- node server.js

# CPU hotspots — flame graph (wide horizontal bars = hot functions)
clinic flame -- node server.js

# Async waterfalls — identify long awaits
clinic bubbleprof -- node server.js

# Memory leaks — retained allocation blocks
clinic heapprofiler -- node server.js
```

Generate load while clinic is running:
```bash
autocannon -c 100 -d 30 http://localhost:4000/api/endpoint
```

## 4 — Memory leak hunting

**Development / staging — on-demand heap snapshot:**

```ts
// In app bootstrap — trigger via SIGUSR2
import * as v8 from 'v8';
process.on('SIGUSR2', () => {
  const filename = v8.writeHeapSnapshot();
  console.log(`Heap snapshot written to ${filename}`);
});
```

```bash
kill -SIGUSR2 <pid>
```

Load the `.heapsnapshot` file in Chrome DevTools → Memory tab. Diff two snapshots taken 10 minutes
apart — the delta shows retained objects.

**Continuous heap profiling (production-safe):**

```bash
node --heap-prof --heap-prof-interval=512000 dist/main.js
# writes .heapprofile on exit; load in Chrome DevTools → Memory → Sampling Profiles
```

## 5 — Event loop lag sentinel

Add this once in your app's bootstrap. Never remove it in production.

```ts
import { monitorEventLoopDelay } from 'perf_hooks';

const h = monitorEventLoopDelay({ resolution: 20 });
h.enable();
setInterval(() => {
  logger.info({ p99_ms: h.percentile(99) / 1e6 }, 'evloop:lag');
  h.reset();
}, 5_000);
```

Alert in OpenObserve when `p99_ms > 50`. Event loop lag above 50ms means synchronous work is
blocking I/O — look for `JSON.parse` on large payloads, `crypto.pbkdf2Sync`, or unbounded loops.

## 6 — Diagnostic reports

Emit a structured JSON report on crash or SIGUSR2:

```bash
node \
  --report-on-fatalerror \
  --report-on-signal \
  --report-signal=SIGUSR2 \
  dist/main.js
```

The report includes heap state, env vars, libuv handles, and a native stack. Ship to OpenObserve
as a structured log field (`report: JSON.parse(fs.readFileSync(filename))`).

## 7 — Source maps everywhere

```bash
# .env / docker-compose environment
NODE_OPTIONS='--enable-source-maps'
```

For compiled output (esbuild / swc / tsc), always emit source maps in dev:
```json
// tsconfig.json
{ "compilerOptions": { "sourceMap": true } }
```

Without `--enable-source-maps`, stack traces point at `.js` lines. With it, they point at `.ts`.

## 8 — git bisect for regressions

"When did this break?" → binary search with a test:

```bash
git bisect start
git bisect bad                  # current commit is broken
git bisect good v1.2.0          # last known good tag/commit

# Automate with a test or script
git bisect run pnpm test:e2e:focused
# Git will check out commits and run the test until the first bad commit is found
```

Stop with `git bisect reset`.

## 9 — TypeScript / compile-time guardrails

Encode these as ESLint rules so the agent catches them at edit time:

- No `any` — use `unknown` + narrowing; use Zod at IO boundaries.
- No `JSON.parse` without try/catch or Zod `safeParse`.
- No floating promises — always `await` or `.catch()`.
- No sequential `await` for independent work — use `Promise.all`.
- No `setTimeout` / `setInterval` without `clearTimeout` / `clearInterval` reference.

## 10 — OTel pipeline self-check (when spans vanish)

1. Add `ConsoleSpanExporter` temporarily → confirm spans exist in SDK.
2. If using a sidecar OTel Collector: `curl http://localhost:8888/metrics | grep otelcol_receiver_accepted_spans`. **Forwood One** exports gRPC straight to OpenObserve (HTTPS) — skip 8888 unless you run a collector locally.
3. Check `otelcol_exporter_sent_spans` vs `otelcol_exporter_send_failed_spans`.
4. Verify port: **4317 = gRPC**, **4318 = HTTP/protobuf** — mixing kills the pipeline silently.
5. Enable `debug` exporter in Collector config with `verbosity: detailed` to see every span.

Simulate load without touching app:
```bash
telemetrygen traces --otlp-endpoint localhost:4317 --rate 10 --duration 30s
```
