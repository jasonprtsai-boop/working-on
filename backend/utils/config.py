import os
import yaml
from dotenv import load_dotenv
import logging

# Load .env file if it exists [Opt 12]
load_dotenv()

# --- System Path Center ---

_backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_PATH = os.path.join(_backend_root, "config", "config.yaml")
if not os.path.exists(CONFIG_PATH):
    CONFIG_PATH = os.path.join(_backend_root, "config.yaml")

# Ultralytics settings directory override (sandbox-friendly)
if "YOLO_CONFIG_DIR" not in os.environ:
    os.environ["YOLO_CONFIG_DIR"] = os.path.abspath(os.path.join("logs", "ultralytics"))
    try:
        os.makedirs(os.environ["YOLO_CONFIG_DIR"], exist_ok=True)
    except Exception:
        pass

_cfg = {}
if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            _cfg = yaml.safe_load(f) or {}
    except Exception:
        logging.getLogger(__name__).debug("Failed to load config.yaml", exc_info=True)

def get_cfg(path, default=None):
    """Safe retrieval of nested config keys."""
    parts = path.split('.')
    val = _cfg
    for p in parts:
        if isinstance(val, dict) and p in val:
            val = val[p]
        else:
            return default
    return val if val is not None else default


def _env_or_cfg(env_name: str, cfg_path: str, default=None):
    """Read runtime config from .env first, then YAML config, then default."""
    value = os.environ.get(env_name)
    if value is not None:
        return value
    return get_cfg(cfg_path, default)


