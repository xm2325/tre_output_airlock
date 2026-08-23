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
    database_pool_checkout_timeouts: int = 0
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

    def record_database_pool_checkout_timeout(self) -> None:
        with self.lock:
            self.database_pool_checkout_timeouts += 1

    @staticmethod
    def _normalise_path(path: str) -> str:
        parts = path.split("/")
        return "/".join(
            "{id}" if len(part) == 36 and part.count("-") == 4 else part for part in parts
        )

    def prometheus(self) -> str:
        # Import lazily so this module stays independent of SQLAlchemy during import.
        from app.db import database_pool_snapshot

        database_pool = database_pool_snapshot()
        lines = [
            "# HELP airlock_http_requests_total HTTP requests handled by the demo service.",
            "# TYPE airlock_http_requests_total counter",
        ]
        with self.lock:
            request_count = self.request_count.copy()
            durations = sorted(self.durations_ms)
            oidc_count = self.oidc_count.copy()
            oidc_durations = sorted(self.oidc_upstream_durations_ms)
            database_pool_checkout_timeouts = self.database_pool_checkout_timeouts

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
                (
                    "# HELP airlock_oidc_upstream_duration_ms "
                    "Recent IdP introspection latency summary."
                ),
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

        if database_pool is not None:
            lines.extend(
                [
                    (
                        "# HELP airlock_database_pool_configured_size "
                        "Persistent connections configured per API process."
                    ),
                    "# TYPE airlock_database_pool_configured_size gauge",
                    f"airlock_database_pool_configured_size {database_pool.configured_size}",
                    (
                        "# HELP airlock_database_pool_max_overflow "
                        "Additional overflow connections allowed per API process."
                    ),
                    "# TYPE airlock_database_pool_max_overflow gauge",
                    f"airlock_database_pool_max_overflow {database_pool.max_overflow}",
                    (
                        "# HELP airlock_database_pool_capacity "
                        "Maximum connections available to this API process."
                    ),
                    "# TYPE airlock_database_pool_capacity gauge",
                    f"airlock_database_pool_capacity {database_pool.capacity}",
                    (
                        "# HELP airlock_database_pool_checked_out "
                        "Connections currently checked out by this API process."
                    ),
                    "# TYPE airlock_database_pool_checked_out gauge",
                    f"airlock_database_pool_checked_out {database_pool.checked_out}",
                    (
                        "# HELP airlock_database_pool_checked_in "
                        "Established persistent connections currently idle."
                    ),
                    "# TYPE airlock_database_pool_checked_in gauge",
                    f"airlock_database_pool_checked_in {database_pool.checked_in}",
                    (
                        "# HELP airlock_database_pool_overflow_open "
                        "Open connections above the persistent pool size."
                    ),
                    "# TYPE airlock_database_pool_overflow_open gauge",
                    f"airlock_database_pool_overflow_open {database_pool.overflow_open}",
                    (
                        "# HELP airlock_database_pool_available "
                        "Remaining checkout capacity in this API process."
                    ),
                    "# TYPE airlock_database_pool_available gauge",
                    f"airlock_database_pool_available {database_pool.available}",
                    (
                        "# HELP airlock_database_pool_utilisation_ratio "
                        "Checked-out connections divided by total pool capacity."
                    ),
                    "# TYPE airlock_database_pool_utilisation_ratio gauge",
                    (
                        "airlock_database_pool_utilisation_ratio "
                        f"{database_pool.utilisation_ratio:.6f}"
                    ),
                    (
                        "# HELP airlock_database_pool_checkout_timeouts_total "
                        "Requests that timed out waiting for a database connection."
                    ),
                    "# TYPE airlock_database_pool_checkout_timeouts_total counter",
                    (
                        "airlock_database_pool_checkout_timeouts_total "
                        f"{database_pool_checkout_timeouts}"
                    ),
                ]
            )

        return "\n".join(lines) + "\n"


telemetry = Telemetry()
