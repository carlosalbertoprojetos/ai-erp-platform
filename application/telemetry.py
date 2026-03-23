from __future__ import annotations

import re
import threading
from collections import defaultdict


_METRIC_NAME_PATTERN = re.compile(r'[^a-zA-Z0-9_]')


class MetricsRegistry:
    def __init__(self):
        self._lock = threading.Lock()
        self._counters = defaultdict(int)
        self._latencies = defaultdict(float)

    def increment(self, key: str, amount: int = 1) -> None:
        with self._lock:
            self._counters[key] += amount

    def observe(self, key: str, value: float) -> None:
        with self._lock:
            self._latencies[key] += value

    def snapshot(self) -> dict:
        with self._lock:
            return {
                'counters': dict(self._counters),
                'latencies_ms_total': {key: round(value, 2) for key, value in self._latencies.items()},
            }

    def to_prometheus(self, namespace: str = 'coreflow') -> str:
        snapshot = self.snapshot()
        lines: list[str] = []
        for key, value in sorted(snapshot['counters'].items()):
            metric_name = _prometheus_metric_name(namespace, key, 'total')
            lines.append(f'# TYPE {metric_name} counter')
            lines.append(f'{metric_name} {value}')
        for key, value in sorted(snapshot['latencies_ms_total'].items()):
            metric_name = _prometheus_metric_name(namespace, key, 'milliseconds_total')
            lines.append(f'# TYPE {metric_name} counter')
            lines.append(f'{metric_name} {value}')
        return '\n'.join(lines) + ('\n' if lines else '')


def _prometheus_metric_name(namespace: str, key: str, suffix: str) -> str:
    base = f'{namespace}_{key}_{suffix}'.replace('.', '_').replace('-', '_')
    base = _METRIC_NAME_PATTERN.sub('_', base)
    base = re.sub(r'_+', '_', base).strip('_')
    return base.lower()
