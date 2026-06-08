"""ATLAS Brain — the orchestration layer (facilitator agent + brainwaves).

Today this package ships the **capability manifest** (`capabilities.py`): the single, machine-readable
source of truth for everything ATLAS can and cannot do. The future Brain runtime (planner + sub-agent
fan-out + brainwave threads) introspects this manifest to decide, for any goal, whether it can do it
(route to a skill), cannot (research + recommend a new skill), or whether it's a settings change it can
only point the user to. See ATLAS_ARCHITECTURE.md for the full design and roadmap.
"""
from atlas.brain import capabilities  # noqa: F401
