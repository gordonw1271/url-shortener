# url-shortener

A URL shortener built incrementally as a system-design learning exercise.
Each phase adds one concept from the [System Design School URL shortener
solution](https://systemdesignschool.io/problems/url-shortener/solution).

| Phase | Status | Adds |
|---|---|---|
| 1. MVP | ✅ done | FastAPI + SQLite, base62 counter encoding |
| 2. Analytics split | ✅ done | Separate `clicks` table, fire-and-forget writes on redirect |
| 3. Cache | ✅ done | Redis read-through cache, graceful degradation |
| **4. Sharding sim** | ✅ current | Postgres + machine-ID prefix, two app replicas behind nginx |
| 5. Polish | planned | Dockerfile, tests, CI, architecture diagrams |

## What's here

- `POST /shorten` — mints a short code prefixed with this instance's `MACHINE_ID`
- `GET /{short_code}` — read-through Redis cache → Postgres on miss → 302 redirect → background click write
- `GET /stats/{short_code}` — total clicks + 10 most recent (timestamp, IP, user-agent, referer)
- **Postgres** holds `url_mappings` + `clicks` + per-machine `seq_<id>` sequences
- **Redis** caches `mapping:<code>` → long URL with 1-day TTL
- **nginx** on port 8000 round-robins POSTs across two `uvicorn` instances on 8001 and 8002
- Swagger UI per instance at `/docs`; cache UI at 8082, DB UI at 8083

### Design choices

**(Phase 1) Base62 counter encoding.** A counter (auto-increment in Phase 1,
per-machine sequence in Phase 4) is encoded into a URL-safe alphanumeric
string. Collision-free by construction — no hash collisions to handle, no
retry loops. Tradeoff: short codes are sequential and guessable, which leaks
how many URLs you've shortened.

**(Phase 1) 302 instead of 301 redirects.** A 301 (permanent) is cached
aggressively by browsers, so subsequent clicks bypass the server. We need
every click to reach us so the analytics row gets written. 302 is non-cached.

**(Phase 1) FastAPI + SQLAlchemy + SQLite.** FastAPI gives auto-generated
Swagger UI at `/docs` so you can hand-drive every endpoint. SQLAlchemy keeps
the ORM code identical when the connection string swaps from SQLite to
Postgres in Phase 4. SQLite was the perfect day-one DB — a single file you
could open in `sqlite-web` to *see the data* — and the only thing that
changed in Phase 4 was the `DATABASE_URL`.

**(Phase 2) Separate `clicks` table.** Redirects are read-heavy, analytics
are write-heavy. Splitting them means a redirect's INSERT goes to a
different table from the SELECT — no row-level contention, and we can scale
them independently later. One row per click (richer than a counter).

**(Phase 2) Fire-and-forget click writes.** The redirect handler returns
the 302 *before* the click row is written. FastAPI's `BackgroundTasks`
schedules the INSERT to run after the response is sent. Tradeoff: a crash
between response and INSERT loses one click. Acceptable for analytics;
unacceptable for billing.

**(Phase 3) Read-through Redis cache.** Redirect handler asks Redis first
(`mapping:{code}` → long URL). On miss it reads Postgres and populates the
cache. Mappings are immutable, so no invalidation needed — we still set a
1-day TTL to evict cold entries.

**(Phase 3) Graceful degradation.** Every Redis call is wrapped in
try/except. If Redis is down, latency degrades but the app keeps working.
Cache is an optimization, never a hard dependency.

**(Phase 3) Read-through, not write-through.** We don't pre-populate the
cache when a URL is shortened — only when it's first *clicked*. Most
shortened URLs are never clicked, so write-through wastes memory.

**(Phase 4) Machine-ID prefix.** Each instance has a single-character
`MACHINE_ID` (`a`, `b`, ...). Short codes are `MACHINE_ID + base62(seq)`,
where `seq` comes from a Postgres `SEQUENCE` named per machine
(`seq_a`, `seq_b`). Two writers mint codes in disjoint keyspaces — no
distributed lock, no central counter. The prefix also doubles as a
"shard key": in real systems with physically separate DBs, the first
character of the short code tells you which shard owns it.

**(Phase 4) nginx round-robin.** A single entrypoint on port 8000 spreads
load across both replicas. Either replica can serve any GET because they
share Postgres + Redis (logical sharding — physical sharding would split
the DB by prefix, kept as a future exercise).

## Run it

```bash
python -m venv .venv
.venv\Scripts\activate     # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

Then four terminals:

```bash
# terminal 1 — infra (postgres, redis, redis-commander, adminer, nginx)
docker compose up

# terminal 2 — instance "a" on port 8001  (Windows cmd)
set MACHINE_ID=a&& uvicorn app.main:app --reload --port 8001

# terminal 3 — instance "b" on port 8002
set MACHINE_ID=b && uvicorn app.main:app --reload --port 8002
```

| URL | What it is |
|---|---|
| <http://localhost:8000/docs> | API via nginx (round-robins between A and B) |
| <http://localhost:8001/docs> | Direct hit on instance A |
| <http://localhost:8002/docs> | Direct hit on instance B |
| <http://localhost:8082> | redis-commander (cache visualizer) |
| <http://localhost:8083> | Adminer (Postgres viewer — server `postgres`, user/pwd/db all `shortener`) |

### Try it

1. POST `/shorten` to <http://localhost:8000/shorten> a few times. Watch the
   short codes alternate prefixes — `a1`, `b1`, `a2`, `b2`, ... — proving
   nginx round-robins and each instance pulls from its own counter.
2. In Adminer, browse `url_mappings` to see all rows in one Postgres DB,
   and run `SELECT * FROM information_schema.sequences` to see `seq_a` and
   `seq_b`.
3. Hit a short URL through nginx (`http://localhost:8000/<code>`) — either
   instance can serve it. Watch both uvicorn terminals: only one logs the
   request.
4. Stop one of the uvicorn instances. Keep hitting nginx. Requests still
   succeed (nginx routes around the dead upstream). That's the load-
   balancer-as-failover bonus lesson.

If you skip Docker entirely, the app won't start (Postgres isn't optional in
Phase 4). Redis is still optional — kill its container and you'll just see
`degrading to DB` warnings.
