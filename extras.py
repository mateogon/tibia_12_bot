import time
from typing import Optional
import scipy.stats as stats
import difflib
from functools import wraps
lower, upper = -3, 6
mu, sigma = 2, 1
normal = stats.truncnorm((lower - mu) / sigma,
                         (upper - mu) / sigma, loc=mu, scale=sigma)
def timeInMillis():
    return time.time_ns()/1000000
def getNormalDelay():
    return normal.rvs(1)[0]*10
def similarString(seq1, seq2):
    return difflib.SequenceMatcher(a=seq1.lower(), b=seq2.lower()).ratio() > 0.748
def stringSimilarity(seq1, seq2):
    return difflib.SequenceMatcher(a=seq1.lower(), b=seq2.lower()).ratio()

def timeit(func):
    @wraps(func)
    def timeit_wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        total_time = end_time - start_time
        print(f'Function {func.__name__}{args} {kwargs} Took {total_time:.4f} seconds')
        return result
    return timeit_wrapper


def monotonic_ms() -> int:
    return time.monotonic_ns() // 1_000_000


class DelayManager:
    """
    Lightweight keyed timers (monotonic ms) to centralize throttles/cooldowns.

    - due(key): check without updating
    - allow(key): check and update (throttle)
    - trigger(key): update without checking (mark after success)
    """

    def __init__(self, now_ms_fn=None, default_jitter_ms_fn=None):
        self._now_ms_fn = now_ms_fn or monotonic_ms
        self._default_jitter_ms_fn = default_jitter_ms_fn
        self._defaults = {}  # key -> (base_ms, jitter_ms_fn)
        self._next_ms = {}   # key -> next allowed timestamp (ms)
        self._last_ms = {}   # key -> last trigger timestamp (ms)

    def now_ms(self) -> int:
        return int(self._now_ms_fn())

    def set_default(self, key: str, base_ms: int, jitter_ms_fn=None) -> None:
        self._defaults[key] = (int(base_ms), jitter_ms_fn)

    def _resolve_defaults(self, key: str, base_ms, jitter_ms_fn):
        if base_ms is None:
            base_ms, default_jitter = self._defaults[key]
            if jitter_ms_fn is None:
                jitter_ms_fn = default_jitter
        return int(base_ms), jitter_ms_fn

    def due(self, key: str, now_ms: Optional[int] = None) -> bool:
        now = self.now_ms() if now_ms is None else int(now_ms)
        return now >= int(self._next_ms.get(key, 0))

    def remaining_ms(self, key: str, now_ms: Optional[int] = None) -> int:
        now = self.now_ms() if now_ms is None else int(now_ms)
        return max(0, int(self._next_ms.get(key, 0)) - now)

    def last_ms(self, key: str, default: Optional[int] = None) -> Optional[int]:
        return self._last_ms.get(key, default)

    def elapsed_ms(self, key: str, now_ms: Optional[int] = None, default: int = 10**9) -> int:
        now = self.now_ms() if now_ms is None else int(now_ms)
        last = self._last_ms.get(key)
        if last is None:
            return int(default)
        return int(now - last)

    def trigger(self, key: str, base_ms: Optional[int] = None, *, jitter_ms_fn=None, now_ms: Optional[int] = None) -> None:
        base_ms, jitter_ms_fn = self._resolve_defaults(key, base_ms, jitter_ms_fn)
        now = self.now_ms() if now_ms is None else int(now_ms)

        jitter = 0
        fn = jitter_ms_fn if jitter_ms_fn is not None else self._default_jitter_ms_fn
        if fn is not None:
            try:
                jitter = int(fn())
            except Exception:
                jitter = 0

        self._last_ms[key] = now
        self._next_ms[key] = now + base_ms + jitter

    def allow(self, key: str, base_ms: Optional[int] = None, *, jitter_ms_fn=None, now_ms: Optional[int] = None) -> bool:
        if not self.due(key, now_ms=now_ms):
            return False
        self.trigger(key, base_ms=base_ms, jitter_ms_fn=jitter_ms_fn, now_ms=now_ms)
        return True

    def reset(self, key: str) -> None:
        self._next_ms.pop(key, None)
        self._last_ms.pop(key, None)
