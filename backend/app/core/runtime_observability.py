"""Bounded in-process observability for EFHC HTTP runtime.

The module stores aggregate request facts only. It never stores request
bodies, query strings, Telegram init data, wallet proofs, or secrets.
"""

from __future__ import annotations

import re
from collections import Counter, deque
from dataclasses import dataclass
from threading import Lock
from typing import Any

from app.lib.time import utcnow

_ID_SEGMENT = re.compile(
    r"^(?:\d+|[0-9a-f]{16,}|[0-9a-f-]{32,})$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RequestObservation:
    """One safe request timing observation."""

    method: str
    route: str
    status_code: int
    duration_ms: float


def normalize_route(path: str) -> str:
    """Collapse identifier-like path segments into ``:id``."""
    clean = str(path or "/").split("?", 1)[0]
    segments = []
    for part in clean.split("/"):
        if not part:
            continue
        segments.append(":id" if _ID_SEGMENT.match(part) else part)
    return "/" + "/".join(segments)


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(
        len(ordered) - 1,
        max(0, int(round((len(ordered) - 1) * ratio))),
    )
    return round(ordered[index], 2)


class RuntimeObservabilityRegistry:
    """Thread-safe bounded request metrics registry."""

    def __init__(self, max_samples: int = 1000) -> None:
        self._lock = Lock()
        self._started_at = utcnow()
        self._samples: deque[RequestObservation] = deque(
            maxlen=max(100, int(max_samples)),
        )
        self._status_counts: Counter[str] = Counter()
        self._route_counts: Counter[str] = Counter()
        self._total_requests = 0

    def record(
        self,
        *,
        method: str,
        route: str,
        status_code: int,
        duration_ms: float,
    ) -> None:
        observation = RequestObservation(
            method=str(method or "GET").upper()[:12],
            route=normalize_route(route),
            status_code=int(status_code),
            duration_ms=max(0.0, round(float(duration_ms), 2)),
        )
        status_class = f"{observation.status_code // 100}xx"
        route_key = f"{observation.method} {observation.route}"
        with self._lock:
            self._samples.append(observation)
            self._status_counts[status_class] += 1
            self._route_counts[route_key] += 1
            self._total_requests += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            samples = list(self._samples)
            status_counts = dict(self._status_counts)
            route_counts = self._route_counts.most_common(20)
            total_requests = self._total_requests
        durations = [item.duration_ms for item in samples]
        recent_5xx = sum(
            1 for item in samples if item.status_code >= 500
        )
        recent_4xx = sum(
            1 for item in samples if 400 <= item.status_code < 500
        )
        sample_count = len(samples)
        error_ratio = (
            recent_5xx / sample_count if sample_count else 0.0
        )
        p95 = _percentile(durations, 0.95)
        alerts = []
        if sample_count >= 20 and error_ratio >= 0.05:
            alerts.append(
                {
                    "id": "HTTP_5XX_RATIO_HIGH",
                    "severity": "critical",
                    "value": round(error_ratio, 4),
                }
            )
        if sample_count >= 10 and p95 >= 1500.0:
            alerts.append(
                {
                    "id": "HTTP_P95_LATENCY_HIGH",
                    "severity": "warning",
                    "value": p95,
                }
            )
        now = utcnow()
        return {
            "ok": not any(
                item["severity"] == "critical" for item in alerts
            ),
            "generated_at_epoch": round(now.timestamp(), 3),
            "uptime_sec": round((now - self._started_at).total_seconds(), 2),
            "total_requests": total_requests,
            "sample_count": sample_count,
            "status_counts": status_counts,
            "recent_4xx": recent_4xx,
            "recent_5xx": recent_5xx,
            "latency_ms": {
                "p50": _percentile(durations, 0.50),
                "p95": p95,
                "p99": _percentile(durations, 0.99),
                "max": round(max(durations), 2) if durations else 0.0,
            },
            "top_routes": [
                {"route": route, "requests": count}
                for route, count in route_counts
            ],
            "alerts": alerts,
            "privacy": {
                "request_bodies_stored": False,
                "query_strings_stored": False,
                "identifiers_normalized": True,
            },
        }


runtime_observability = RuntimeObservabilityRegistry()
