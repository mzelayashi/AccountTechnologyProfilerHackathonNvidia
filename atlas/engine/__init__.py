from .copilot import CopilotEngine, Session
from .pool import EnginePool, get_pool


def get_engine() -> Session:
    """Legacy single-engine accessor → slot 0 of the shared pool (one signed-in session)."""
    return get_pool().sessions[0]


__all__ = ["Session", "CopilotEngine", "EnginePool", "get_pool", "get_engine"]
