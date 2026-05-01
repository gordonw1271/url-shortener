import redis as redis_pkg

from app import cache


def test_shorten_returns_201_and_prefixed_code(client):
    r = client.post("/shorten", json={"url": "https://example.com/page"})
    assert r.status_code == 201
    body = r.json()
    assert body["short_code"].startswith("a"), f"unexpected: {body['short_code']}"
    assert body["long_url"] == "https://example.com/page"
    assert body["short_url"].endswith("/" + body["short_code"])


def test_first_short_code_is_a1(client):
    r = client.post("/shorten", json={"url": "https://example.com/x"})
    assert r.json()["short_code"] == "a1"


def test_codes_advance_sequentially(client):
    codes = []
    for i in range(3):
        r = client.post("/shorten", json={"url": f"https://example.com/p{i}"})
        codes.append(r.json()["short_code"])
    assert codes == ["a1", "a2", "a3"]


def test_invalid_url_returns_422(client):
    r = client.post("/shorten", json={"url": "not-a-url"})
    assert r.status_code == 422


def test_redirect_302_to_long_url(client):
    r = client.post("/shorten", json={"url": "https://example.com/page"})
    code = r.json()["short_code"]
    r2 = client.get(f"/{code}", follow_redirects=False)
    assert r2.status_code == 302
    assert r2.headers["location"] == "https://example.com/page"


def test_unknown_short_code_returns_404(client):
    r = client.get("/no-such-code", follow_redirects=False)
    assert r.status_code == 404


def test_redirect_records_clicks(client):
    r = client.post("/shorten", json={"url": "https://example.com/page"})
    code = r.json()["short_code"]
    for _ in range(3):
        client.get(f"/{code}", follow_redirects=False)
    stats = client.get(f"/stats/{code}").json()
    assert stats["total_clicks"] == 3
    assert len(stats["recent"]) == 3


def test_stats_404_on_unknown(client):
    r = client.get("/stats/no-such-code")
    assert r.status_code == 404


def test_cache_populated_on_first_redirect(client, fake_redis):
    r = client.post("/shorten", json={"url": "https://example.com/page"})
    code = r.json()["short_code"]
    assert fake_redis.get(f"mapping:{code}") is None

    client.get(f"/{code}", follow_redirects=False)
    assert fake_redis.get(f"mapping:{code}") == "https://example.com/page"


def test_redirect_works_when_redis_dead(client, monkeypatch):
    """The whole point of graceful degradation: redirects must keep working
    even with no cache."""

    class Broken:
        def get(self, _key):
            raise redis_pkg.ConnectionError("dead")

        def setex(self, *_args, **_kw):
            raise redis_pkg.ConnectionError("dead")

    monkeypatch.setattr(cache, "_client", Broken())

    r = client.post("/shorten", json={"url": "https://example.com/page"})
    code = r.json()["short_code"]
    r2 = client.get(f"/{code}", follow_redirects=False)
    assert r2.status_code == 302
    assert r2.headers["location"] == "https://example.com/page"
