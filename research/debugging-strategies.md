# Fast Debugging & Agent-Driven Feedback Loops for a NestJS + Remix + Next.js + Python Stack

## TL;DR
- **The single highest-leverage move is to plug AI agents (Claude Code, Cursor, Codex, Cline, Aider) directly into your existing OpenTelemetry/OpenObserve pipeline via MCP.** OpenObserve already ships an Enterprise MCP server exposing ~137 tools — including `SearchSQL`, `StreamList`, `StreamSchema`, `PrometheusRangeQuery`, and `GetIncident` — reachable at `https://your-instance/api/{org_id}/mcp`. Combine it with Chrome DevTools MCP, Playwright MCP, Sentry MCP, and Prisma MCP to give one agent a full vertical view of logs/traces/metrics/browser/errors/DB.
- **Tighten the inner loop with deterministic, agent-readable feedback.** Enforce a Stop hook that runs `tsc --noEmit` + `vitest --reporter=basic` + `eslint --format json` and blocks the agent until clean; standardize on AGENTS.md/CLAUDE.md with exact commands (per the Linux Foundation's December 9, 2025 AAIF announcement, AGENTS.md "has already been adopted by more than 60,000 open-source projects and agent frameworks including Amp, Codex, Cursor, Devin, Factory, Gemini CLI, GitHub Copilot, Jules and VS Code"); pipe Pino logs with `trace_id`/`span_id` injected by `@opentelemetry/instrumentation-pino` so a single ID stitches a stack trace to a span to a slow SQL query.
- **Use the right tool for the right pain.** Wallaby.js for typing-speed unit feedback, Vitest watch + focused tests for refactors, `clinic doctor/flame/bubbleprof/heapprofiler` for perf, `node --inspect=0.0.0.0:9229` inside Docker with `kubectl port-forward` for remote attaches, `wrangler tail --format json` for Cloudflare, `pytest -x --pdb` for Python — then encode all of it in AGENTS.md so the agent can do it for you.

## Key Findings

1. **Agents need a closed loop, not just a prompt.** Verification hooks that fail closed beat written rules every time. The empirical pattern from production Claude Code users is to move "you must run the tests" out of CLAUDE.md and into a Stop hook that runs `tsc --noEmit && vitest --reporter=basic --no-watch` and emits `{"decision":"block","reason":"..."}` when it fails, forcing the agent to keep working until verification passes.
2. **OpenObserve is already an agent platform, not just a backend.** Its Enterprise MCP endpoint exposes Search, Streams, Alerts, Dashboards, Pipelines, Sourcemaps and PromQL tools to any MCP client over HTTP+Basic Auth. The underlying `POST /api/{org_id}/_search` SQL API is trivial to wrap as a custom MCP tool for OSS deployments.
3. **The Chrome DevTools MCP is the biggest leap for full-stack debugging.** It lets an agent open your localhost app, read source-mapped stack traces from the console, capture network failures, and run performance traces — the developer becomes a director, not a copy/paster of screenshots.
4. **Trace-log-metric correlation is the single best ROI in observability.** Once `@opentelemetry/instrumentation-pino` injects `trace_id`/`span_id` into every Pino record and the same IDs appear on spans in OpenObserve, an agent can jump from a single error log to the full distributed trace and the slowest span via one SQL query.
5. **Most "spans missing" problems are configuration, not code.** Use the OTel Collector `debug` exporter with `verbosity: detailed`, check `otelcol_receiver_accepted_spans` and `otelcol_exporter_send_failed_spans`, and confirm 4317 (gRPC) vs 4318 (HTTP) ports. `telemetrygen` can simulate spans without touching app code.
6. **The Vitest/Wallaby gap matters more than you think.** Vitest re-runs all tests in files dependent on a change; Wallaby re-runs only the tests actually affected, as you type, with a time-travel debugger. Wallaby also ships its own MCP server giving agents runtime values, execution paths, and coverage.
7. **Hydration debugging in Remix/Next is mostly date/locale/extension drift.** Diffing server HTML against client HTML in a production build (`next build && next start`) and bisecting the component tree is the deterministic path; `suppressHydrationWarning` is a leaf-node escape hatch, not a fix.
8. **Empirical evidence supports tight agent feedback loops.** Alonso, Yovine & Braberman, *TDAD: Test-Driven Agentic Development – Reducing Code Regressions in AI Coding Agents via Graph-Based Impact Analysis* (arXiv:2603.17973): "TDAD reduced regressions by 70% (6.08% → 1.82%) compared to a vanilla baseline" and (Phase 2, Qwen3.5-35B-A3B + OpenCode) "improved issue-resolution rate from 24% to 32%" — i.e. an +8 pp SWE-bench Verified lift purely from telling the agent which tests are at risk.

## Details

### 1. The agent feedback-loop architecture (the core ask)

The mental model: an agent's success rate is bounded by the fidelity and latency of the signal it receives after it makes a change. Every second between "agent edits a file" and "agent sees a specific, structured failure" is wasted token spend and drift.

**The four signal layers — wire each into your agent:**

| Layer | Tool | How to feed it to the agent |
|---|---|---|
| Compiler | `tsc --noEmit` | exit code + stderr (already structured) |
| Linter | `eslint --format json` | machine-readable JSON output |
| Tests | `vitest --reporter=basic --no-watch` (or `--reporter=json` for tool parsing) | streamed to stdout |
| Runtime | OpenObserve MCP, Sentry MCP, Chrome DevTools MCP, Wallaby MCP | live queries from agent |

**Stop-hook pattern (Claude Code, portable to Cursor/Codex):**

```json
// .claude/settings.json
{
  "hooks": {
    "Stop": [
      { "hooks": [
        { "type": "command", "command": ".claude/hooks/verify.sh", "timeout": 180 }
      ]}
    ]
  }
}
```

```bash
# .claude/hooks/verify.sh
#!/bin/bash
INPUT=$(cat)
[ "$(echo "$INPUT" | jq -r '.stop_hook_active')" = "true" ] && exit 0
cd "$CLAUDE_PROJECT_DIR" || exit 0
OUTPUT=$(npx tsc --noEmit 2>&1 && npx vitest run --reporter=basic --no-watch 2>&1)
if [ $? -ne 0 ]; then
  jq -n --arg out "$(echo "$OUTPUT" | tail -50)" \
    '{decision:"block",reason:("Verification failed:\n" + $out)}'
fi
exit 0
```

Crucially, **don't** put `tsc --noEmit` in a per-edit (PostToolUse) hook on a real codebase — typecheck takes 10–30 seconds on a real codebase, multiplied by 50+ edits per feature that's tens of minutes of wall-clock time. Keep it in Stop. Reserve per-edit hooks for instant Rust-based formatters/linters (`oxfmt`, `oxlint`) that finish in milliseconds.

**Per-edit hook (cheap, instant feedback):**

```json
{ "hooks": { "PostToolUse": [
  { "matcher": "Edit|Write", "hooks": [
    { "type": "command", "command": "npx --no-install oxlint --fix $CLAUDE_FILE_PATHS" }
  ]}
]}}
```

**AGENTS.md / CLAUDE.md template for this stack.** This file is read once per session — keep it dense, command-first, and skip prose. AGENTS.md is the cross-tool open standard now stewarded by the Agentic AI Foundation under the Linux Foundation, supported by Amp, Codex, Cursor, Devin, Factory, Gemini CLI, GitHub Copilot, Jules, VS Code, Aider, goose, opencode, Zed, Warp and others; Claude Code reads `CLAUDE.md` — symlink them.

```markdown
# AGENTS.md

## Commands (run these, in this order, before declaring done)
- Typecheck:   pnpm typecheck         # tsc --noEmit -p tsconfig.json
- Lint (JSON): pnpm lint:json         # eslint . --ext .ts,.tsx --format json -o .agent/lint.json
- Test:        pnpm test              # vitest run --reporter=basic --no-watch
- E2E single:  pnpm test:e2e:focused  # playwright test --grep
- DB:          pnpm prisma:validate   # prisma validate && prisma format

## Debug feedback sources (query these before guessing)
- Logs/traces: MCP server "openobserve" — prefer SearchSQL with a 15-minute window
- Browser:     MCP server "chrome-devtools" — list_pages then list_console_messages
- Errors:      MCP server "sentry" — search_issues by file path
- DB:          MCP server "postgres" — read-only SELECTs only

## Conventions
- No `any`. Use `unknown` + narrowing. Use Zod at IO boundaries.
- Every NestJS controller method has a `span.setAttribute('user.id', ...)`.
- Every Remix loader returns typed data; never `any`.
- Logs are structured Pino: `logger.info({ userId, orderId }, 'message')`.
- Correlation IDs: trace_id/span_id are auto-injected — do not set manually.
- One Prisma query per function; flag N+1 explicitly.

## Conventional debug recipes
- "Why is X slow?" → SearchSQL `SELECT operation_name, approx_percentile_cont(duration,0.99) FROM traces WHERE service_name='api' GROUP BY 1 ORDER BY 2 DESC`
- "Why did X fail in staging?" → SearchSQL on logs where `level='error'`, then follow trace_id to spans
- "Hydration error in /dashboard" → curl the server HTML, diff against view-source, isolate by component
```

Per OpenAI's Codex docs: "more deeply nested files take precedence in case of conflicting instructions" — put environment-specific overrides (e.g. `apps/api/AGENTS.md` for the NestJS service) next to the code they govern.

**Self-healing loops in the wild.** Tools like `gnhf` ("good night, have fun") wrap Claude Code / Codex / Copilot CLI / OpenCode in a loop: each successful iteration becomes a separate commit on a `gnhf/<slug>` branch; failures get `git reset --hard`. The pattern is straightforward to replicate: run agent, run verify script, on success commit, on failure feed the structured output back, repeat with exponential backoff on hard errors. The TDAD paper (Alonso, Yovine & Braberman, arXiv:2603.17973) shows graph-based test impact analysis "reduced regressions by 70% (6.08% → 1.82%) compared to a vanilla baseline" and lifted issue-resolution rate "from 24% to 32%" when an agent is told which tests are actually at risk.

### 2. MCP server stack you should install today

Install order (highest ROI first). Use `claude mcp add` (Claude Code), `~/.cursor/mcp.json` (Cursor), or `~/.codex/config.toml` (Codex):

| MCP server | What an agent gains | Install |
|---|---|---|
| **chrome-devtools** | List pages, read console errors (source-mapped), capture network requests, run perf traces, take screenshots, click/fill forms | `claude mcp add chrome-devtools npx chrome-devtools-mcp@latest --autoConnect`. Per the official README at github.com/ChromeDevTools/chrome-devtools-mcp: "`--autoConnect`: automatically connects to a browser (Chrome 144+)" — note Chrome 144 shipped this on Beta only; Chrome 146 was the first stable release. Enable `chrome://inspect/#remote-debugging`. |
| **playwright** | Browser automation via the accessibility tree, with deterministic refs; works headed for visual verification | `claude mcp add playwright npx @playwright/mcp@latest` |
| **openobserve** | Query your own logs/traces/metrics with SQL/PromQL; manage alerts, dashboards, pipelines, sourcemaps; ~137 named tools | Enterprise only; set `O2_TOOL_API_URL` and `O2_AI_ENABLED=true`, then point client at `https://your-instance/api/{org}/mcp` with Basic Auth |
| **sentry** | Paste a Sentry issue URL; agent pulls stack trace + tags + Seer root-cause analysis | OAuth: `https://mcp.sentry.dev/mcp` (cloud) or `@sentry/mcp-server` stdio for self-hosted |
| **prisma** | Introspect schema, execute parameterized SQL on Prisma Postgres, manage migrations safely (built-in guard blocks `migrate reset --force` from agents) | `npx -y prisma mcp`. Per the official Prisma changelog (prisma.io/changelog/2025-04-10): "In the v6.6.0 ORM release, we added a command to start a Prisma MCP server that you can integrate in your AI development environment." |
| **wallaby** | Live runtime values, execution paths, coverage, dependencies — not just file contents | Bundled with Wallaby; per Wallaby's site: "Wallaby MCP server and tools give AI agents live access to test results, runtime values, execution paths, coverage, and dependencies" |

**Why Playwright MCP cost matters.** Per Microsoft's published benchmark (cited by the Playwright team and Pramod Dutta's analysis on skyvern.com/blog/what-is-playwright-mcp-server): "a typical browser automation task consum[es] roughly 114,000 tokens with MCP versus about 27,000 tokens with CLI, a 4x reduction, with longer sessions showing even wider gaps." Separately, the accessibility-tree approach itself is far smaller than screenshot-based control — accessibility snapshots run a few KB versus 500 KB–2 MB for screenshots. For exploratory debugging use MCP; for stable test suites in CI, promote interactions into `@playwright/test` specs.

