from __future__ import annotations

from application.resilience import CircuitBreaker, CircuitBreakerOpenError, retry_sync
from application.security import RateLimiter, RedisRateLimiter
from application.telemetry import MetricsRegistry
from application.tracing import TracerAdapter


class _FakeRedisPipeline:
    def __init__(self, client):
        self.client = client
        self.operations = []

    def incr(self, key):
        self.operations.append(("incr", key, None))
        return self

    def expire(self, key, ttl):
        self.operations.append(("expire", key, ttl))
        return self

    def ttl(self, key):
        self.operations.append(("ttl", key, None))
        return self

    def execute(self):
        results = []
        for operation, key, value in self.operations:
            if operation == "incr":
                self.client.counters[key] = self.client.counters.get(key, 0) + 1
                results.append(self.client.counters[key])
            elif operation == "expire":
                self.client.ttls[key] = value
                results.append(True)
            elif operation == "ttl":
                results.append(self.client.ttls.get(key, 1))
        return results


class _FakeRedisClient:
    def __init__(self):
        self.counters = {}
        self.ttls = {}

    def pipeline(self):
        return _FakeRedisPipeline(self)


class _BrokenRedisClient:
    def pipeline(self):
        raise RuntimeError("redis unavailable")


def test_redis_rate_limiter_enforces_limit():
    limiter = RedisRateLimiter(_FakeRedisClient(), prefix="test")

    assert limiter.check("client-a", 2, 60) == (True, 0)
    assert limiter.check("client-a", 2, 60) == (True, 0)
    allowed, retry_after = limiter.check("client-a", 2, 60)

    assert allowed is False
    assert retry_after >= 1


def test_redis_rate_limiter_falls_back_to_memory():
    limiter = RedisRateLimiter(_BrokenRedisClient(), fallback=RateLimiter())

    assert limiter.check("client-b", 1, 60) == (True, 0)
    allowed, retry_after = limiter.check("client-b", 1, 60)

    assert allowed is False
    assert retry_after >= 1


def test_metrics_registry_renders_prometheus():
    metrics = MetricsRegistry()
    metrics.increment("http.requests", 3)
    metrics.observe("http.duration_ms", 12.5)

    payload = metrics.to_prometheus("coreflow")

    assert "coreflow_http_requests_total 3" in payload
    assert "coreflow_http_duration_ms_milliseconds_total 12.5" in payload


def test_tracer_adapter_preserves_incoming_trace_id():
    tracer = TracerAdapter(service_name="coreflow-test", enabled=True)
    handle = tracer.start_span("GET /health", incoming_traceparent="00-0123456789abcdef0123456789abcdef-1111111111111111-01")

    assert handle.context.trace_id == "0123456789abcdef0123456789abcdef"
    assert handle.context.traceparent.startswith("00-0123456789abcdef0123456789abcdef-")


def test_retry_and_circuit_breaker_open_after_failures():
    attempts = {"count": 0}

    def flaky():
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise RuntimeError("temporary failure")
        return "ok"

    assert retry_sync(flaky, attempts=2, backoff_seconds=0) == "ok"

    breaker = CircuitBreaker("test-breaker", failure_threshold=1, recovery_timeout_seconds=60)

    try:
        breaker.execute(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    except RuntimeError:
        pass

    try:
        breaker.execute(lambda: "never")
    except CircuitBreakerOpenError:
        pass
    else:
        raise AssertionError("Circuit breaker should be open after failure threshold is reached.")
