from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _base_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    return env


def _safe_production_env(tmpdir: str) -> dict[str, str]:
    env = _base_env()
    env.update(
        {
            "APP_ENV": "production",
            "SYSTEM_MODE": "production",
            "CHESS_SECRET_KEY": "0123456789abcdef0123456789abcdef",
            "ADMIN_PASSWORD": "not-default-admin-password",
            "SETUP_PASSWORD": "not-default-setup-password",
            "ALLOW_INSECURE_DEFAULTS": "0",
            "TEST_MODE": "0",
            "CORS_ALLOWED_ORIGINS": "https://example.test",
            "CONTROL_AUTH_REQUIRED": "1",
            "RATE_LIMITS_ENABLED": "1",
            "SOCKET_PUBLIC_SNAPSHOT_ENABLED": "0",
            "EVENTBUS_ALLOW_LEGACY_DICT_EVENTS": "0",
            "FAKE_VISION": "0",
            "FAKE_ROBOT": "0",
            "FAKE_AI": "0",
            "VISION_SOURCE": "opencv",
            "VISION_TMFLOW_INGEST_KEY": "",
            "DB_PATH": str(Path(tmpdir, "prod.db").resolve()),
            "SMART_CHESS_HOST": "127.0.0.1",
            "SMART_CHESS_BIND_ALL": "0",
        }
    )
    return env