**OpenObserve MCP — the exact tool surface (Enterprise).** Per OpenObserve's official MCP docs at openobserve.ai/docs/integration/ai/mcp/: "MCP is supported in the Enterprise edition of OpenObserve. Set the following environment variables on your OpenObserve instance: `O2_TOOL_API_URL="http://localhost:5080"`, `O2_AI_ENABLED="true"`." The endpoint URL pattern is `https://your-instance/api/{org_id}/mcp` with `Authorization: Basic <base64>`. Tool names are prefixed (`mcp__openobserve__SearchSQL`). The full surface (~137 tools across 16 categories) includes:

- **Search (17):** `SearchSQL` (pinned), `SearchAround`, `SearchValues`, `SearchPartition`, `SearchHistory`, `GetSavedView`, `ListSavedViews`, `SubmitSearchJob`, `GetSearchJobResult`, `RetrySearchJob`, plus CRUD on saved views and search jobs.
- **Streams (5):** `StreamList` (pinned), `StreamSchema` (pinned), `StreamCreate`, `UpdateStreamSettings`, `StreamDelete`.
- **PromQL/Metrics (7):** `PrometheusQuery`, `PrometheusRangeQuery` (pinned), `PrometheusMetadata`, `PrometheusSeries`, `PrometheusLabels`, `PrometheusLabelValues`, `PrometheusFormatQuery`.
- **Alerts (28):** `CreateAlert`, `ListAlerts`, `TriggerAlert`, `EnableAlert`, `ListIncidents`, `GetIncident` (pinned), `TriggerIncidentRca`, destinations, templates, etc.
- **Dashboards (20)**, **Pipelines (7)**, **Folders (6)**, **Functions (6)**, **Sourcemaps (4)**, **Patterns (1)**, **KV Store (4)**, **Service Accounts (4)**, **Users (5)**, **Organizations & System Settings (12)**, **Authorization (4)**, **Enrichment Tables (2)**, **Logs (1)**.

