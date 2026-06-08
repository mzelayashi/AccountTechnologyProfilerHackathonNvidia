"""A pool of independent Copilot browser sessions — one Chrome process per slot.

Each slot has its OWN profile dir (chrome_profile_0..N-1), cloned once from the user's
signed-in `cache/chrome_profile` seed so the M365 session carries over without re-login
(same Windows user → the DPAPI key that encrypts the cookies copies fine). Independent
profiles let the slots run in true parallel without fighting over one profile lock.
"""
from __future__ import annotations

import shutil
import threading

import config

from .copilot import Session

POOL_SIZE = int(getattr(config, "POOL_SIZE", 4) or 4)

# Skip the big, regenerable caches when cloning — we only need cookies/tokens/prefs.
_IGNORE = shutil.ignore_patterns(
    "Cache", "Code Cache", "GPUCache", "ShaderCache", "GrShaderCache",
    "Service Worker", "Crashpad", "component_crx_cache", "extensions_crx_cache",
    "Singleton*",
)


def _slot_dir(i: int):
    base = config.CHROME_PROFILE_DIR
    return base.parent / f"{base.name}_{i}"


def _clone_seed(dst) -> None:
    """Clone the signed-in seed profile into a slot dir if it doesn't exist yet."""
    if dst.exists():
        return
    seed = config.CHROME_PROFILE_DIR
    try:
        if seed.exists() and any(seed.iterdir()):
            shutil.copytree(seed, dst, ignore=_IGNORE)
            print(f"[pool] cloned signed-in profile -> {dst.name}", flush=True)
            return
    except Exception as e:  # noqa: BLE001
        print(f"[pool] clone {dst.name} failed ({e}); starting it empty", flush=True)
    dst.mkdir(parents=True, exist_ok=True)


class EnginePool:
    """Holds N independent Sessions. Slot 0 doubles as the legacy single engine."""

    def __init__(self, size: int = POOL_SIZE) -> None:
        self.sessions: list[Session] = []
        for i in range(size):
            d = _slot_dir(i)
            _clone_seed(d)
            self.sessions.append(Session(profile_dir=d, idx=i))

    def __len__(self) -> int:
        return len(self.sessions)

    def close_all(self) -> None:
        for s in self.sessions:
            try:
                s.close()
            except Exception:
                pass


_pool: EnginePool | None = None
_lock = threading.Lock()


def get_pool() -> EnginePool:
    global _pool
    with _lock:
        if _pool is None:
            _pool = EnginePool()
        return _pool
