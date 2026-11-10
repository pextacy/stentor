"""Platform middleware: operator token, rate limit, request id, Server-Timing, metrics."""
from __future__ import annotations

import hmac
import threading
import time
import uuid
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
BUCKETS = (0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10)


class Metrics:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.counters: dict[tuple[str, tuple], float] = defaultdict(float)
        self.hist: dict[tuple, list[float]] = {}

    def inc(self, name: str, value: float = 1, **labels: str) -> None:
        with self.lock:
            self.counters[(name, tuple(sorted(labels.items())))] += value

    def observe(self, seconds: float, **labels: str) -> None:
        key = tuple(sorted(labels.items()))
        with self.lock:
            h = self.hist.setdefault(key, [0.0] * (len(BUCKETS) + 2))  # buckets..., count, sum
            for i, b in enumerate(BUCKETS):
                if seconds <= b:
                    h[i] += 1
            h[-2] += 1
            h[-1] += seconds

    def reset(self) -> None:
        with self.lock:
            self.counters.clear()
            self.hist.clear()

    def render(self) -> str:
        def lab(items) -> str:
            return "{" + ",".join(f'{k}="{v}"' for k, v in items) + "}" if items else ""

        lines: list[str] = []
        with self.lock:
            names = sorted({n for n, _ in self.counters})
            for n in names:
                lines.append(f"# TYPE {n} counter")
                for (name, labels), v in sorted(self.counters.items()):
                    if name == n:
                        lines.append(f"{n}{lab(labels)} {v:g}")
            if self.hist:
                lines.append("# TYPE stentor_request_seconds histogram")
                for labels, h in sorted(self.hist.items()):
                    for i, b in enumerate(BUCKETS):
                        lines.append(f"stentor_request_seconds_bucket{lab(labels + (('le', f'{b:g}'),))} {h[i]:g}")
                    lines.append(f"stentor_request_seconds_bucket{lab(labels + (('le', '+Inf'),))} {h[-2]:g}")
                    lines.append(f"stentor_request_seconds_count{lab(labels)} {h[-2]:g}")
                    lines.append(f"stentor_request_seconds_sum{lab(labels)} {h[-1]:.6f}")
        return "\n".join(lines) + "\n"


METRICS = Metrics()


class RateLimiter:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str, limit: int, window: float = 60.0) -> tuple[bool, int]:
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                return False, max(1, int(window - (now - q[0])) + 1)
            q.append(now)
            return True, 0

    def reset(self) -> None:
        with self.lock:
            self.hits.clear()


LIMITER = RateLimiter()


def install(app: FastAPI, get_settings) -> None:
    """Call before adding CORS, so CORS stays the outermost layer and every
    refusal (401, 429) still carries CORS headers the browser can read."""

    @app.middleware("http")
    async def platform(request: Request, call_next):
        settings = get_settings()
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        t0 = time.perf_counter()
        method = request.method
        is_write = method in WRITE_METHODS

        def done(resp: Response, route: str) -> Response:
            dt = time.perf_counter() - t0
            resp.headers["X-Request-ID"] = rid
            resp.headers["Server-Timing"] = f"app;dur={dt * 1000:.1f}"
            METRICS.inc("stentor_requests_total", method=method, route=route, status=str(resp.status_code))
            METRICS.observe(dt, route=route)
            return resp

        if is_write and settings.stentor_operator_token:
            auth = request.headers.get("authorization", "")
            token = auth[7:] if auth.lower().startswith("bearer ") else ""
            if not hmac.compare_digest(token, settings.stentor_operator_token):
                return done(JSONResponse({"detail": "operator token required for this action"}, status_code=401,
                                         headers={"WWW-Authenticate": "Bearer"}), "unauthorized")
        if is_write and settings.stentor_rate_limit > 0:
            client = request.client.host if request.client else "unknown"
            ok, retry = LIMITER.allow(client, settings.stentor_rate_limit)
            if not ok:
                return done(JSONResponse({"detail": "too many requests; slow down"}, status_code=429,
                                         headers={"Retry-After": str(retry)}), "rate_limited")
        resp = await call_next(request)
        route = getattr(request.scope.get("route"), "path", "unmatched")
        return done(resp, route)
