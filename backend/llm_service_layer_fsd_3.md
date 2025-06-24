# Functional Specification Document (FSD)

## LLM Service Layer – **Internal‑Use, Robust‑Yet‑Lean** Edition

**Version 1.2 – 2025‑06‑24** (applies v1.1 review feedback)

---

### 1 Purpose

Internal tool for four engineers to compare outputs from multiple LLM providers **without risking token loss**, while keeping operational overhead extremely low.  Enhancements added in this revision improve resiliency against the single most likely failure‑modes—Postgres downtime and silent data gaps—without re‑introducing heavy external dependencies.

Priority order: 1) data integrity, 2) availability during dev hours, 3) simplicity of ops, 4) viewpoint diversity, 5) latency.

### 2 Scope (unchanged)

- Single‑node FastAPI + Postgres; Docker‑compose.
- Providers: OpenAI, Anthropic, Google Gemini/Vertex, DeepSeek, Cohere.

### 3 Key Terms (unchanged)

### 4 Architecture After Review

```
        ┌──── Engineers POST /prompt ───┐
┌───────────────────┐                  ▼
│   FastAPI Server  │── async gather─► Buffer & Persist
└───────────────────┘                  │
          ▲                            ▼  flush(≤16 tokens or 1 s)
          │                       ┌──────────────────┐
          │   SSE /stream/{id}    │  Token Persister │
          └──────────────────────►│  (PG + File WAL) │
                                  └──────────────────┘
                                          │ COPY
                                          ▼
                                  ┌──────────────────┐
                                  │  Postgres (TLS)  │
                                  └──────────────────┘
```

**Changes vs v1.1**

1. **File‑based Write‑Ahead Log (WAL‑Lite).**  If Postgres is unreachable, token batches append to `tokens.wal` (newline‑delimited JSON).  On reconnect or restart the persister replays the file into Postgres and truncates it.
2. **Graceful Shutdown.**  SIGTERM → stop accepting new requests → flush in‑memory buffer & close WAL file → exit.
3. **Weekly Retention Job.**  Cron inside container (`/etc/cron.weekly/prune_tokens.sh`) deletes rows older than 180 days.
4. **Enhanced Health Endpoint.**  `/health` now returns buffer length, last flush duration, last DB OK timestamp, WAL‑Lite file size.

### 5 Functional Requirements (delta)

#### 5.1 Prompt Handling (additions)

- **Input limits:** max 8 k characters prompt; reject non‑UTF‑8 with 400.

#### 5.3 Token Persistence (expanded)

- In‑memory buffer (`batch_size=16 | 1 s`)
- **If INSERT fails → write batch to WAL‑Lite file**.  Background task attempts replay every 10 s.
- Primary key prevents duplicates when WAL replay overlaps live inserts.

#### 5.6 Admin / Health (enhanced)

- Response sample:

```json
{
  "providers": {"openai": "closed", "anthropic": "half‑open"},
  "db_ok": true,
  "buffer_len": 4,
  "last_flush_ms": 110,
  "wal_size_bytes": 2048,
  "last_db_write": "2025‑06‑24T14:02:09Z"
}
```

### 6 Boot‑time Consistency Check

On startup FastAPI runs:

```sql
SELECT request_id, attempt_seq
FROM (
  SELECT request_id, attempt_seq, token_index,
         lag(token_index) OVER (PARTITION BY request_id,attempt_seq ORDER BY token_index) AS prev
  FROM llm_token_log) q
WHERE prev IS NOT NULL AND token_index <> prev + 1
LIMIT 10;
```

If rows returned → log `WARNING: token gap detected`; service still starts but health endpoint surfaces `token_gap=true`.

### 7 Data Model (unchanged SQL)

- Additional index on `ts` for prune speed.

### 8 Retention & Backup

- **Weekly prune job** removes tokens > 180 days.
- Daily `pg_dump` still performed via simple shell script.
- WAL‑Lite file auto‑rotates at 100 MiB (old file renamed `wal‑$(date).bak`).

### 9 Observability (minor)

- `/metrics` optional endpoint exposes buffer\_len, wal\_size\_bytes, attempts\_total.

### 10 Deployment (unchanged)

- `docker compose up` now launches an extra lightweight helper container `pruner` with cron.

### 11 Non‑Functional Goals (updated)

- **Durability:** no token loss unless *both* Postgres storage and WAL‑Lite disk vanish.
- **Recovery:** tokens.wal replay guarantees Postgres downtime ≤ 3 h loses ≤ 1 s of data.

### 12 Removed vs v1.1 (Still Removed)

