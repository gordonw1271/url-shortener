import fakeredis
import pytest
import redis

from app import cache


@pytest.fixture
def fake(monkeypatch):
    f = fakeredis.FakeStrictRedis(decode_responses=True)
    monkeypatch.setattr(cache, "_client", f)
    return f


def test_get_miss_returns_none(fake):
    assert cache.get("nonexistent") is None


def test_put_then_get(fake):
    cache.put("a1", "https://example.com")
    assert cache.get("a1") == "https://example.com"


def test_put_sets_default_ttl(fake):
    cache.put("a1", "https://example.com")
    ttl = fake.ttl("mapping:a1")
    # SETEX stores whole seconds, so a wall-clock tick between put() and
    # ttl() can shave one off. Allow a small tolerance.
    assert cache.CACHE_TTL_SECONDS - 2 <= ttl <= cache.CACHE_TTL_SECONDS


def test_put_custom_ttl(fake):
    cache.put("a1", "https://example.com", ttl=60)
    assert 58 <= fake.ttl("mapping:a1") <= 60


def test_key_namespacing(fake):
    """Cache keys are prefixed with `mapping:` so they don't collide with
    other Redis users (queues, sessions, etc.)."""
    cache.put("a1", "https://example.com")
    assert fake.exists("mapping:a1") == 1
    assert fake.exists("a1") == 0


def test_get_swallows_redis_error(monkeypatch):
    """A Redis outage on the read path returns None, never raises."""

    class Broken:
        def get(self, _key):
            raise redis.ConnectionError("fake outage")

    monkeypatch.setattr(cache, "_client", Broken())
    assert cache.get("a1") is None


def test_put_swallows_redis_error(monkeypatch):
    """A Redis outage on the write path is silent — caller can't tell."""

    class Broken:
        def setex(self, *_args, **_kw):
            raise redis.ConnectionError("fake outage")

    monkeypatch.setattr(cache, "_client", Broken())
    cache.put("a1", "https://example.com")  # must not raise
