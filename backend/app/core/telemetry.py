from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class Telemetry:
    request_count: Counter[tuple[str, str, int]] = field(default_factory=Counter)
    durations_ms: deque[float] = field(default_factory=lambda: deque(maxlen=5000))
    lock: Lock = field(default_factory=Lock)

    def record(self, method: str, path: str, status_code: int, duration_ms: float) -> None:
        normalised_path = self._normalise_path(path)
        with self.lock:
            self.request_count[(method, normalised_path, status_code)] += 1
            self.durations_ms.append(duration_ms)

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
            for (method, path, status_code), count in sorted(self.request_count.items()):
                lines.append(
                    "airlock_http_requests_total"
                    f'{{method="{method}",path="{path}",status="{status_code}"}} {count}'
                )
            durations = sorted(self.durations_ms)
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
        return "\n".join(lines) + "\n"


telemetry = Telemetry()