Verbatim MCP tool call example from the official docs:

```bash
curl https://your-instance/api/default/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Basic <YOUR_BASE64_TOKEN>" \
  -d @- <<EOF
{ "jsonrpc": "2.0", "method": "tools/call",
  "params": { "name": "SearchSQL", "arguments": {
    "org_id": "default",
    "request_body": { "query": {
      "sql": "SELECT * FROM logs WHERE level = 'error' LIMIT 10",
      "start_time": $START, "end_time": $END, "from": 0, "size": 10
    }}}}, "id": 1 }
EOF
```

**For OSS OpenObserve users:** the official MCP server is Enterprise-only, but the underlying HTTP API is open and trivial to wrap. The relevant n8n community workflow (n8n.io/workflows/15478) exposes exactly 10 forensic tools wrapping the public API:

1. **Stream Schema Inspection** — `DESCRIBE default`; "Allows the AI to see available fields before constructing queries."
2. **Unique Error Fingerprinting** — Groups by `message`, returns top recurring failures.
3. **Volume Trend Analysis** — "1-minute histogram over `_timestamp`; Surfaces abnormal traffic bursts."
4. **Log Pattern Discovery** — Groups by first 20 characters of `message`.
5. **P99 Latency Analysis (Traces)** — `approx_percentile_cont(duration, 0.99) GROUP BY operation_name`.
6. **Cold-Start Identification (Traces)** — `operation_name = 'init'`.
7. **Dependency Hotspots (Traces)** — average duration grouped by `service_name`.
8. **SQL Logs Query** — flexible SQL execution.
9. **Span Error Mapping (Traces)** — `status_code >= 400` within a `trace_id`.
10. **SQL Traces Query** — flexible SQL execution for traces.

Endpoints used: `/api/default/_search` for logs, `/api/default/_search?type=traces` for traces, HTTP Basic Auth.

