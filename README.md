# url-shortener

A URL shortener built incrementally as a system-design learning exercise.
Each phase adds one concept from the [System Design School URL shortener
solution](https://systemdesignschool.io/problems/url-shortener/solution).

| Phase | Status | Adds |
|---|---|---|
| **1. MVP** | ✅ current | FastAPI + SQLite, base62 counter encoding, sqlite-web for DB visibility |
| 2. Analytics split | planned | Separate `clicks` table, fire-and-forget writes on redirect |
| 3. Cache | planned | Redis read-through cache, docker-compose |
| 4. Sharding sim | planned | Postgres + machine-ID prefix, two app replicas behind nginx |
| 5. Polish | planned | Dockerfile, tests, CI, architecture diagrams |

## Phase 1 — what's here

- `POST /shorten` — accepts a long URL, returns a short code
- `GET /{short_code}` — 302-redirects to the long URL
- SQLite at `data/shortener.db`, viewable in your browser via `sqlite-web`
- Swagger UI at `/docs` for hand-driving traffic

### Design choices

**Base62 counter encoding.** The DB's auto-increment `id` is the counter; the
short code is `base62(id)`. This is collision-free by construction — no hash
collisions to handle, no retry loops. Tradeoff: short codes are sequential
and guessable, which leaks how many URLs you've shortened. Real shorteners
add a random offset or scramble the counter; we'll ignore that for now.

**302 instead of 301 redirects.** A 301 (permanent) is cached aggressively by
browsers, so subsequent clicks bypass the server. Phase 2 needs every click
to hit us so we can record analytics, so 302 sets us up for that.

**SQLite + SQLAlchemy.** SQLite is a single file you can open in any tool;
SQLAlchemy keeps the model code identical when we switch to Postgres in
Phase 4. The point of Phase 1 is to **see the data** — sqlite-web makes
every row visible.

## Run it

```bash
python -m venv .venv
.venv\Scripts\activate     # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
```

Two terminals (venv activated in both):

```bash
# terminal 1 — the API
uvicorn app.main:app --reload --port 8000

# terminal 2 — the DB visualizer
python -m sqlite_web --port 8081 data/shortener.db
```

- API + Swagger: <http://localhost:8000/docs>
- DB visualizer: <http://localhost:8081>

### Try it

1. Open <http://localhost:8000/docs>, expand `POST /shorten`, click **Try it
   out**, paste a URL, **Execute**.
2. Copy the `short_code` from the response.
3. Refresh sqlite-web — your row is there.
4. Visit `http://localhost:8000/<short_code>` — you'll be redirected.
