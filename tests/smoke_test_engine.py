import asyncio
import os
import sys

sys.path.append(os.getcwd())

from backend.application.services.engine_service import EngineService
from backend.utils import config


async def smoke_test_pikafish():
    print("=== Pikafish Engine Smoke Test ===")
    engine_path = os.path.abspath(config.ENGINE_PATH)
    nnue_path = os.path.abspath(config.NNUE_PATH)
    print(f"Testing engine at: {engine_path}")
    print(f"Testing NNUE at: {nnue_path}")

    if not os.path.exists(engine_path):
        print(f"ERROR: Engine file not found at {engine_path}")
        return False
    if not os.path.exists(nnue_path):
        print(f"ERROR: NNUE file not found at {nnue_path}")
        return False

    engine = EngineService(path=engine_path)
    try:
        ok = await engine.probe_compatible_pair(force=True)
        print(f"Probe status: {engine.get_probe_status()}")
        return bool(ok)
    finally:
        await engine.close()


if __name__ == "__main__":
    success = asyncio.run(smoke_test_pikafish())
    if success:
        print("\nSMOKE TEST PASSED")
        sys.exit(0)
    print("\nSMOKE TEST FAILED")
    sys.exit(1)
