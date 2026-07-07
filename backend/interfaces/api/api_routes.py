from __future__ import annotations

from backend.interfaces.api.shared import api_bp

# Import route modules for their decorators on the shared api_bp.
from backend.interfaces.api import auth_routes  # noqa: F401
from backend.interfaces.api import control_routes  # noqa: F401
from backend.interfaces.api import diagnostics_routes  # noqa: F401
from backend.interfaces.api import estop_routes  # noqa: F401
from backend.interfaces.api import export_routes  # noqa: F401
from backend.interfaces.api import replay_routes  # noqa: F401
from backend.interfaces.api import runtime_control_routes  # noqa: F401
from backend.interfaces.api import robot_routes  # noqa: F401
from backend.interfaces.api import setup_routes  # noqa: F401
from backend.interfaces.api import state_routes  # noqa: F401
from backend.interfaces.api import vision_routes  # noqa: F401


__all__ = ["api_bp"]
