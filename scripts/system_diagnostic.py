import os
import sys


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.events.bus.event_bus import EventBus
from backend.events.event_types import EventType
from backend.events.models.base_event import BaseEvent
from backend.events import EventFactory
from backend.infrastructure.protected_assets.manifest import validate_assets
from backend.utils import config


def test_engine_and_asset_configuration() -> bool:
    print("\n[1/3] Engine and protected asset configuration")
    checks = {
        "engine": config.ENGINE_PATH,
        "nnue": config.NNUE_PATH,
        "vision_model": config.YOLO_MODEL_PATH,
    }
    ok = True
    for name, path in checks.items():
        exists = bool(path and os.path.exists(path))
        print(f"{name}: {path} ({'OK' if exists else 'MISSING'})")
        ok = ok and exists

    asset_report = validate_assets()
    print(f"asset_manifest: {'OK' if asset_report['ok'] else 'FAIL'}")
    return bool(ok and asset_report["ok"])


def test_event_factory_contract() -> bool:
    print("\n[2/3] Event factory contract")
    event = EventFactory.vision_detect("fen_test", 0.9, 0.1)
    payload = event.to_dict()
    checks = [
        payload.get("event_type") == EventType.VISION_FRAME_PROCESSED.value,
        payload.get("domain") == "VISION",
        payload.get("payload", {}).get("fen") == "fen_test",
    ]
    print(f"event_type: {payload.get('event_type')}")
    print(f"domain: {payload.get('domain')}")
    return all(checks)


def test_event_bus_dispatch() -> bool:
    print("\n[3/3] Event bus dispatch")
    local_bus = EventBus()
    received = []
    event_type = "DIAGNOSTIC.PING"
    local_bus.subscribe(event_type, received.append)
    local_bus.publish(
        BaseEvent.create(
            event_type=event_type,
            source="system_diagnostic",
            payload={"fps": 30.0, "latency": 12.5},
        )
    )
    print(f"events_received: {len(received)}")
    return len(received) == 1


def main() -> int:
    print("=== S.M.A.R.T. Chess System Diagnostic ===")
    results = [
        test_engine_and_asset_configuration(),
        test_event_factory_contract(),
        test_event_bus_dispatch(),
    ]
    passed = all(results)
    print(f"\n=== Diagnostic {'PASSED' if passed else 'FAILED'} ===")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
