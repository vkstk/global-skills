---
name: debug-nestjs
description: >
  NestJS-specific debugging skill. Use when diagnosing NestJS API errors, DI failures,
  slow endpoints, Prisma N+1 queries, missing OpenTelemetry spans, or request lifecycle
  issues. Covers OTel setup, Pino correlation, manual spans, interceptors, Prisma tracing,
  and remote attach patterns.
---

# Debugging NestJS

## 1 — OpenTelemetry bootstrap (critical: load BEFORE main.ts)

```ts
// instrumentation.ts  — load via node -r ./instrumentation.js dist/main.js
import { NodeSDK } from '@opentelemetry/sdk-node';
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-http';
import { PinoInstrumentation } from '@opentelemetry/instrumentation-pino';
import { resourceFromAttributes } from '@opentelemetry/resources';
import { ATTR_SERVICE_NAME, ATTR_SERVICE_VERSION } from '@opentelemetry/semantic-conventions';

const sdk = new NodeSDK({
  resource: resourceFromAttributes({
    [ATTR_SERVICE_NAME]: process.env.SERVICE_NAME ?? 'api',
    [ATTR_SERVICE_VERSION]: process.env.npm_package_version ?? '0.0.0',
  }),
  traceExporter: new OTLPTraceExporter({
    url: process.env.OTEL_EXPORTER_OTLP_ENDPOINT ?? 'http://localhost:4318/v1/traces',
  }),
  instrumentations: [
    getNodeAutoInstrumentations(),
    new PinoInstrumentation(),        // injects trace_id + span_id into every Pino log
  ],
});
sdk.start();
```

`PinoInstrumentation` auto-injects `trace_id`, `span_id`, `trace_flags` — **do not set these manually**.

## 2 — Manual spans for business logic

```ts
import { trace, SpanStatusCode } from '@opentelemetry/api';

const tracer = trace.getTracer('billing');

async charge(customerId: string, amount: number) {
  return tracer.startActiveSpan('billing.charge', async (span) => {
    try {
      span.setAttributes({ 'customer.id': customerId, 'billing.amount': amount });
      const result = await this.stripe.charge(customerId, amount);
      return result;
    } catch (err) {
      span.recordException(err as Error);
      span.setStatus({ code: SpanStatusCode.ERROR, message: (err as Error).message });
      throw err;
    } finally {
      span.end();
    }
  });
}
```

Every NestJS controller method should call `span.setAttribute('user.id', ...)` for correlation.

## 3 — Expose trace_id on error responses (interceptor)

```ts
import { Injectable, NestInterceptor, ExecutionContext, CallHandler } from '@nestjs/common';
import { trace } from '@opentelemetry/api';

@Injectable()
export class TraceLogInterceptor implements NestInterceptor {
  intercept(ctx: ExecutionContext, next: CallHandler) {
    const span = trace.getActiveSpan();
    const traceId = span?.spanContext().traceId;
    if (traceId) {
      ctx.switchToHttp().getResponse().setHeader('X-Trace-Id', traceId);
    }
    return next.handle();
  }
}
```

Wire globally in `main.ts`: `app.useGlobalInterceptors(new TraceLogInterceptor())`.
Paste `X-Trace-Id` value into `query-observability` skill to get the full request timeline.

## 4 — Prisma query tracing

```ts
const prisma = new PrismaClient({
  log: [
    { level: 'query', emit: 'event' },
    { level: 'error', emit: 'event' },
    { level: 'warn',  emit: 'event' },
  ],
});
prisma.$on('query', (e) =>
  logger.debug({ ms: e.duration, sql: e.query, params: e.params }, 'prisma:query')
);
```

Combined with `@opentelemetry/auto-instrumentations-node` (includes Prisma instrumentation), every
query becomes a span. Surface slow ones:

```sql
-- via query-observability skill
SELECT operation_name, approx_percentile_cont(duration, 0.99) p99
FROM default
WHERE operation_name LIKE 'prisma:%'
  AND _timestamp > NOW() - INTERVAL 15 MINUTE
GROUP BY 1 ORDER BY 2 DESC
```

Flag N+1 patterns: the same `operation_name` appearing >10× in a single `trace_id`.

## 5 — DI / provider errors

Turn on verbose logging in `main.ts` to see full provider resolution:

```ts
const app = await NestFactory.create(AppModule, {
  logger: ['error', 'warn', 'log', 'debug', 'verbose'],
});
```

Common causes: circular dependency (use `forwardRef`), `Scope.REQUEST` breaking singleton
instrumentation assumptions, missing `@Global()` on shared modules.

## 6 — Request lifecycle logging

```ts
// logger.middleware.ts
@Injectable()
export class LoggerMiddleware implements NestMiddleware {
  use(req: Request, res: Response, next: NextFunction) {
    const span = trace.getActiveSpan();
    logger.info({
      method: req.method,
      path: req.path,
      trace_id: span?.spanContext().traceId,
    }, 'request:start');
    next();
  }
}
```

Pair with an `AllExceptionsFilter` that logs `{ trace_id, statusCode, message }` so the agent can
pivot from an error log to the full span in one `query-observability` call.

## 7 — Remote attach (Docker / Kubernetes)

```bash
# Docker: start with inspector exposed
node --inspect=0.0.0.0:9229 dist/main.js
# in docker-compose: ports: ["127.0.0.1:9229:9229"]

# Already-running container — no restart needed
docker exec <container> kill -SIGUSR1 1

# Kubernetes
kubectl exec <pod> -- kill -SIGUSR1 1
kubectl port-forward pod/<pod> 9229:9229

# Remote VM — always tunnel, never expose 9229
ssh -L 9229:127.0.0.1:9229 user@host
```

VS Code `launch.json` attach config:

```json
{
  "type": "node",
  "request": "attach",
  "name": "Attach NestJS",
  "port": 9229,
  "address": "localhost",
  "remoteRoot": "/app",
  "localRoot": "${workspaceFolder}",
  "sourceMaps": true,
  "skipFiles": ["<node_internals>/**"]
}
```

## 8 — Stop-hook verification (AGENTS.md commands)

```bash
pnpm typecheck    # tsc --noEmit -p tsconfig.json
pnpm lint:json    # eslint . --format json -o .agent/lint.json
pnpm test         # vitest run --reporter=basic --no-watch
```

Run in this order before declaring done. Typecheck belongs in Stop hook, not per-edit.

## 9 — Common NestJS gotchas

| Symptom | Likely cause | Fix |
|---|---|---|
| Spans missing | `instrumentation.ts` loaded after `main.ts` | Move to `-r ./instrumentation.js` |
| `trace_id` absent in logs | `PinoInstrumentation` not in SDK | Add to `instrumentations` array |
| DI error on `Scope.REQUEST` | Breaks singleton OTel span propagation | Use `REQUEST` scope only when essential |
| Slow Prisma queries invisible | No `$on('query')` listener | Wire query event listener |
| N+1 not surfaced | OTel Prisma instrumentation missing | Ensure `@opentelemetry/auto-instrumentations-node` includes it |