**Roll your own OpenObserve tool for OSS in ~30 lines.** The search API is a single POST:

```bash
curl -X POST "https://o2.example.com/api/default/_search?type=logs" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Basic $O2_TOKEN" \
  -d '{
    "query": {
      "sql": "SELECT _timestamp, service_name, message, trace_id FROM default WHERE level=\u0027error\u0027 ORDER BY _timestamp DESC",
      "start_time": 1751443100969000,
      "end_time":   1751444000969000,
      "from": 0,
      "size": 100
    },
    "search_type": "ui",
    "timeout": 0
  }'
```

(Times are in microseconds; `size: -1` returns everything; `search_type` values: `"ui"`, `"dashboards"`, `"others"`.) Wrap that in an MCP server using `@modelcontextprotocol/sdk` and you have parity with the Enterprise feature for queries.

**Grafana, for completeness.** Per OpenObserve's MCP comparison blog: "Grafana ships multiple MCP server implementations: `mcp-grafana` (covering dashboards, Loki logs, Prometheus metrics, Tempo traces, alerting, OnCall, and incidents), a dedicated `loki-mcp`, a Tempo MCP server, and Grafana Cloud MCP (currently in public preview)." If you migrate observability backends later, the agent layer doesn't change.

**Security note for agent→DB MCP.** Always create a dedicated read-only user. The Prisma MCP server has an explicit built-in guardrail: "Error: Prisma Migrate detected that it was invoked by Cursor. You are attempting a highly dangerous action... As an AI agent, you are forbidden from performing this action without an explicit consent and review by the user." Replicate that pattern for your own MCP wrappers.

### 3. OpenTelemetry deep-dive for this exact stack

**Auto-instrumentation for NestJS.** Initialize *before any other import* — this is the #1 mistake. Spans for HTTP, Fastify/Express, Postgres, Prisma, Redis, undici/fetch all come for free:

```ts
// instrumentation.ts (loaded via -r/--require BEFORE main.ts)
import { NodeSDK } from '@opentelemetry/sdk-node';
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { PinoInstrumentation } from '@opentelemetry/instrumentation-pino';
import { resourceFromAttributes } from '@opentelemetry/resources';
import { ATTR_SERVICE_NAME, ATTR_SERVICE_VERSION } from '@opentelemetry/semantic-conventions';

const sdk = new NodeSDK({
  resource: resourceFromAttributes({
    [ATTR_SERVICE_NAME]: 'api',
    [ATTR_SERVICE_VERSION]: process.env.GIT_SHA ?? 'dev',
    'deployment.environment': process.env.NODE_ENV,
  }),
  traceExporter: new OTLPTraceExporter({ url: 'http://otel-collector:4318/v1/traces' }),
  instrumentations: [
    ...getNodeAutoInstrumentations({
      '@opentelemetry/instrumentation-fs': { enabled: false }, // noisy
    }),
    new PinoInstrumentation({
      logKeys: { traceId: 'trace_id', spanId: 'span_id', traceFlags: 'trace_flags' },
    }),
  ],
});
sdk.start();
```

Run with `node -r ./instrumentation.js dist/main.js`. Per the npm page for `@opentelemetry/instrumentation-pino`: "Pino logger calls in the context of a tracing span will have fields identifying the span added to the log record. This allows correlating log records with tracing data" — and separately "Log records will be sent to the SDK-registered log record processor" if you wire a `LoggerProvider`. The injected fields are `trace_id`, `span_id`, `trace_flags`.

**Manual span pattern for business logic.** Always record exceptions and set status:

```ts
async charge(customerId: string, amount: number) {
  return this.tracer.startActiveSpan('billing.charge', async (span) => {
    try {
      span.setAttributes({ 'customer.id': customerId, 'billing.amount': amount });
      const result = await this.gateway.charge(customerId, amount);
      span.setAttribute('billing.ok', result.ok);
      return result;
    } catch (err: any) {
      span.recordException(err);
      span.setStatus({ code: 2, message: err?.message });
      throw err;
    } finally {
      span.end();
    }
  });
}
```

**Cross-service trace-id in a NestJS interceptor:**

```ts
@Injectable()
export class TraceLogInterceptor implements NestInterceptor {
  intercept(ctx: ExecutionContext, next: CallHandler) {
    const req = ctx.switchToHttp().getRequest();
    const span = trace.getSpan(context.active());
    req.traceId = span?.spanContext().traceId;
    req.spanId  = span?.spanContext().spanId;
    return next.handle();
  }
}
```

