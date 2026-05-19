import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_contract_events():
    sys.path.insert(0, str(ROOT))
    from backend.runtime.contract import CONTRACT_EVENTS  # noqa

    return set(CONTRACT_EVENTS)


def load_frontend_cases():
    normalizer = ROOT / "frontend" / "static" / "js" / "modules" / "state" / "normalizer.js"
    text = normalizer.read_text(encoding="utf-8", errors="ignore")
    # crude but stable: match `case "EVENT":`
    return set(re.findall(r'case\s+"([A-Z0-9_.-]+)"\s*:', text))


def main():
    contract = load_contract_events()
    cases = load_frontend_cases()

    missing = sorted(contract - cases)
    if missing:
        print("Contract events missing in frontend Normalizer:")
        for e in missing:
            print(f"- {e}")
        return 1

    print("Contract check OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