def _import_config(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", "import backend.utils.config"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )


def _run_current(require_production: bool) -> int:
    try:
        from backend.utils import config
    except Exception as exc:
        print(f"Production preflight FAILED: config import rejected current environment: {exc}")
        return 1

    env_name = getattr(config, "APP_ENV", "unknown")
    if require_production and not getattr(config, "IS_PRODUCTION", False):
        print(
            "Production preflight FAILED: current APP_ENV is "
            f"{env_name!r}, not production."
        )
        return 1

    if not getattr(config, "IS_PRODUCTION", False):
        print(f"Production preflight skipped current-env hard checks because APP_ENV={env_name!r}.")
        return 0

    print("Production preflight OK for current environment.")
    print(f"- host: {getattr(config, 'BIND_HOST', 'unknown')}")
    print(f"- port: {getattr(config, 'PORT', 'unknown')}")
    print(f"- auth required: {bool(getattr(config, 'CONTROL_AUTH_REQUIRED', False))}")
    print(f"- rate limits enabled: {bool(getattr(config, 'RATE_LIMITS_ENABLED', False))}")
    print(f"- cors allow all: {bool(getattr(config, 'CORS_ALLOW_ALL', False))}")
    print(f"- fake robot: {bool(getattr(config, 'FAKE_ROBOT', False))}")
    print(f"- fake vision: {bool(getattr(config, 'FAKE_VISION', False))}")
    print(f"- fake ai: {bool(getattr(config, 'FAKE_AI', False))}")
    return 0


def _expect_pass(name: str, env: dict[str, str]) -> bool:
    result = _import_config(env)
    if result.returncode == 0:
        print(f"[PASS] {name}")
        return True
    print(f"[FAIL] {name}: expected config import to pass.")
    print(_clean_output(result))
    return False


def _expect_fail(name: str, env: dict[str, str], tokens: tuple[str, ...]) -> bool:
    result = _import_config(env)
    output = _clean_output(result)
    if result.returncode != 0 and all(token in output for token in tokens):
        print(f"[PASS] {name}")
        return True
    print(f"[FAIL] {name}: expected config import to fail with {', '.join(tokens)}.")
    print(output)
    return False


def _clean_output(result: subprocess.CompletedProcess[str]) -> str:
    # Do not include environment values. The config module already reports only field names.
    text = "\n".join(part for part in (result.stdout, result.stderr) if part)
    return text.strip() or "<no output>"


def _run_self_test() -> int:
    passed = True
    with tempfile.TemporaryDirectory() as tmpdir:
        safe = _safe_production_env(tmpdir)
        passed &= _expect_pass("safe production profile", safe)

        weak_secret = dict(safe)
        weak_secret["CHESS_SECRET_KEY"] = "change-me"
        passed &= _expect_fail("reject weak secret", weak_secret, ("CHESS_SECRET_KEY",))

        default_admin = dict(safe)
        default_admin["ADMIN_PASSWORD"] = "888888"
        default_admin["ALLOW_INSECURE_DEFAULTS"] = "1"
        passed &= _expect_fail("reject default admin password", default_admin, ("ADMIN_PASSWORD",))

        default_setup = dict(safe)
        default_setup["SETUP_PASSWORD"] = "login"
        passed &= _expect_fail("reject default setup password", default_setup, ("SETUP_PASSWORD",))

        unsafe_control = dict(safe)
        unsafe_control.update(
            {
                "TEST_MODE": "1",
                "CORS_ALLOWED_ORIGINS": "*",
                "CONTROL_AUTH_REQUIRED": "0",
                "RATE_LIMITS_ENABLED": "0",
                "SOCKET_PUBLIC_SNAPSHOT_ENABLED": "1",
                "EVENTBUS_ALLOW_LEGACY_DICT_EVENTS": "1",
            }
        )
        passed &= _expect_fail(
            "reject unsafe control-plane switches",
            unsafe_control,
            (
                "TEST_MODE",
                "CORS_ALLOWED_ORIGINS",
                "CONTROL_AUTH_REQUIRED",
                "RATE_LIMITS_ENABLED",
                "SOCKET_PUBLIC_SNAPSHOT_ENABLED",
                "EVENTBUS_ALLOW_LEGACY_DICT_EVENTS",
            ),
        )

        fake_modes = dict(safe)
        fake_modes.update(
            {
                "SYSTEM_MODE": "simulation",
                "FAKE_VISION": "1",
                "FAKE_ROBOT": "1",
                "FAKE_AI": "1",
            }
        )
        passed &= _expect_fail(
            "reject fake hardware modes in production",
            fake_modes,
            ("SYSTEM_MODE", "FAKE_VISION", "FAKE_ROBOT", "FAKE_AI"),
        )

        tmflow_vision_without_key = dict(safe)
        tmflow_vision_without_key.update({"VISION_SOURCE": "tmflow_json", "VISION_TMFLOW_INGEST_KEY": ""})
        passed &= _expect_fail(
            "reject tmflow vision without ingest key",
            tmflow_vision_without_key,
            ("VISION_TMFLOW_INGEST_KEY",),
        )

        tmflow_vision_with_key = dict(tmflow_vision_without_key)
        tmflow_vision_with_key["VISION_TMFLOW_INGEST_KEY"] = "configured-secret"
        passed &= _expect_pass("accept tmflow vision with ingest key", tmflow_vision_with_key)

        bad_db = dict(safe)
        bad_db["DB_PATH"] = "data/runtime/prod.db"
        passed &= _expect_fail("reject relative production DB path", bad_db, ("DB_PATH", "absolute path"))

        bind_all = dict(safe)
        bind_all.update({"SMART_CHESS_HOST": "0.0.0.0", "SMART_CHESS_BIND_ALL": "0"})
        passed &= _expect_fail("reject implicit bind-all", bind_all, ("SMART_CHESS_BIND_ALL",))

        external_engine_dir = Path(tmpdir, "external-engine")
        external_engine_dir.mkdir(exist_ok=True)
        external_engine = external_engine_dir / "pikafish.exe"
        external_nnue = external_engine_dir / "pikafish.nnue"
        external_engine.write_bytes(b"")
        external_nnue.write_bytes(b"")
        bad_assets = dict(safe)
        bad_assets.update({"ENGINE_PATH": str(external_engine), "NNUE_PATH": str(external_nnue)})
        passed &= _expect_fail(
            "reject unprotected engine assets",
            bad_assets,
            ("ENGINE_PATH", "ENGINE_NNUE_CANDIDATES"),
        )

    if passed:
        print("Production config preflight self-test OK.")
        return 0
    print("Production config preflight self-test FAILED.")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate S.M.A.R.T. Chess production config guards.")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run safe and unsafe production profile checks without using the current .env.",
    )
    parser.add_argument(
        "--current",
        action="store_true",
        help="Validate the current process environment.",
    )
    parser.add_argument(
        "--require-production",
        action="store_true",
        help="Fail current-env validation unless APP_ENV is production.",
    )
    args = parser.parse_args()

    if args.self_test:
        return _run_self_test()
    if args.current or not args.self_test:
        return _run_current(require_production=args.require_production)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
