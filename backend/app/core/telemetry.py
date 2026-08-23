from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class Telemetry:
    request_count: Counter[tuple[str, str, int]] = field(default_factory=Counter)
    durations_ms: deque[float] = field(default_factory=lambda: deque(maxlen=5000))
    oidc_count: Counter[str] = field(default_factory=Counter)
    oidc_upstream_durations_ms: deque[float] = field(default_factory=lambda: deque(maxlen=5000))
    lock: Lock = field(default_factory=Lock)

    def record(self, method: str, path: str, status_code: int, duration_ms: float) -> None:
        normalised_path = self._normalise_path(path)
        with self.lock:
            self.request_count[(method, normalised_path, status_code)] += 1
            self.durations_ms.append(duration_ms)

    def record_oidc(self, outcome: str, duration_ms: float | None = None) -> None:
        with self.lock:
            self.oidc_count[outcome] += 1
            if duration_ms is not None:
                self.oidc_upstream_durations_ms.append(duration_ms)

    @staticmethod
    def _normalise_path(path: str) -> str:
        parts = path.split("/")
        return "/".join(
            "{id}" if len(part) == 36 and part.count("-") == 4 else part for part in parts
        )

    def prometheus(self) -> str:
        lines = [
            "# HELP airlock_http_requests_total HTTP requests handled by the demo service.",
            "# TYPE airlock_http_requests_total counter",
        ]
        with self.lock:
            request_count = self.request_count.copy()
            durations = sorted(self.durations_ms)
            oidc_count = self.oidc_count.copy()
            oidc_durations = sorted(self.oidc_upstream_durations_ms)

        for (method, path, status_code), count in sorted(request_count.items()):
            lines.append(
                "airlock_http_requests_total"
                f'{{method="{method}",path="{path}",status="{status_code}"}} {count}'
            )

        lines.extend(
            [
                "# HELP airlock_http_request_duration_ms Recent request duration summary.",
                "# TYPE airlock_http_request_duration_ms gauge",
            ]
        )
        if durations:
            for label, quantile in (("p50", 0.50), ("p95", 0.95), ("p99", 0.99)):
                index = min(len(durations) - 1, int((len(durations) - 1) * quantile))
                lines.append(
                    f'airlock_http_request_duration_ms{{quantile="{label}"}} {durations[index]:.3f}'
                )
        else:
            lines.append('airlock_http_request_duration_ms{quantile="p50"} 0')

        lines.extend(
            [
                "# HELP airlock_oidc_events_total OIDC cache and introspection outcomes.",
                "# TYPE airlock_oidc_events_total counter",
            ]
        )
        for outcome, count in sorted(oidc_count.items()):
            lines.append(f'airlock_oidc_events_total{{outcome="{outcome}"}} {count}')

        lines.extend(
            [
                "# HELP airlock_oidc_upstream_duration_ms Recent IdP introspection latency summary.",
                "# TYPE airlock_oidc_upstream_duration_ms gauge",
            ]
        )
        if oidc_durations:
            for label, quantile in (("p50", 0.50), ("p95", 0.95), ("p99", 0.99)):
                index = min(len(oidc_durations) - 1, int((len(oidc_durations) - 1) * quantile))
                lines.append(
                    "airlock_oidc_upstream_duration_ms"
                    f'{{quantile="{label}"}} {oidc_durations[index]:.3f}'
                )
        else:
            lines.append('airlock_oidc_upstream_duration_ms{quantile="p50"} 0')
        return "\n".join(lines) + "\n"


telemetry = Telemetry()
