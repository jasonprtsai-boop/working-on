import importlib
import os
import sys


sys.path.append(os.getcwd())


def test_module(name: str):
    try:
        print(f"Testing {name} ...")
        importlib.import_module(name)
        print(f"SUCCESS: {name}")
    except Exception as exc:
        print(f"FAILURE: {name} - {exc}")


MODULES = [
    "backend.main",
    "backend.utils.config",
    "backend.application.bootstrap",
    "backend.application.services.engine_service",
    "backend.application.services.game_service",
    "backend.application.services.robot_facade",
    "backend.infrastructure.vision.vision_system",
    "backend.interfaces.api.api_routes",
    "backend.interfaces.websocket.socket_handler",
    "backend.runtime.workers.persistence_worker",
]


if __name__ == "__main__":
    for module_name in MODULES:
        test_module(module_name)
