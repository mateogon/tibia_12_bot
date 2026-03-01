"""Performance aggregation and reporting for bot main loop."""

from __future__ import annotations

import time
from typing import Dict


class PerfTracker:
    """Collects per-cycle timings and prints 1s rolling reports."""

    def __init__(self) -> None:
        self._last_t = time.perf_counter()
        self._last_count = 0
        self._samples = 0
        self._totals_ms: Dict[str, float] = {}

    def add_span(self, name: str, t0: float) -> None:
        dt_ms = (time.perf_counter() - t0) * 1000.0
        self._totals_ms[name] = self._totals_ms.get(name, 0.0) + dt_ms

    def add_value_ms(self, name: str, value_ms: float) -> None:
        self._totals_ms[name] = self._totals_ms.get(name, 0.0) + float(value_ms)

    def add_sample(self) -> None:
        self._samples += 1

    def report_if_due(self, cycle_count: int) -> None:
        now = time.perf_counter()
        dt = now - self._last_t
        if dt < 1.0:
            return

        cps = (cycle_count - self._last_count) / dt
        avg_frame_ms = self._totals_ms.get("frame_total", 0.0) / max(self._samples, 1)
        print(f"[PERF] cycles/s={cps:.1f} avg_frame_ms={avg_frame_ms:.2f}")

        total_ms_window = self._totals_ms.get("frame_total", 0.0)
        ranked = []
        for k, v in self._totals_ms.items():
            if k in {"frame_total", "bg_throttled_frames"}:
                continue
            avg_ms = v / max(self._samples, 1)
            share = (v / total_ms_window * 100.0) if total_ms_window > 0 else 0.0
            ranked.append((v, k, avg_ms, share))

        ranked.sort(reverse=True)
        top = ranked[:8]
        if top:
            top_line = " | ".join([f"{k}:{avg_ms:.2f}ms({share:.0f}%)" for _, k, avg_ms, share in top])
            print(f"[PERF] top: {top_line}")

        if "bg_throttled_frames" in self._totals_ms:
            throttled = self._totals_ms["bg_throttled_frames"]
            print(f"[PERF] bg_throttled={int(throttled)}/{self._samples}")

        self._last_t = now
        self._last_count = cycle_count
        self._samples = 0
        self._totals_ms = {}