def _as_bool(value, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in ["1", "true", "yes", "on"]


def _normalize_origins(value, default=None):
    if value is None:
        value = default
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text == "*":
            return ["*"]
        return [part.strip() for part in text.split(",") if part.strip()]
    if isinstance(value, (list, tuple, set)):
        origins = [str(part).strip() for part in value if str(part).strip()]
        return ["*"] if "*" in origins else origins
    return []

# System
SYSTEM_MODE = os.environ.get('SYSTEM_MODE', get_cfg('system.mode', 'simulation'))
TEST_MODE = _as_bool(os.environ.get('TEST_MODE', get_cfg('system.test_mode', False)))
LOG_LEVEL = os.environ.get('LOG_LEVEL', get_cfg('system.log_level', 'INFO'))
WS_THROTTLE_MS = get_cfg('system.ws_throttle_ms', 50)
APP_ENV = str(os.environ.get("APP_ENV") or os.environ.get("FLASK_ENV") or get_cfg("system.environment", "development")).strip().lower()
IS_PRODUCTION = APP_ENV in {"prod", "production"}
LOG_QUEUE_SIZE = int(_env_or_cfg("LOG_QUEUE_SIZE", "system.log_queue_size", 10000))

# Runtime contract validation (best-effort, non-fatal)
CONTRACT_VALIDATE = _as_bool(os.environ.get('CONTRACT_VALIDATE', get_cfg('system.contract_validate', True)), default=True)
CONTROL_AUTH_REQUIRED = _as_bool(
    os.environ.get("CONTROL_AUTH_REQUIRED", get_cfg("security.control_auth_required", True)),
    default=True,
)
RATE_LIMITS_ENABLED = _as_bool(
    os.environ.get("RATE_LIMITS_ENABLED", get_cfg("security.rate_limits_enabled", True)),
    default=True,
)
LOGIN_RATE_LIMIT_PER_MINUTE = int(_env_or_cfg("LOGIN_RATE_LIMIT_PER_MINUTE", "security.login_rate_limit_per_minute", 20))
CONTROL_RATE_LIMIT_PER_MINUTE = int(_env_or_cfg("CONTROL_RATE_LIMIT_PER_MINUTE", "security.control_rate_limit_per_minute", 120))
SOCKET_RATE_LIMIT_PER_MINUTE = int(_env_or_cfg("SOCKET_RATE_LIMIT_PER_MINUTE", "security.socket_rate_limit_per_minute", 120))
MAX_REQUEST_BYTES = int(_env_or_cfg("MAX_REQUEST_BYTES", "security.max_request_bytes", 1_048_576))
MAX_SOCKET_PAYLOAD_BYTES = int(_env_or_cfg("MAX_SOCKET_PAYLOAD_BYTES", "security.max_socket_payload_bytes", 65_536))
TRUST_X_FORWARDED_FOR = _as_bool(
    _env_or_cfg("TRUST_X_FORWARDED_FOR", "security.trust_x_forwarded_for", False),
    default=False,
)
TRUSTED_PROXY_IPS = tuple(_normalize_origins(_env_or_cfg("TRUSTED_PROXY_IPS", "security.trusted_proxy_ips", "")))
SOCKET_ACTION_ALLOWLIST = tuple(
    action.strip().upper()
    for action in str(_env_or_cfg(
        "SOCKET_ACTION_ALLOWLIST",
        "security.socket_action_allowlist",
        "START_ENGINE,STOP_ENGINE,SYNC_VISION,RESET,PAUSE,UNDO,RESUME",
    )).split(",")
    if action.strip()
)

# Security (Phase 4 Industrialization Update)
DEFAULT_SECRET_KEY = "industrial-secret"
DEFAULT_ADMIN_PASSWORD = "888888"
ALLOW_INSECURE_DEFAULTS = _as_bool(
    os.environ.get("ALLOW_INSECURE_DEFAULTS", get_cfg("security.allow_insecure_defaults", (not IS_PRODUCTION) or TEST_MODE)),
    default=(not IS_PRODUCTION) or TEST_MODE,
)
SECRET_KEY = os.environ.get("CHESS_SECRET_KEY") or get_cfg("security.secret_key", None) or DEFAULT_SECRET_KEY
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD") or get_cfg("security.admin_password", None) or DEFAULT_ADMIN_PASSWORD

_default_origins = ["*"] if (not IS_PRODUCTION or TEST_MODE) else []
CORS_ALLOWED_ORIGINS = _normalize_origins(
    os.environ.get("CORS_ALLOWED_ORIGINS", None) or get_cfg("security.cors_allowed_origins", _default_origins),
    default=_default_origins,
)
CORS_ALLOW_ALL = CORS_ALLOWED_ORIGINS == ["*"]

_security_logger = logging.getLogger(__name__)
_security_errors = []
_weak_secret_keys = {DEFAULT_SECRET_KEY, "change-me", "changeme", "secret", "dev-secret"}
_secret_text = str(SECRET_KEY or "").strip()
_weak_secret = (
    _secret_text in _weak_secret_keys
    or len(_secret_text) < 32
    or "change-me" in _secret_text.lower()
    or "changeme" in _secret_text.lower()
)
_default_admin_password = ADMIN_PASSWORD == DEFAULT_ADMIN_PASSWORD

if IS_PRODUCTION:
    if TEST_MODE:
        _security_errors.append("TEST_MODE must be false in production.")
    if not CONTROL_AUTH_REQUIRED:
        _security_errors.append("CONTROL_AUTH_REQUIRED must be true in production.")
    if CORS_ALLOW_ALL:
        _security_errors.append("CORS_ALLOWED_ORIGINS must not be '*' in production.")
    if not RATE_LIMITS_ENABLED:
        _security_errors.append("RATE_LIMITS_ENABLED must be true in production.")
    if LOGIN_RATE_LIMIT_PER_MINUTE <= 0 or CONTROL_RATE_LIMIT_PER_MINUTE <= 0 or SOCKET_RATE_LIMIT_PER_MINUTE <= 0:
        _security_errors.append("Rate limits must be positive in production.")
    if TRUST_X_FORWARDED_FOR and not TRUSTED_PROXY_IPS:
        _security_errors.append("TRUSTED_PROXY_IPS must be set when TRUST_X_FORWARDED_FOR is enabled in production.")
    if TRUST_X_FORWARDED_FOR and "*" in TRUSTED_PROXY_IPS:
        _security_errors.append("TRUSTED_PROXY_IPS must not contain '*' in production.")

if _weak_secret:
    message = "[config] Using weak SECRET_KEY."
    if ALLOW_INSECURE_DEFAULTS and not IS_PRODUCTION:
        _security_logger.warning(f"{message} Set a random 32+ character CHESS_SECRET_KEY before production deployment.")
    else:
        _security_errors.append(
            "CHESS_SECRET_KEY must be a non-default 32+ character value in production. "
            "Use 'openssl rand -hex 32' to generate one."
        )
if _default_admin_password:
    message = "[config] Using default ADMIN_PASSWORD."
    if ALLOW_INSECURE_DEFAULTS and not IS_PRODUCTION:
        _security_logger.warning(f"{message} Set ADMIN_PASSWORD before production deployment.")
    else:
        _security_errors.append(
            "ADMIN_PASSWORD must be set to a non-default value in production. "
            "Please update your .env or config.yaml."
        )

# Simulation / Fake Modules
FAKE_ROBOT = _as_bool(os.environ.get('FAKE_ROBOT', get_cfg('system.simulation.fake_robot', True)), default=True)
FAKE_VISION = _as_bool(os.environ.get('FAKE_VISION', get_cfg('system.simulation.fake_vision', True)), default=True)
FAKE_AI = _as_bool(os.environ.get('FAKE_AI', get_cfg('system.simulation.fake_ai', True)), default=True)
AUTO_EXECUTE_ROBOT = _as_bool(
    os.environ.get("AUTO_EXECUTE_ROBOT", get_cfg("system.auto_execute_robot", False)),
    default=False,
)

# Engine
_engine_root = "backend/infrastructure/protected_assets/engine/pikafish-avx2.exe"
_default_nnue_candidates = [
    "backend/infrastructure/protected_assets/engine/pikafish.nnue",
]

_cfg_nnue_candidates = get_cfg("engine.nnue_candidates", None)
if isinstance(_cfg_nnue_candidates, list) and _cfg_nnue_candidates:
    _nnue_candidates = [str(path) for path in _cfg_nnue_candidates]
else:
    _nnue_candidates = list(_default_nnue_candidates)

_nnue_root = next((path for path in _nnue_candidates if os.path.exists(path)), _nnue_candidates[0])

ENGINE_PATH = _env_or_cfg('ENGINE_PATH', 'engine.path', _engine_root)
NNUE_PATH = _env_or_cfg('NNUE_PATH', 'engine.nnue_path', _nnue_root)
ENGINE_NNUE_CANDIDATES = [os.path.abspath(path) for path in _nnue_candidates]
if NNUE_PATH:
    _primary_nnue = os.path.abspath(NNUE_PATH)
    ENGINE_NNUE_CANDIDATES = [_primary_nnue] + [path for path in ENGINE_NNUE_CANDIDATES if os.path.abspath(path) != _primary_nnue]
ENGINE_BOOT_TIMEOUT = 10.0
ENGINE_COMPUTE_TIMEOUT = 12.0
ENGINE_OUTPUT_QUEUE_SIZE = int(_env_or_cfg("ENGINE_OUTPUT_QUEUE_SIZE", "engine.output_queue_size", 2000))
CPU_THROTTLE_THRESHOLD = 80
ENGINE_PROBE_ON_BOOT = _as_bool(os.environ.get("ENGINE_PROBE_ON_BOOT", get_cfg("engine.probe_on_boot", True)), default=True)
ENGINE_AUTO_ANALYZE = _as_bool(os.environ.get("ENGINE_AUTO_ANALYZE", get_cfg("engine.auto_analyze", True)), default=True)
ROBOT_COMMAND_QUEUE_SIZE = int(_env_or_cfg("ROBOT_COMMAND_QUEUE_SIZE", "robot.command_queue_size", 200))
REPLAY_MAX_SESSION_EVENTS = int(_env_or_cfg("REPLAY_MAX_SESSION_EVENTS", "replay.max_session_events", 1000))
REPLAY_SAVE_EVERY_N_EVENTS = int(_env_or_cfg("REPLAY_SAVE_EVERY_N_EVENTS", "replay.save_every_n_events", 10))
REPLAY_RETENTION_FILES = int(_env_or_cfg("REPLAY_RETENTION_FILES", "replay.retention_files", 20))

# Database - Normalized Paths
_db_path_configured = os.environ.get("DB_PATH") is not None or get_cfg("database.path", None) is not None
_db_path_raw = _env_or_cfg('DB_PATH', 'database.path', 'data/runtime/app.db')
_db_path_text = str(_db_path_raw).strip()
DB_PATH = ":memory:" if _db_path_text == ":memory:" else os.path.abspath(_db_path_text)
# Ensure directory exists for file-backed SQLite databases.
if DB_PATH != ":memory:":
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

WAL_MODE = get_cfg('database.wal_mode', True)
PERSISTENCE_QUEUE_SIZE = int(get_cfg("database.persistence_queue_size", 2000))
PERSISTENCE_BATCH_SIZE = int(get_cfg("database.persistence_batch_size", 100))
PERSISTENCE_FLUSH_INTERVAL_SEC = float(get_cfg("database.persistence_flush_interval_sec", 0.25))

if IS_PRODUCTION:
    if not _db_path_configured:
        _security_errors.append("DB_PATH must be explicitly configured in production.")
    if _db_path_text == ":memory:":
        _security_errors.append("DB_PATH must not use in-memory SQLite in production.")
    if _db_path_text != ":memory:" and not os.path.isabs(_db_path_text):
        _security_errors.append("DB_PATH must be an absolute path in production.")
    if SYSTEM_MODE.strip().lower() in {"simulation", "test", "demo"}:
        _security_errors.append("SYSTEM_MODE must not be simulation/test/demo in production.")
    if FAKE_VISION:
        _security_errors.append("FAKE_VISION must be false in production.")
    if FAKE_ROBOT:
        _security_errors.append("FAKE_ROBOT must be false in production.")
    if FAKE_AI:
        _security_errors.append("FAKE_AI must be false in production.")
    if MAX_REQUEST_BYTES <= 0 or MAX_SOCKET_PAYLOAD_BYTES <= 0:
        _security_errors.append("Payload size limits must be positive in production.")
    if not SOCKET_ACTION_ALLOWLIST:
        _security_errors.append("SOCKET_ACTION_ALLOWLIST must not be empty in production.")

if _security_errors:
    raise RuntimeError("Unsafe production security configuration: " + " ".join(_security_errors))

# Vision
CAMERA_INDEX = int(_env_or_cfg('CAMERA_INDEX', 'vision.camera_index', 0))
WARP_WIDTH = int(_env_or_cfg('WARP_WIDTH', 'vision.warp_width', 1000))
WARP_HEIGHT = int(_env_or_cfg('WARP_HEIGHT', 'vision.warp_height', 1000))
VISION_CONFIDENCE = float(_env_or_cfg('VISION_CONFIDENCE', 'vision.confidence_threshold', 0.3))
VISION_NMS_IOU = float(_env_or_cfg('VISION_NMS_IOU', 'vision.nms_iou', 0.45))
STABILITY_THRESHOLD = int(_env_or_cfg('STABILITY_THRESHOLD', 'vision.stability_threshold', 3))
VISION_SMALL_OBJECT_AREA_RATIO = float(_env_or_cfg('VISION_SMALL_OBJECT_AREA_RATIO', 'vision.small_object_area_ratio', 0.01))

# AI Detection
_default_model_candidates = [
    "backend/infrastructure/protected_assets/vision/best.pt",
]
_default_model_path = next(
    (path for path in _default_model_candidates if os.path.exists(path)),
    _default_model_candidates[0],
)
YOLO_MODEL_PATH = _env_or_cfg('YOLO_MODEL_PATH', 'vision.model_path', _default_model_path)
YOLO_MODEL_TYPE = str(_env_or_cfg('YOLO_MODEL_TYPE', 'vision.model_type', 'yolov8'))
YOLO_DNN_INPUT_SIZE = int(_env_or_cfg('YOLO_DNN_INPUT_SIZE', 'vision.dnn_input_size', 640))
YOLO_OUTPUT_HAS_OBJECTNESS = _as_bool(
    _env_or_cfg('YOLO_OUTPUT_HAS_OBJECTNESS', 'vision.output_has_objectness', False),
    default=False,
)
VISION_DEVICE = str(_env_or_cfg('VISION_DEVICE', 'vision.device', 'cpu'))
SAHI_SLICE_HEIGHT = int(_env_or_cfg('SAHI_SLICE_HEIGHT', 'vision.sahi_slice_height', 640))
SAHI_SLICE_WIDTH = int(_env_or_cfg('SAHI_SLICE_WIDTH', 'vision.sahi_slice_width', 640))
SAHI_OVERLAP_RATIO = float(_env_or_cfg('SAHI_OVERLAP_RATIO', 'vision.sahi_overlap_ratio', 0.20))

# Robot
ROBOT_IP = get_cfg('robot.ip', '192.168.1.1')
ROBOT_PORT = get_cfg('robot.port', 5891)
CALIBRATION_FILE = get_cfg('robot.calibration_file', 'robot/calibration.json')
Z_SAFE = float(get_cfg("robot.z_safe", 150.0))
Z_GRAB = float(get_cfg("robot.z_grab", 20.0))
ROBOT_MAX_X = float(get_cfg("robot.max_x", 600.0))
ROBOT_MIN_X = float(get_cfg("robot.min_x", -600.0))
ROBOT_MAX_Y = float(get_cfg("robot.max_y", 600.0))
ROBOT_MIN_Y = float(get_cfg("robot.min_y", 100.0))

# Board
BOARD_ROWS = 10
BOARD_COLS = 9
FILES = "abcdefghi"
RANKS = [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]