| Feature                            | Status                                                     |
| ---------------------------------- | ---------------------------------------------------------- |
| Redis / Kafka / Vault / HA replica | still omitted                                              |
| Live fan‑out polling optimisation  | *not adopted* – 4 dev users unlikely to overload Postgres  |
| Schema version audit table         | *not adopted* – schema drift risk acceptable in small team |
| Disk encryption                    | *not adopted* – dev laptops already full‑disk encrypted    |

---

## Appendix A – Review Suggestions Adopted

| # | Suggestion                    | Implementation                                     |
| - | ----------------------------- | -------------------------------------------------- |
| 1 | Disk‑backed write‑ahead queue | WAL‑Lite file `tokens.wal`; replay loop every 10 s |
| 2 | Automated prune               | weekly cron job inside container                   |
| 3 | Health metrics                | extended `/health` JSON plus `/metrics` optional   |
| 4 | Boot‑time gap check           | SQL scan & warning                                 |
| 5 | Input validation & size cap   | 8 k chars, UTF‑8 only                              |
| 6 | Graceful shutdown             | SIGTERM handler flushes buffer + WAL file          |

## Appendix B – Review Suggestions **Not** Adopted & Rationale

| Suggestion                             | Reason                                                                      |
| -------------------------------------- | --------------------------------------------------------------------------- |
| In‑memory fan‑out to reduce DB polling | Single‑second polling by ≤4 users OK; extra thread adds code complexity.    |
| Git pre‑commit hook to block `.env`    | Devs already follow private‑repo workflow; agreed discipline.               |
| Full schema version table              | Alembic already embedded; drift unlikely.                                   |
| Encryption‑at‑rest (LUKS/EFS)          | All dev machines use OS disk encryption by default; duplication not needed. |

---

*Prepared by: AI Systems Architecture Team – v1.2 simplified yet hardened*



---

## Functional Decomposition

> *This section breaks the v1.2 design into nested, testable functions and sub‑functions.  It is appended without altering the prior FSD content.*

### 1 Prompt Intake & Validation

1.1 ``** handler**  → coordinator. 1.2 `validate_utf8(prompt)` → raises 400 if invalid. 1.3 `enforce_size(prompt, max_chars=8_000)`. 1.4 `auto_select_models(prompt)` if user omitted list. 1.5 `create_request_row(request_id, models)` in Postgres.

### 2 Concurrency & Provider Safety

2.1 `get_semaphore(provider)`  – concurrency guard. 2.2 `with_circuit_breaker(provider)` context → determines open/half‑open/closed. 2.3 `invoke_provider(model, prompt)` coroutine.

### 3 Token Generation Pipeline

3.1 `stream_tokens(sdk_response)`  – async generator. 3.2 `buffer.add(token)`  – in‑memory accumulation. 3.3 `if buffer.flush_needed(): persist_batch()`. 3.4 `on_error(provider_error) → mark_attempt_failed(); maybe_fallback()`.

### 4 Persistence Layer

4.1 `persist_batch(batch)`  – `COPY` to Postgres. 4.2 `on_copy_fail(batch)`  – `wal_write(batch, "tokens.wal")`. 4.3 Background `wal_replay_loop()` every 10 s when DB reachable.

### 5 Fallback Handling

5.1 `fallback_queue = [gpt‑3.5‑turbo, claude‑haiku, gemini‑flash, deepseek‑chat]`. 5.2 `apply_jitter(1–3 s)` before fallback call.

### 6 Health & Metrics

6.1 `collect_metrics()` – buffer\_len, wal\_size, flush\_ms. 6.2 `/health` endpoint serialises `collect_metrics()` with CB + DB status. 6.3 Optional `/metrics` Prometheus formatter.

### 7 Boot‑up & Consistency

7.1 `run_schema_migrations()` (Alembic). 7.2 `detect_token_gaps()` – SQL window query. 7.3 `wal_replay_loop()` kick‑off.

### 8 Graceful Shutdown

8.1 `signal_handler(SIGTERM)` – stop accepting requests. 8.2 `flush_buffer()` – write remaining tokens / WAL. 8.3 `close_connections()` – DB & HTTP clients.

### 9 Retention & Cleanup

9.1 Cron job `prune_tokens.sh`  – `DELETE … WHERE ts < now()‑180d`. 9.2 `rotate_wal_file(100 MiB)`.

### 10 Backup & Recovery

10.1 Daily `pg_dump` shell task. 10.2 Manual restore instructions: replay WAL‑Lite then `psql < dump`.

### 11 Administrative Controls

11.1 `GET /health` – quick status. 11.2 `GET /requests/{id}` – metadata + token stream link. 11.3 `POST /providers/{name}/enable|disable` – toggle provider.

*End of Functional Decomposition – v1.2.*