This gives your error response a `trace_id` field — paste it into the OpenObserve UI (or an agent's `SearchSQL` call) and you have the entire request timeline.

**Next.js (your home stack).** Use the official `@vercel/otel` for the Edge runtime; fall back to `@opentelemetry/sdk-node` in a Node-only `instrumentation.node.ts` conditionally imported from `instrumentation.ts`. Add `@opentelemetry/instrumentation-undici` to capture `fetch()` calls between Next.js and downstream APIs.

**Debugging the OTel pipeline itself.** Three deterministic steps, in this exact order, when "nothing shows up":

1. **Verify spans exist at the SDK.** Add a `ConsoleSpanExporter` temporarily — if you see spans, the app is fine.
2. **Verify the Collector receives them.** Add the `debug` exporter with `verbosity: detailed` and tail the Collector logs; also check `curl http://localhost:8888/metrics | grep otelcol_receiver_accepted_spans`. Non-zero = received.
3. **Verify the Collector exports them.** Check `otelcol_exporter_sent_spans` vs `otelcol_exporter_send_failed_spans`. Common failure modes (per upstream docs): wrong port (4317 gRPC vs 4318 HTTP), TLS mismatch, missing auth header, HTTP 413 from oversized batches (lower `send_batch_size`).

The `telemetrygen` tool is the fast-feedback shortcut — `telemetrygen traces --otlp-endpoint localhost:4317 --rate 10 --duration 30s` simulates load without touching your app.

**zPages.** Enable the `zpages` extension on the Collector (port 55679) — `/debug/tracez` lets you see latency buckets and live spans inside the Collector itself. Critical for diagnosing the difference between "Collector dropped it" and "backend never accepted it".

**OpenObserve operational tips.**
- Use the SQL `histogram(_timestamp)` function for time-series of any field — perfect for spotting bursts of errors right after a deploy.
- Use `match_all('keyword')` (full-text, indexed) instead of `LIKE` on the `message` field — much faster.
- Use `re_match(field, 'regex')` for advanced filtering, e.g. `re_match(k8s_container_name, 'api|worker')`.
- Use `str_match_ignore_case(...)` for case-insensitive equality without paying the regex cost.
- The MCP server has 137 tools across 16 categories — pre-pin only the ones you need (Search, Streams, Pipelines) to avoid blowing up the context window.

### 4. Node.js / TypeScript advanced debugging

**Interactive debugging hierarchy:**
- VS Code "Auto Attach" + `pnpm dev` → for local apps, the path of least resistance.
- `node --inspect=0.0.0.0:9229 dist/main.js` inside a container, `EXPOSE 9229`, then VS Code `"request":"attach","port":9229,"address":"localhost","remoteRoot":"/app","localRoot":"${workspaceFolder}"`.
- Already-running container: `docker exec my-container kill -SIGUSR1 1` activates the inspector without restart; in K8s, `kubectl exec ... -- kill -SIGUSR1 1` then `kubectl port-forward pod/x 9229:9229`.
- For remote (staging) VMs, always tunnel: `ssh -L 9229:127.0.0.1:9229 user@host`. **Never** publish 9229; the CDP protocol has zero auth.

**Conditional breakpoints + logpoints (VS Code).** Right-click the gutter → "Add Conditional Breakpoint" with an expression like `req.userId === '123'`. Logpoints (`Add Logpoint`) emit a message without stopping execution — invaluable when you can't reproduce reliably and want to avoid the heisenbugs of `console.log`.

**Performance — clinic.js is the cleanest workflow:**
- `clinic doctor -- node server.js` then load with `autocannon` → categorical diagnosis (CPU/I-O/Memory/Event Loop).
- `clinic flame` for CPU flame graphs (wide bars = hot functions).
- `clinic bubbleprof` for async waterfalls (large bubbles = long awaits).
- `clinic heapprofiler` for memory leaks (large blocks = retained allocations).

**Memory leak hunting in production-safe mode.** `node --heap-prof --heap-prof-interval=512000 dist/main.js` writes a `.heapprofile`; load in Chrome DevTools Memory tab. Or trigger an on-demand snapshot: `kill -SIGUSR2 <pid>` after enabling `process.on('SIGUSR2', () => v8.writeHeapSnapshot())`. Diff two snapshots in DevTools to surface retained objects.

**Event loop lag.** Add a 1-line sentinel:
```ts
import { monitorEventLoopDelay } from 'perf_hooks';
const h = monitorEventLoopDelay({ resolution: 20 }); h.enable();
setInterval(() => logger.info({ p99: h.percentile(99) / 1e6 }, 'evloop'), 5000);
```

**Diagnostic reports.** `node --report-on-fatalerror --report-on-signal --report-signal=SIGUSR2 main.js` writes a JSON report on crash or SIGUSR2 — heap state, env, libuv handles, native stack. Ship to OpenObserve as a structured log.

**NestJS-specific.**
- DI errors: turn on `logger: ['error','warn','log','debug','verbose']` in `NestFactory.create` to see provider resolution.
- Request lifecycle: write a `LoggerMiddleware` early and an `ExceptionsFilter` late; both should `logger.info({ trace_id })` so the agent can pivot between log and trace.
- Use `Scope.REQUEST` providers only when necessary — they break some auto-instrumentation singleton assumptions.

**Prisma debugging.**
```ts
const prisma = new PrismaClient({
  log: [
    { emit: 'event', level: 'query' },
    { emit: 'event', level: 'warn' },
    { emit: 'event', level: 'error' },
  ],
});
prisma.$on('query', (e) => logger.debug({ ms: e.duration, sql: e.query, params: e.params }, 'prisma'));
```
Combined with OTel's Prisma instrumentation, every query becomes a span. Slow ones surface immediately in the OpenObserve traces UI; an agent can run `SearchSQL` with `WHERE operation_name LIKE 'prisma:%' AND duration > 100`.

**TS/source maps.** When running compiled output (tsx/ts-node/esbuild/swc), always emit source maps in dev and set `NODE_OPTIONS='--enable-source-maps'` so stack traces point at `.ts` lines, not `.js`. For production, upload source maps to Sentry (or OpenObserve's `SourcemapList`/`SourcemapStacktrace` MCP tools) so symbolicated stacks land back in your error tracker.

### 5. Frontend / browser debugging

**Chrome DevTools MCP is the workflow change.** Rather than copy-pasting console errors, the agent loop becomes: write code → start dev server → ask agent "test /checkout" → agent navigates, reads console, fixes, retests. The MCP supports `--autoConnect` so it attaches to your existing Chrome profile (with logins/cookies) rather than launching a fresh one — set up per the Chrome 144+ Beta / 146+ stable `chrome://inspect/#remote-debugging` flow.

**Playwright MCP for reproducible bug capture.** Run headed to verify visually, then promote the same `browser_snapshot`-based interaction into a maintained `@playwright/test` spec. Use `trace.zip` (Playwright trace viewer) for any flaky failure — it's a full DOM + network + console replay.

**Hydration mismatches (Remix and Next).** The cause is one of: dates/timezones/locales (the most common — `new Date().toLocaleString()` differs between server and client), `Math.random()`/`Date.now()`, `typeof window !== 'undefined'` branches in render bodies, browser extensions injecting DOM, ad-blockers, CSS-in-JS double-render quirks, or CDN HTML minification (Cloudflare Auto Minify is a known offender).

Deterministic debug workflow:
1. Reproduce in production build (`next build && next start`); dev mode masks timing.
2. View-source the HTML; diff against `document.body.innerHTML` after hydration (use diffchecker.com).
3. Binary-search the component tree by replacing halves with static placeholders.
4. For client-only content, wrap with `<ClientOnly>` (Remix-utils) or `dynamic(() => ..., { ssr: false })` (Next).
5. Use React's `useId` (not `Math.random()`) for stable IDs.
6. Per Next.js docs: "You can silence the hydration mismatch warning by adding `suppressHydrationWarning={true}` to the element. This only works one level deep, and is intended to be an escape hatch. Don't overuse it."

**Remix-specific gotcha.** Hydration errors triggered by a loader-thrown response will sometimes render the ErrorBoundary without styles (remix-run/remix issues #8764 / #9610) — workaround is to add a `HydrateFallback` export per route. For locale-driven mismatches (`toLocaleDateString`), normalize the server's locale or parse dates in the loader so the server timezone is used once.

**Capturing client-side errors with source-mapped stacks.** Wire `@sentry/remix` or `@sentry/nextjs`, upload source maps in CI, and the agent (via Sentry MCP) can read symbolicated stacks. For an OpenObserve-only setup, the `SourcemapList`/`SourcemapStacktrace` MCP tools do the equivalent.

### 6. Python (your automation/testing)

```bash
pytest -x --pdb                  # stop on first failure, drop into pdb
pytest --lf -x --pdb             # rerun last failure only, drop into pdb
pytest -l --tb=short             # show locals, short traceback
pytest -k "checkout and not slow" # focused selection
pytest --durations=10            # find slow tests
```

For agent-readable output, `pytest --junitxml=report.xml` or `pytest --json-report` give structured failures. Combine with `rich` for human-readable tracebacks (`from rich.traceback import install; install(show_locals=True)`).

**The `breakpoint()` builtin** (Python 3.7+) is preferable to importing `pdb` directly — it respects `PYTHONBREAKPOINT=ipdb.set_trace` for richer interactive sessions.

Wire pytest into AGENTS.md:
```
## Python
- Run tests: uv run pytest -x --tb=short -q
- Focused:   uv run pytest -k <expr>
- Type check: uv run mypy --strict src/
- Format:    uv run ruff format && uv run ruff check --fix
```

### 7. Cross-cutting: bisect, contracts, observability-driven dev

- **`git bisect run pnpm test:e2e:focused`** turns "when did this break?" into a 10-minute binary search.
- **Shift left with contracts.** Zod (or Valibot) at every IO boundary (HTTP body, env vars, DB results); turn runtime errors into compile-time + early-runtime errors with explicit `safeParse` and structured logging on failure. The TypeScript reviewer pattern from Claude Code skills: catch "Unhandled promise rejections", "Sequential awaits for independent work" that should be `Promise.all`, "Floating promises: Fire-and-forget without error handling", "JSON.parse without try/catch: Throws on invalid input — always wrap". Encode these as project lint rules so the agent gets them at edit time.
- **Cloudflare Workers.** `wrangler tail --format json --status error | jq` is the moral equivalent of `kubectl logs` for the edge. Enable `[observability] enabled = true` in `wrangler.toml` for persistent Workers Logs. Per the official Cloudflare Workers Logs docs: "The Paid plan bundles 20 million per month with 7-day retention and charges $0.60 per additional million events." For high-traffic Workers, head-sample via `head_sampling_rate = 0.1` (10% of invocations). For agent integration, Cloudflare ships a Workers Observability MCP server documented at developers.cloudflare.com/workers/observability/.

## Recommendations — a skills-based approach (no MCP)

You don't need always-on MCP connections to get the same feedback loops. **Package each capability as an agent skill: a `SKILL.md` describing when and how to use it, plus a small script the agent runs on demand.** This is leaner than MCP — nothing is loaded into context until the task actually calls for it, there are no long-lived server processes, and a 137-tool surface never bloats your context window. The trade-off is that skills are pull-based (the agent shells out to a script and reads stdout) rather than push-based (a live tool surface), which for debugging is exactly what you want: you query logs, traces, the browser, or the DB only when chasing a specific bug.

**How a debug skill is structured.** Each skill is a directory the agent discovers by its `SKILL.md` description, then executes the bundled script and reads structured stdout back into its loop:

```
.agent/skills/
  query-observability/
    SKILL.md          # "Use when debugging a prod/staging error or slow request..."
    o2_search.sh      # wraps POST /api/{org}/_search, returns JSON
  inspect-browser/
    SKILL.md          # "Use to read console errors / network failures on a running app"
    capture.mjs       # Playwright script: navigate, dump console + failed requests + screenshot
  query-db/
    SKILL.md          # "Use for read-only SELECTs against staging DB"
    psql_ro.sh        # connects as a read-only role, refuses non-SELECT
  profile-node/
    SKILL.md          # "Use when something is slow or leaking memory"
    profile.sh        # clinic doctor/flame/heapprofiler wrapper
```

Example `SKILL.md` for the observability skill (this is the whole interface the agent needs):

```markdown
---
name: query-observability
description: >
  Query OpenObserve logs and traces when debugging a production or staging
  error, a slow request, or a failed deploy. Use whenever a trace_id, error
  message, or service name is known and you need the runtime evidence.
---
# Querying OpenObserve

Run `./o2_search.sh <logs|traces> "<SQL>" <minutes_back>`. Output is JSON.

## Recipes
- Recent errors:      ./o2_search.sh logs "SELECT _timestamp, service_name, message, trace_id FROM default WHERE level='error' ORDER BY _timestamp DESC" 15
- Follow a trace:     ./o2_search.sh traces "SELECT operation_name, duration, status_code FROM default WHERE trace_id='<id>' ORDER BY start_time" 60
- Slowest endpoints:  ./o2_search.sh traces "SELECT operation_name, approx_percentile_cont(duration,0.99) p99 FROM default GROUP BY 1 ORDER BY 2 DESC" 60
- Error burst after deploy: ./o2_search.sh logs "SELECT histogram(_timestamp) t, count(*) c FROM default WHERE level='error' GROUP BY t" 30

## Rules
- Always pass the smallest time window that could contain the evidence.
- Times are auto-converted to microseconds by the script. Do not compute them.
- Never run anything but SELECT.
```

The script underneath is the ~20-line `curl` wrapper from the OpenObserve section — it computes the micro-second timestamps, injects Basic Auth from an env var, and prints JSON. No Enterprise license, no MCP server, works against your existing OSS instance.

**Week 1 — Foundation:**
1. Create four skills: `query-observability` (wraps `/api/{org}/_search`), `inspect-browser` (a Playwright `capture.mjs` that dumps console + network + screenshot), `query-db` (read-only `psql`), and `profile-node` (clinic wrapper). Keep each `SKILL.md` under 40 lines.
2. Write a minimal AGENTS.md (symlinked as CLAUDE.md and `.cursorrules`) using the template above, but point the "Debug feedback sources" section at the **skills** instead of MCP servers (see updated block below). Commit to every repo, keep under 150 lines.
3. Wire the Stop hook (`tsc --noEmit && vitest run`) in `.claude/settings.json`. Add `eslint --format json` if you have lint debt.
4. Add `@opentelemetry/instrumentation-pino` if not already enabled; verify `trace_id` appears in a sample log line.

Updated AGENTS.md debug block (skills, not MCP):

```markdown
## Debug feedback sources (use the matching skill before guessing)
- Logs/traces: skill `query-observability` — prefer the smallest time window
- Browser:     skill `inspect-browser` — dumps console errors + failed requests
- DB:          skill `query-db` — read-only SELECTs only
- Perf/leak:   skill `profile-node` — clinic doctor first, then flame/heapprofiler
```

**Week 2 — Tightening the loop:**
5. Add a per-edit hook running `oxlint --fix` (or `eslint --fix`) — must finish in <1s.
6. Bake `clinic doctor` into the `profile-node` skill; run once per service to baseline before any future perf work.
7. For test feedback, standardize the agent on focused Vitest (`vitest run path/to/file.test.ts`). Wallaby remains the fastest human-facing loop if you want it, but it's optional and orthogonal to the skills approach.
8. Set `NODE_OPTIONS='--enable-source-maps'` everywhere; verify a production stack trace points at `.ts` files.

**Week 3 — Production debugging:**
9. Enable diagnostic reports: `node --report-on-fatalerror --report-on-signal=SIGUSR2`. Ship the JSON to OpenObserve as a separate stream.
10. Set up alerting in OpenObserve (in the UI) on `event_loop_lag_p99 > 50ms` and `traces where duration > 1s AND service_name='api'`.
11. Build one composite skill — `triage-incident` — that takes a `trace_id` or error message and internally calls the observability + db scripts to assemble the trace, the surrounding 15-minute log window, and the relevant Prisma queries into a single report. This collapses the most common "why is this broken in staging" loop into one skill invocation.

**Thresholds that should change your approach:**
- If `tsc --noEmit` takes >15s, switch to project references (`tsc -b`) — the agent loop is too slow.
- If `vitest run` takes >30s for a focused change, the agent isn't running focused tests; enforce `vitest run path/to/file.test.ts`.
- If hooks add >2s per file edit, move the slow ones into Stop — agents make 50+ edits per task.
- If an agent regularly burns >5 turns "guessing", you're missing a skill for that signal — add one.
- If MTTD/MTTR on prod bugs doesn't drop within 30 days, the skills aren't being invoked during incidents. Codify a "first 5 minutes: agent runs `query-observability` for the last error in $service" runbook.

## Caveats

- **Don't expose CDP/9229 to the public internet.** Anyone who reaches the port can execute arbitrary code in your process. SSH-tunnel or `kubectl port-forward` only.
- **Skills are only as safe as their scripts.** Bake the guardrails into the script, not the prose: `query-db` should connect as a read-only Postgres role and refuse anything but SELECT; `o2_search.sh` should reject non-SELECT SQL. Don't rely on the `SKILL.md` "rules" section alone — an agent can ignore prose, but it can't bypass a role with no write grant.
- **Pino instrumentation has two modes** (per the official npm docs): "log correlation" injects `trace_id`/`span_id` into records (mostly free); "log sending" routes records through the OTel Logs SDK — a silent no-op if your SDK has no `LoggerProvider`. Verify with `ConsoleLogRecordExporter` first.
- **Hydration debugging in production builds only.** Dev mode reshapes timing and hides errors; reproduce with `next build && next start` before claiming a fix works.
- **OpenObserve's official MCP is Enterprise-only — which is exactly why the skills approach wins for you.** The skill wraps the open `/api/{org}/_search` HTTP API directly, so you get the same query power on the OSS edition with no license and no server process.
- **TDAD results are research-grade, not enterprise benchmarks.** The 70% regression reduction and +8 pp issue-resolution lift were measured on Qwen3.5-35B-A3B + OpenCode against SWE-bench Verified subsets; treat the direction as solid, the specific numbers as illustrative.
- **Wallaby is paid and optional.** Fastest JS/TS test-feedback loop available, but Vitest watch + focused-test discipline is a free, viable alternative and needs no skill.
- **Agent capability is on a steep curve.** The patterns here (Stop hooks, skills, AGENTS.md layering) are current as of May 2026. Re-evaluate quarterly.

## Summary

The fastest debugging is the kind an agent can do for you in a closed loop, and that loop is only as good as the signal you feed back after each change. The highest-leverage moves are deterministic verification (a Stop hook running `tsc --noEmit` + focused Vitest that blocks the agent until clean), a dense command-first AGENTS.md/CLAUDE.md so the agent already knows your exact commands, and structured logging where `@opentelemetry/instrumentation-pino` injects `trace_id`/`span_id` into every Pino record so one ID stitches a stack trace to a span to a slow SQL query in OpenObserve. Rather than wiring always-on MCP servers, package each runtime signal — observability queries, browser console/network capture, read-only DB access, Node profiling — as an on-demand skill: a short `SKILL.md` plus a hardened script the agent shells out to only when a specific bug calls for it. This keeps context lean, needs no Enterprise license (the observability skill wraps the open `/api/{org}/_search` API directly), and turns "why is this broken in staging" into a single skill invocation that assembles the trace, the surrounding logs, and the relevant queries in seconds.

Underneath the agent layer, classic technique still decides how fast you find the bug. Reach for interactive debuggers and conditional breakpoints/logpoints over `console.log`; attach to remote/containerized Node via `--inspect` over an SSH tunnel or `kubectl port-forward` (never expose 9229); use `clinic doctor → flame/bubbleprof/heapprofiler` for performance and leaks; and bisect with `git bisect run` to turn "when did this break" into a binary search. Shift bugs left with Zod contracts at IO boundaries and `--enable-source-maps` so stacks point at `.ts`. For the framework-specific traps, debug hydration mismatches only in production builds by diffing server HTML against client and bisecting the component tree, log Prisma queries as spans to surface N+1s and slow SQL, and for Python lean on `pytest -x --pdb` with `--lf` and rich tracebacks. The OTel pipeline itself fails far more often than your code: when spans go missing, verify SDK → Collector (`debug` exporter, `otelcol_receiver_accepted_spans`) → backend in that order, and remember 4317 is gRPC, 4318 is HTTP.

## Technique Tier List

| Tier | Technique | Why it ranks here | Effort to adopt |
|---|---|---|---|
| **S** | Pino + OTel `trace_id`/`span_id` correlation in OpenObserve | One ID jumps log → trace → slow query; the single best observability ROI | Low (one instrumentation pkg) |
| **S** | Stop hook: `tsc --noEmit` + focused Vitest, fail-closed | Deterministic agent verification beats any written rule | Low |
| **S** | On-demand debug **skills** (observability / browser / db / profile) | Same power as MCP, lean context, no license, pull-based = right for debugging | Medium (write 4 scripts) |
| **S** | Dense AGENTS.md / CLAUDE.md with exact commands + recipes | Agent stops guessing commands; cross-tool open standard | Low |
| **A** | Interactive debugger + conditional breakpoints / logpoints | Surgical state inspection without `console.log` heisenbugs | Low |
| **A** | `inspect-browser` skill (Playwright: console + network + screenshot) | Agent reads source-mapped client errors itself; ends copy-paste | Medium |
| **A** | clinic.js (`doctor → flame/bubbleprof/heapprofiler`) | Cleanest categorical perf/leak diagnosis | Medium |
| **A** | `git bisect run <test>` | Converts "when did it break" into a 10-min binary search | Low |
| **A** | Source maps everywhere (`--enable-source-maps`) | Stacks point at `.ts`, not compiled `.js` | Low |
| **A** | Prisma query logging as OTel spans | N+1 and slow SQL surface instantly in traces | Low |
| **B** | Remote `--inspect` via SSH tunnel / `kubectl port-forward` | Essential for staging/container bugs, but situational | Medium |
| **B** | Zod contracts at IO boundaries (shift-left) | Turns runtime errors into early, structured failures | Medium |
| **B** | Diagnostic reports (`--report-on-signal`) + heap snapshots | High value, but only when chasing crashes/leaks | Low |
| **B** | Wallaby.js (live test feedback + time-travel) | Fastest human TDD loop, but paid and optional | Low (paid) |
| **B** | Hydration diff workflow (prod build, bisect tree) | Decisive for SSR mismatch bugs, narrow applicability | Low |
| **C** | OTel pipeline debugging (`debug` exporter, zPages, `telemetrygen`) | Critical when telemetry breaks, irrelevant otherwise | Medium |
| **C** | Event-loop lag sentinel | Cheap early-warning, niche until you have a throughput issue | Low |
| **C** | `wrangler tail --format json` (Cloudflare edge) | Only relevant for Workers-hosted code | Low |