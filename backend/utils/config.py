import os
import yaml
from dotenv import load_dotenv
import logging

from backend.utils.setup_settings import get_nested as _setup_get
from backend.utils.setup_settings import load_settings as _load_setup_settings

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


SETUP_SETTINGS_FILE = os.path.abspath(
    os.environ.get("SETUP_SETTINGS_FILE") or get_cfg("setup.settings_file", "data/setup_settings.json")
)
_setup_settings = _load_setup_settings(SETUP_SETTINGS_FILE)


def _env_or_cfg(env_name: str, cfg_path: str, default=None):
    """Read runtime config from .env first, then YAML config, then default."""
    value = os.environ.get(env_name)
    if value is not None:
        return value
    return get_cfg(cfg_path, default)


def _setup_or_env_or_cfg(env_name: str, cfg_path: str, setup_path: str, default=None):
    """Read setup JSON before env/YAML, except production env overrides stale setup."""
    env_value = os.environ.get(env_name)
    app_env = str(
        os.environ.get("APP_ENV") or os.environ.get("FLASK_ENV") or get_cfg("system.environment", "development")
    ).strip().lower()
    if app_env in {"prod", "production"} and env_value is not None:
        return env_value
    value = _setup_get(_setup_settings, setup_path, None)
    if value is not None:
        return value
    if env_value is not None:
        return env_value
    return _env_or_cfg(env_name, cfg_path, default)


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


def _load_yolo_class_names(path: str) -> list[str]:
    """Load class names from the preserved YOLO dataset yaml when available."""
    if not path:
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        logging.getLogger(__name__).debug("Failed to load YOLO class names from %s", path, exc_info=True)
        return []

    names = data.get("names")
    if isinstance(names, dict):
        try:
            keys = sorted(names, key=lambda item: int(item))
        except Exception:
            keys = sorted(names)
        return [str(names[key]) for key in keys]
    if isinstance(names, list):
        return [str(name) for name in names]
    return []

# System
SYSTEM_MODE = os.environ.get('SYSTEM_MODE', get_cfg('system.mode', 'simulation'))
TEST_MODE = _as_bool(os.environ.get('TEST_MODE', get_cfg('system.test_mode', False)))
LOG_LEVEL = os.environ.get('LOG_LEVEL', get_cfg('system.log_level', 'INFO'))
WS_THROTTLE_MS = get_cfg('system.ws_throttle_ms', 50)
APP_ENV = str(os.environ.get("APP_ENV") or os.environ.get("FLASK_ENV") or get_cfg("system.environment", "development")).strip().lower()
IS_PRODUCTION = APP_ENV in {"prod", "production"}
LOG_QUEUE_SIZE = int(_env_or_cfg("LOG_QUEUE_SIZE", "system.log_queue_size", 10000))
MONITORING_INTERVAL_SEC = float(_env_or_cfg("MONITORING_INTERVAL_SEC", "system.monitoring_interval_sec", 1.0))

_bind_all_requested = _as_bool(_env_or_cfg("SMART_CHESS_BIND_ALL", "server.bind_all", False), default=False)
_explicit_host = os.environ.get("SMART_CHESS_HOST") or os.environ.get("HOST") or get_cfg("server.host", None)
BIND_HOST = str(_explicit_host or ("0.0.0.0" if _bind_all_requested else "127.0.0.1")).strip() or "127.0.0.1"
PORT = int(_env_or_cfg("PORT", "server.port", 5000))

# Runtime contract validation (best-effort, non-fatal)
CONTRACT_VALIDATE = _as_bool(os.environ.get('CONTRACT_VALIDATE', get_cfg('system.contract_validate', True)), default=True)
EVENTBUS_ALLOW_LEGACY_DICT_EVENTS = _as_bool(
    _env_or_cfg("EVENTBUS_ALLOW_LEGACY_DICT_EVENTS", "system.eventbus_allow_legacy_dict_events", not IS_PRODUCTION),
    default=not IS_PRODUCTION,
)
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
SOCKET_PUBLIC_SNAPSHOT_ENABLED = _as_bool(
    _env_or_cfg("SOCKET_PUBLIC_SNAPSHOT_ENABLED", "security.socket_public_snapshot_enabled", not IS_PRODUCTION),
    default=not IS_PRODUCTION,
)
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
_default_allow_insecure_defaults = bool(TEST_MODE)
ALLOW_INSECURE_DEFAULTS = _as_bool(
    os.environ.get("ALLOW_INSECURE_DEFAULTS", get_cfg("security.allow_insecure_defaults", _default_allow_insecure_defaults)),
    default=_default_allow_insecure_defaults,
)
SECRET_KEY = os.environ.get("CHESS_SECRET_KEY") or get_cfg("security.secret_key", None) or DEFAULT_SECRET_KEY
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD") or get_cfg("security.admin_password", None) or DEFAULT_ADMIN_PASSWORD
SETUP_PASSWORD = os.environ.get("SETUP_PASSWORD") or get_cfg("security.setup_password", "login")
JWT_TTL_MINUTES = int(_env_or_cfg("JWT_TTL_MINUTES", "security.jwt_ttl_minutes", 120))
COMMISSIONING_REPORT_FILE = _env_or_cfg(
    "COMMISSIONING_REPORT_FILE",
    "system.commissioning_report_file",
    os.path.join("data", "commissioning_report.json"),
)

_local_origins = [f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}"]
_default_origins = ["*"] if TEST_MODE else ([] if IS_PRODUCTION else _local_origins)
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
_default_setup_password = str(SETUP_PASSWORD or "") == "login"

if IS_PRODUCTION:
    if TEST_MODE:
        _security_errors.append("TEST_MODE must be false in production.")
    if not CONTROL_AUTH_REQUIRED:
        _security_errors.append("CONTROL_AUTH_REQUIRED must be true in production.")
    if CORS_ALLOW_ALL:
        _security_errors.append("CORS_ALLOWED_ORIGINS must not be '*' in production.")
    if not RATE_LIMITS_ENABLED:
        _security_errors.append("RATE_LIMITS_ENABLED must be true in production.")
    if SOCKET_PUBLIC_SNAPSHOT_ENABLED:
        _security_errors.append("SOCKET_PUBLIC_SNAPSHOT_ENABLED must be false in production.")
    if EVENTBUS_ALLOW_LEGACY_DICT_EVENTS:
        _security_errors.append("EVENTBUS_ALLOW_LEGACY_DICT_EVENTS must be false in production.")
    if LOGIN_RATE_LIMIT_PER_MINUTE <= 0 or CONTROL_RATE_LIMIT_PER_MINUTE <= 0 or SOCKET_RATE_LIMIT_PER_MINUTE <= 0:
        _security_errors.append("Rate limits must be positive in production.")
    if TRUST_X_FORWARDED_FOR and not TRUSTED_PROXY_IPS:
        _security_errors.append("TRUSTED_PROXY_IPS must be set when TRUST_X_FORWARDED_FOR is enabled in production.")
    if TRUST_X_FORWARDED_FOR and "*" in TRUSTED_PROXY_IPS:
        _security_errors.append("TRUSTED_PROXY_IPS must not contain '*' in production.")
    if _default_setup_password:
        _security_errors.append("SETUP_PASSWORD must be changed from the default 'login' in production.")

if JWT_TTL_MINUTES <= 0 or JWT_TTL_MINUTES > 24 * 60:
    _security_errors.append("JWT_TTL_MINUTES must be between 1 and 1440.")

if _weak_secret:
    message = "[config] Using weak SECRET_KEY."
    if ALLOW_INSECURE_DEFAULTS and not IS_PRODUCTION:
        _security_logger.warning(
            f"{message} Set a random 32+ character CHESS_SECRET_KEY before production deployment."
        )
    else:
        _security_errors.append(
            "CHESS_SECRET_KEY must be a non-default 32+ character value outside explicit TEST_MODE/insecure-dev. "
            "Use 'openssl rand -hex 32' to generate one."
        )
if _default_admin_password:
    message = "[config] Using default ADMIN_PASSWORD."
    if ALLOW_INSECURE_DEFAULTS and not IS_PRODUCTION:
        _security_logger.warning(f"{message} Set ADMIN_PASSWORD before production deployment.")
    else:
        _security_errors.append(
            "ADMIN_PASSWORD must be set to a non-default value outside explicit TEST_MODE/insecure-dev. "
            "Please update your .env or config.yaml."
        )

if BIND_HOST in {"0.0.0.0", "::"} and not _bind_all_requested:
    _security_errors.append("Binding to all interfaces requires SMART_CHESS_BIND_ALL=1.")
if BIND_HOST in {"0.0.0.0", "::"} and (_weak_secret or _default_admin_password or CORS_ALLOW_ALL):
    if ALLOW_INSECURE_DEFAULTS and TEST_MODE and not IS_PRODUCTION:
        _security_logger.warning("[config] TEST_MODE permits insecure bind-all settings for local test harnesses.")
    else:
        _security_errors.append(
            "Bind-all mode requires a strong CHESS_SECRET_KEY, non-default ADMIN_PASSWORD, and non-wildcard CORS."
        )

# Simulation / Fake Modules
FAKE_ROBOT = _as_bool(
    _setup_or_env_or_cfg('FAKE_ROBOT', 'system.simulation.fake_robot', 'robot.runtime.fake_robot', True),
    default=True,
)
FAKE_VISION = _as_bool(os.environ.get('FAKE_VISION', get_cfg('system.simulation.fake_vision', False)), default=False)
FAKE_AI = _as_bool(os.environ.get('FAKE_AI', get_cfg('system.simulation.fake_ai', True)), default=True)
AUTO_EXECUTE_ROBOT = _as_bool(
    _setup_or_env_or_cfg("AUTO_EXECUTE_ROBOT", "system.auto_execute_robot", "robot.runtime.auto_execute_robot", False),
    default=False,
)

# Engine
PROTECTED_ASSET_ROOT = os.path.abspath(os.path.join("backend", "infrastructure", "protected_assets"))
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
ENGINE_PROBE_ON_BOOT = _as_bool(os.environ.get("ENGINE_PROBE_ON_BOOT", get_cfg("engine.probe_on_boot", False)), default=False)
ENGINE_AUTO_ANALYZE = _as_bool(os.environ.get("ENGINE_AUTO_ANALYZE", get_cfg("engine.auto_analyze", False)), default=False)
AI_MODE_DEFAULT = str(_env_or_cfg("AI_MODE_DEFAULT", "engine.ai_mode_default", "companionship")).strip().lower()
REPLAY_MAX_SESSION_EVENTS = int(_env_or_cfg("REPLAY_MAX_SESSION_EVENTS", "replay.max_session_events", 1000))
REPLAY_SAVE_EVERY_N_EVENTS = int(_env_or_cfg("REPLAY_SAVE_EVERY_N_EVENTS", "replay.save_every_n_events", 10))
REPLAY_RETENTION_FILES = int(_env_or_cfg("REPLAY_RETENTION_FILES", "replay.retention_files", 20))


def _is_under_root(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([os.path.abspath(path), root]) == root
    except (OSError, ValueError):
        return False

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
PERSISTENCE_DROP_WARNING_THRESHOLD = int(_env_or_cfg("PERSISTENCE_DROP_WARNING_THRESHOLD", "database.persistence_drop_warning_threshold", 1))
PERSISTENCE_DROP_WARNING_INTERVAL_SEC = float(_env_or_cfg("PERSISTENCE_DROP_WARNING_INTERVAL_SEC", "database.persistence_drop_warning_interval_sec", 5.0))
EXCEL_EXPORT_EVENT_LIMIT = int(_env_or_cfg("EXCEL_EXPORT_EVENT_LIMIT", "database.excel_export_event_limit", 1000))
AUTO_EXPORT_SESSION_RECORD = _as_bool(
    _env_or_cfg("AUTO_EXPORT_SESSION_RECORD", "database.auto_export_session_record", True),
    default=True,
)
GAME_RECORD_EXPORT_DIR = _env_or_cfg("GAME_RECORD_EXPORT_DIR", "database.game_record_export_dir", os.path.join("logs", "game_records"))

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
    if not _is_under_root(ENGINE_PATH, PROTECTED_ASSET_ROOT):
        _security_errors.append("ENGINE_PATH must point inside backend/infrastructure/protected_assets in production.")
    if not os.path.isfile(os.path.abspath(ENGINE_PATH)):
        _security_errors.append("ENGINE_PATH must point to an existing protected engine executable in production.")
    for candidate in ENGINE_NNUE_CANDIDATES:
        if not _is_under_root(candidate, PROTECTED_ASSET_ROOT):
            _security_errors.append("ENGINE_NNUE_CANDIDATES must point inside backend/infrastructure/protected_assets in production.")
            break
        if not os.path.isfile(os.path.abspath(candidate)):
            _security_errors.append("ENGINE_NNUE_CANDIDATES must point to existing protected NNUE files in production.")
            break

if _security_errors:
    raise RuntimeError("Unsafe production security configuration: " + " ".join(_security_errors))

# Lab robot network defaults
DEFAULT_ROBOT_IP = "192.168.10.10"
DEFAULT_ROBOT_PC_IP = "192.168.10.50"
DEFAULT_ROBOT_SUBNET_MASK = "255.255.0.0"

# Vision
CAMERA_INDEX = int(_setup_or_env_or_cfg('CAMERA_INDEX', 'vision.camera_index', 'vision.camera_index', 0))
VISION_SOURCE = str(
    _setup_or_env_or_cfg("VISION_SOURCE", "vision.source", "vision.source", "opencv")
).strip().lower()
if VISION_SOURCE in {"usb", "usb_camera", "camera", "opencv_usb"}:
    VISION_SOURCE = "opencv"
if VISION_SOURCE not in {"opencv", "tmflow_json"}:
    VISION_SOURCE = "opencv"
_default_vision_tmflow_host = (
    _setup_get(_setup_settings, "vision.tmflow_json.host", None)
    or _setup_get(_setup_settings, "robot.connection.ip", None)
    or get_cfg("vision.tmflow_json.host", None)
    or get_cfg("robot.ip", DEFAULT_ROBOT_IP)
)
VISION_TMFLOW_IMAGE_HOST = str(
    _setup_or_env_or_cfg(
        "VISION_TMFLOW_IMAGE_HOST",
        "vision.tmflow_json.host",
        "vision.tmflow_json.host",
        _default_vision_tmflow_host,
    )
).strip()
VISION_TMFLOW_IMAGE_PORT = int(
    _setup_or_env_or_cfg("VISION_TMFLOW_IMAGE_PORT", "vision.tmflow_json.port", "vision.tmflow_json.port", 5891)
)
VISION_TMFLOW_IMAGE_TIMEOUT_SEC = float(
    _setup_or_env_or_cfg(
        "VISION_TMFLOW_IMAGE_TIMEOUT_SEC",
        "vision.tmflow_json.timeout_sec",
        "vision.tmflow_json.timeout_sec",
        2.0,
    )
)
VISION_TMFLOW_IMAGE_MAX_MESSAGE_BYTES = int(
    _setup_or_env_or_cfg(
        "VISION_TMFLOW_IMAGE_MAX_MESSAGE_BYTES",
        "vision.tmflow_json.max_message_bytes",
        "vision.tmflow_json.max_message_bytes",
        1_048_576,
    )
)
VISION_TMFLOW_IMAGE_FPS_LIMIT = float(
    _setup_or_env_or_cfg(
        "VISION_TMFLOW_IMAGE_FPS_LIMIT",
        "vision.tmflow_json.fps_limit",
        "vision.tmflow_json.fps_limit",
        2.0,
    )
)
VISION_TMFLOW_INGEST_KEY = str(
    _setup_or_env_or_cfg(
        "VISION_TMFLOW_INGEST_KEY",
        "vision.tmflow_json.ingest_key",
        "vision.tmflow_json.ingest_key",
        "",
    )
).strip()
_tmflow_vision_key_required = VISION_SOURCE == "tmflow_json" and (
    IS_PRODUCTION or BIND_HOST in {"0.0.0.0", "::"} or not FAKE_ROBOT
)
if _tmflow_vision_key_required and not VISION_TMFLOW_INGEST_KEY:
    raise RuntimeError(
        "Unsafe TMflow vision ingest configuration: VISION_TMFLOW_INGEST_KEY must be set "
        "when TMflow vision is used with production, bind-all networking, or real robot mode."
    )
VISION_WORKER_PIPELINE_ENABLED = _as_bool(
    _env_or_cfg("VISION_WORKER_PIPELINE_ENABLED", "vision.worker_pipeline_enabled", False),
    default=False,
)
WARP_WIDTH = int(_env_or_cfg('WARP_WIDTH', 'vision.warp_width', 1000))
WARP_HEIGHT = int(_env_or_cfg('WARP_HEIGHT', 'vision.warp_height', 1000))
VISION_CALIBRATION_MAX_DIM = int(_env_or_cfg("VISION_CALIBRATION_MAX_DIM", "vision.calibration_max_dim", 960))
VISION_CALIBRATION_FILE = os.path.abspath(
    _env_or_cfg("VISION_CALIBRATION_FILE", "vision.calibration_file", "data/vision_calibration.json")
)
VISION_CONFIDENCE = float(_env_or_cfg('VISION_CONFIDENCE', 'vision.confidence_threshold', 0.3))
VISION_NMS_IOU = float(_env_or_cfg('VISION_NMS_IOU', 'vision.nms_iou', 0.45))
STABILITY_THRESHOLD = int(_env_or_cfg('STABILITY_THRESHOLD', 'vision.stability_threshold', 3))
VISION_SMALL_OBJECT_AREA_RATIO = float(_env_or_cfg('VISION_SMALL_OBJECT_AREA_RATIO', 'vision.small_object_area_ratio', 0.01))
CAMERA_DISCOVERY_CACHE_TTL_SEC = float(_env_or_cfg("CAMERA_DISCOVERY_CACHE_TTL_SEC", "vision.camera_discovery_cache_ttl_sec", 10.0))
VISION_PREPROCESS_MODE = str(_env_or_cfg("VISION_PREPROCESS_MODE", "vision.preprocess_mode", "fast")).strip().lower()
VISION_MJPEG_QUALITY = int(_env_or_cfg("VISION_MJPEG_QUALITY", "vision.mjpeg_quality", 75))
VISION_MJPEG_FPS = int(_env_or_cfg("VISION_MJPEG_FPS", "vision.mjpeg_fps", 15))
VISION_RESULT_MAX_AGE_SEC = float(
    _setup_or_env_or_cfg("VISION_RESULT_MAX_AGE_SEC", "vision.result_max_age_sec", "vision.result_max_age_sec", 3.0)
)

# AI Detection
_default_model_path = "backend/infrastructure/protected_assets/vision/best.onnx"
YOLO_MODEL_PATH = _env_or_cfg('YOLO_MODEL_PATH', 'vision.model_path', _default_model_path)
YOLO_MODEL_TYPE = str(_env_or_cfg('YOLO_MODEL_TYPE', 'vision.model_type', 'yolo26'))
ULTRALYTICS_MIN_VERSION = str(_env_or_cfg("ULTRALYTICS_MIN_VERSION", "vision.ultralytics_min_version", "8.4.55"))
YOLO_DNN_INPUT_SIZE = int(_env_or_cfg('YOLO_DNN_INPUT_SIZE', 'vision.dnn_input_size', 640))
YOLO_OUTPUT_HAS_OBJECTNESS = _as_bool(
    _env_or_cfg('YOLO_OUTPUT_HAS_OBJECTNESS', 'vision.output_has_objectness', False),
    default=False,
)
YOLO_WARMUP_ON_LOAD = _as_bool(
    _env_or_cfg("YOLO_WARMUP_ON_LOAD", "vision.warmup_on_load", True),
    default=True,
)
VISION_BBOX_ANCHOR_X = float(_env_or_cfg("VISION_BBOX_ANCHOR_X", "vision.bbox_anchor_x", 0.5))
VISION_BBOX_ANCHOR_Y = float(_env_or_cfg("VISION_BBOX_ANCHOR_Y", "vision.bbox_anchor_y", 0.5))
YOLO_DATASET_MAPPING_PATH = os.path.abspath(
    _env_or_cfg(
        "YOLO_DATASET_MAPPING_PATH",
        "vision.dataset_mapping_path",
        "backend/infrastructure/protected_assets/vision/dataset_mapping.yaml",
    )
)
YOLO_TRAINING_ARGS_PATH = os.path.abspath(
    _env_or_cfg(
        "YOLO_TRAINING_ARGS_PATH",
        "vision.training_args_path",
        "backend/infrastructure/protected_assets/vision/args.yaml",
    )
)
YOLO_CLASS_NAMES = tuple(_load_yolo_class_names(YOLO_DATASET_MAPPING_PATH))
VISION_DEVICE = str(_env_or_cfg('VISION_DEVICE', 'vision.device', 'cpu'))

# Robot
ROBOT_IP = str(_setup_or_env_or_cfg('ROBOT_IP', 'robot.ip', 'robot.connection.ip', DEFAULT_ROBOT_IP))
ROBOT_PORT = int(_setup_or_env_or_cfg('ROBOT_PORT', 'robot.port', 'robot.connection.port', 5890))
_ROBOT_ADAPTER_SETTING = _setup_get(_setup_settings, "robot.connection.adapter", None)
if _ROBOT_ADAPTER_SETTING is None:
    _ROBOT_ADAPTER_SETTING = _setup_get(_setup_settings, "robot.adapter", None)
if _ROBOT_ADAPTER_SETTING is None:
    _ROBOT_ADAPTER_SETTING = os.environ.get("ROBOT_ADAPTER")
if _ROBOT_ADAPTER_SETTING is None:
    _ROBOT_ADAPTER_SETTING = get_cfg("robot.adapter", None)
if _ROBOT_ADAPTER_SETTING is None and ROBOT_PORT != 5890:
    _ROBOT_ADAPTER_SETTING = "modbus"
ROBOT_ADAPTER = str(_ROBOT_ADAPTER_SETTING or "tmflow_json").strip().lower()
if ROBOT_ADAPTER not in {"tmflow_json", "techmanpy", "modbus"}:
    ROBOT_ADAPTER = "tmflow_json"
ROBOT_PC_IP = str(_setup_or_env_or_cfg("ROBOT_PC_IP", "robot.pc_ip", "robot.connection.pc_ip", DEFAULT_ROBOT_PC_IP))
ROBOT_SUBNET_MASK = str(
    _setup_or_env_or_cfg("ROBOT_SUBNET_MASK", "robot.subnet_mask", "robot.connection.subnet_mask", DEFAULT_ROBOT_SUBNET_MASK)
)
TMFLOW_VERSION = str(
    _setup_or_env_or_cfg("TMFLOW_VERSION", "robot.tmflow_version", "robot.connection.tmflow_version", "1.82")
)
TM_CONTROLLER_VERSION = str(
    _setup_or_env_or_cfg(
        "TM_CONTROLLER_VERSION",
        "robot.controller_version",
        "robot.connection.controller_version",
        "1.82.51",
    )
)
ROBOT_CONNECT_TIMEOUT_SEC = float(
    _setup_or_env_or_cfg("ROBOT_CONNECT_TIMEOUT_SEC", "robot.connection.timeout_sec", "robot.connection.timeout_sec", 3.0)
)
ROBOT_TECHMANPY_REQUIRE_LISTEN_NODE = _as_bool(
    _setup_or_env_or_cfg(
        "ROBOT_TECHMANPY_REQUIRE_LISTEN_NODE",
        "robot.techmanpy.require_listen_node",
        "robot.techmanpy.require_listen_node",
        True,
    ),
    default=True,
)
ROBOT_TECHMANPY_MOTION_MODE = str(
    _setup_or_env_or_cfg("ROBOT_TECHMANPY_MOTION_MODE", "robot.techmanpy.motion_mode", "robot.techmanpy.motion_mode", "ptp")
).strip().lower()
if ROBOT_TECHMANPY_MOTION_MODE not in {"ptp", "line"}:
    ROBOT_TECHMANPY_MOTION_MODE = "ptp"
ROBOT_TECHMANPY_SUPPRESS_WARNINGS = _as_bool(
    _setup_or_env_or_cfg(
        "ROBOT_TECHMANPY_SUPPRESS_WARNINGS",
        "robot.techmanpy.suppress_warnings",
        "robot.techmanpy.suppress_warnings",
        False,
    ),
    default=False,
)
ROBOT_TMFLOW_PROTOCOL_VERSION = str(
    _setup_or_env_or_cfg(
        "ROBOT_TMFLOW_PROTOCOL_VERSION",
        "robot.tmflow_json.protocol_version",
        "robot.tmflow_json.protocol_version",
        "1.0",
    )
)
ROBOT_TMFLOW_CLIENT_VERSION = str(
    _setup_or_env_or_cfg(
        "ROBOT_TMFLOW_CLIENT_VERSION",
        "robot.tmflow_json.client_version",
        "robot.tmflow_json.client_version",
        "1.0",
    )
)
ROBOT_TMFLOW_WIRE_FORMAT = str(
    _setup_or_env_or_cfg(
        "ROBOT_TMFLOW_WIRE_FORMAT",
        "robot.tmflow_json.wire_format",
        "robot.tmflow_json.wire_format",
        "envelope",
    )
).strip().lower()
if ROBOT_TMFLOW_WIRE_FORMAT not in {"envelope", "flat_json"}:
    ROBOT_TMFLOW_WIRE_FORMAT = "envelope"
ROBOT_TMFLOW_REQUIRE_HELLO = _as_bool(
    _setup_or_env_or_cfg(
        "ROBOT_TMFLOW_REQUIRE_HELLO",
        "robot.tmflow_json.require_hello",
        "robot.tmflow_json.require_hello",
        True,
    ),
    default=True,
)
ROBOT_TMFLOW_ACK_TIMEOUT_SEC = float(
    _setup_or_env_or_cfg(
        "ROBOT_TMFLOW_ACK_TIMEOUT_SEC",
        "robot.tmflow_json.ack_timeout_sec",
        "robot.tmflow_json.ack_timeout_sec",
        2.0,
    )
)
ROBOT_TMFLOW_DONE_TIMEOUT_SEC = float(
    _setup_or_env_or_cfg(
        "ROBOT_TMFLOW_DONE_TIMEOUT_SEC",
        "robot.tmflow_json.done_timeout_sec",
        "robot.tmflow_json.done_timeout_sec",
        30.0,
    )
)
ROBOT_TMFLOW_LONG_TASK_TIMEOUT_SEC = float(
    _setup_or_env_or_cfg(
        "ROBOT_TMFLOW_LONG_TASK_TIMEOUT_SEC",
        "robot.tmflow_json.long_task_timeout_sec",
        "robot.tmflow_json.long_task_timeout_sec",
        90.0,
    )
)
ROBOT_TMFLOW_HEARTBEAT_INTERVAL_SEC = float(
    _setup_or_env_or_cfg(
        "ROBOT_TMFLOW_HEARTBEAT_INTERVAL_SEC",
        "robot.tmflow_json.heartbeat_interval_sec",
        "robot.tmflow_json.heartbeat_interval_sec",
        1.0,
    )
)
ROBOT_TMFLOW_RECONNECT_INTERVAL_SEC = float(
    _setup_or_env_or_cfg(
        "ROBOT_TMFLOW_RECONNECT_INTERVAL_SEC",
        "robot.tmflow_json.reconnect_interval_sec",
        "robot.tmflow_json.reconnect_interval_sec",
        2.0,
    )
)
ROBOT_TMFLOW_MAX_RETRY = int(
    _setup_or_env_or_cfg(
        "ROBOT_TMFLOW_MAX_RETRY",
        "robot.tmflow_json.max_retry",
        "robot.tmflow_json.max_retry",
        2,
    )
)
ROBOT_TMFLOW_MAX_MESSAGE_BYTES = int(
    _setup_or_env_or_cfg(
        "ROBOT_TMFLOW_MAX_MESSAGE_BYTES",
        "robot.tmflow_json.max_message_bytes",
        "robot.tmflow_json.max_message_bytes",
        4096,
    )
)
ROBOT_TMFLOW_BASE = str(
    _setup_or_env_or_cfg("ROBOT_TMFLOW_BASE", "robot.tmflow_json.base", "robot.tmflow_json.base", "ChessBoard_Base")
)
ROBOT_TMFLOW_TCP = str(
    _setup_or_env_or_cfg("ROBOT_TMFLOW_TCP", "robot.tmflow_json.tcp", "robot.tmflow_json.tcp", "ChessGripper_TCP")
)
ROBOT_TMFLOW_GRIPPER_WAIT_MS = int(
    _setup_or_env_or_cfg(
        "ROBOT_TMFLOW_GRIPPER_WAIT_MS",
        "robot.tmflow_json.gripper_wait_ms",
        "robot.tmflow_json.gripper_wait_ms",
        300,
    )
)
ROBOT_TMFLOW_STOP_MODE = str(
    _setup_or_env_or_cfg(
        "ROBOT_TMFLOW_STOP_MODE",
        "robot.tmflow_json.stop_mode",
        "robot.tmflow_json.stop_mode",
        "CONTROLLED_STOP",
    )
).strip().upper()
CALIBRATION_FILE = get_cfg('robot.calibration_file', 'robot/calibration.json')
Z_SAFE = float(_setup_or_env_or_cfg("Z_SAFE", "robot.z_safe", "robot.motion.z_safe", 150.0))
Z_GRAB = float(_setup_or_env_or_cfg("Z_GRAB", "robot.z_grab", "robot.motion.z_grab", 20.0))
ROBOT_MAX_X = float(_setup_or_env_or_cfg("ROBOT_MAX_X", "robot.max_x", "robot.limits.max_x", 600.0))
ROBOT_MIN_X = float(_setup_or_env_or_cfg("ROBOT_MIN_X", "robot.min_x", "robot.limits.min_x", -600.0))
ROBOT_MAX_Y = float(_setup_or_env_or_cfg("ROBOT_MAX_Y", "robot.max_y", "robot.limits.max_y", 600.0))
ROBOT_MIN_Y = float(_setup_or_env_or_cfg("ROBOT_MIN_Y", "robot.min_y", "robot.limits.min_y", 100.0))
ROBOT_MIN_Z = float(_setup_or_env_or_cfg("ROBOT_MIN_Z", "robot.min_z", "robot.limits.min_z", 0.0))
ROBOT_MAX_Z = float(
    _setup_or_env_or_cfg("ROBOT_MAX_Z", "robot.max_z", "robot.limits.max_z", max(Z_SAFE, Z_GRAB) + 100.0)
)
SOFT_LIMIT_X = (ROBOT_MIN_X, ROBOT_MAX_X)
SOFT_LIMIT_Y = (ROBOT_MIN_Y, ROBOT_MAX_Y)
SOFT_LIMIT_Z = (ROBOT_MIN_Z, ROBOT_MAX_Z)
ROBOT_MIN_SPEED = float(_setup_or_env_or_cfg("ROBOT_MIN_SPEED", "robot.motion.min_speed", "robot.motion.min_speed", 1.0))
ROBOT_MAX_SPEED = float(_setup_or_env_or_cfg("ROBOT_MAX_SPEED", "robot.motion.max_speed", "robot.motion.max_speed", 80.0))
ROBOT_TRAVEL_SPEED = float(_setup_or_env_or_cfg("ROBOT_TRAVEL_SPEED", "robot.motion.travel_speed", "robot.motion.travel_speed", 30.0))
ROBOT_LIFT_SPEED = float(_setup_or_env_or_cfg("ROBOT_LIFT_SPEED", "robot.motion.lift_speed", "robot.motion.lift_speed", 30.0))
ROBOT_APPROACH_SPEED = float(_setup_or_env_or_cfg("ROBOT_APPROACH_SPEED", "robot.motion.approach_speed", "robot.motion.approach_speed", 15.0))
ROBOT_DEFAULT_ACCELERATION = float(
    _setup_or_env_or_cfg("ROBOT_DEFAULT_ACCELERATION", "robot.motion.default_acceleration", "robot.motion.default_acceleration", 60.0)
)
ROBOT_MOTION_TIMEOUT_SEC = float(
    _setup_or_env_or_cfg("ROBOT_MOTION_TIMEOUT_SEC", "robot.motion.timeout_sec", "robot.motion.timeout_sec", 10.0)
)
ROBOT_PLACE_Z_OFFSET = float(
    _setup_or_env_or_cfg("ROBOT_PLACE_Z_OFFSET", "robot.motion.place_z_offset", "robot.motion.place_z_offset", 2.0)
)
ROBOT_TOOL_RX = float(_setup_or_env_or_cfg("ROBOT_TOOL_RX", "robot.motion.tool_rx", "robot.motion.tool_rx", 0.0))
ROBOT_TOOL_RY = float(_setup_or_env_or_cfg("ROBOT_TOOL_RY", "robot.motion.tool_ry", "robot.motion.tool_ry", 0.0))
ROBOT_TOOL_RZ = float(_setup_or_env_or_cfg("ROBOT_TOOL_RZ", "robot.motion.tool_rz", "robot.motion.tool_rz", 0.0))
ROBOT_MOTION_REGISTER_BASE = int(_setup_or_env_or_cfg(
    "ROBOT_MOTION_REGISTER_BASE", "robot.modbus.motion_register_base", "robot.modbus.motion_register_base", 7000
))
ROBOT_PROFILE_REGISTER_BASE = int(_setup_or_env_or_cfg(
    "ROBOT_PROFILE_REGISTER_BASE", "robot.modbus.profile_register_base", "robot.modbus.profile_register_base", 7012
))
ROBOT_STATUS_REGISTER = int(_setup_or_env_or_cfg(
    "ROBOT_STATUS_REGISTER", "robot.modbus.status_register", "robot.modbus.status_register", 7100
))
ROBOT_STATUS_IDLE_VALUE = int(_setup_or_env_or_cfg(
    "ROBOT_STATUS_IDLE_VALUE", "robot.modbus.status_idle_value", "robot.modbus.status_idle_value", 0
))
ROBOT_STATUS_MOVING_VALUE = int(_setup_or_env_or_cfg(
    "ROBOT_STATUS_MOVING_VALUE", "robot.modbus.status_moving_value", "robot.modbus.status_moving_value", 1
))
ROBOT_STATUS_COMPLETE_VALUE = int(_setup_or_env_or_cfg(
    "ROBOT_STATUS_COMPLETE_VALUE", "robot.modbus.status_complete_value", "robot.modbus.status_complete_value", 2
))
ROBOT_STATUS_ERROR_VALUE = int(_setup_or_env_or_cfg(
    "ROBOT_STATUS_ERROR_VALUE", "robot.modbus.status_error_value", "robot.modbus.status_error_value", 3
))
ROBOT_HALT_REGISTER = int(_setup_or_env_or_cfg(
    "ROBOT_HALT_REGISTER", "robot.modbus.halt_register", "robot.modbus.halt_register", 7099
))
ROBOT_HALT_VALUE = int(_setup_or_env_or_cfg(
    "ROBOT_HALT_VALUE", "robot.modbus.halt_value", "robot.modbus.halt_value", 1
))
ROBOT_COMMAND_HANDSHAKE_ENABLED = _as_bool(_setup_or_env_or_cfg(
    "ROBOT_COMMAND_HANDSHAKE_ENABLED",
    "robot.modbus.command_handshake_enabled",
    "robot.modbus.command_handshake_enabled",
    True,
), default=True)
ROBOT_COMMAND_ID_REGISTER = int(_setup_or_env_or_cfg(
    "ROBOT_COMMAND_ID_REGISTER", "robot.modbus.command_id_register", "robot.modbus.command_id_register", 6998
))
ROBOT_COMMAND_TRIGGER_REGISTER = int(_setup_or_env_or_cfg(
    "ROBOT_COMMAND_TRIGGER_REGISTER", "robot.modbus.command_trigger_register", "robot.modbus.command_trigger_register", 6999
))
ROBOT_COMMAND_ACK_REGISTER = int(_setup_or_env_or_cfg(
    "ROBOT_COMMAND_ACK_REGISTER", "robot.modbus.command_ack_register", "robot.modbus.command_ack_register", 7101
))
ROBOT_ERROR_CODE_REGISTER = int(_setup_or_env_or_cfg(
    "ROBOT_ERROR_CODE_REGISTER", "robot.modbus.error_code_register", "robot.modbus.error_code_register", 7102
))
ROBOT_COMMAND_TRIGGER_VALUE = int(_setup_or_env_or_cfg(
    "ROBOT_COMMAND_TRIGGER_VALUE", "robot.modbus.command_trigger_value", "robot.modbus.command_trigger_value", 1
))
ROBOT_COMMAND_CLEAR_VALUE = int(_setup_or_env_or_cfg(
    "ROBOT_COMMAND_CLEAR_VALUE", "robot.modbus.command_clear_value", "robot.modbus.command_clear_value", 0
))
ROBOT_COMMAND_ID_WRAP = int(_setup_or_env_or_cfg(
    "ROBOT_COMMAND_ID_WRAP", "robot.modbus.command_id_wrap", "robot.modbus.command_id_wrap", 32767
))
ROBOT_COMMAND_ACK_TIMEOUT_SEC = float(_setup_or_env_or_cfg(
    "ROBOT_COMMAND_ACK_TIMEOUT_SEC", "robot.modbus.command_ack_timeout_sec", "robot.modbus.command_ack_timeout_sec", 2.0
))
ROBOT_REGISTER_SCALE = float(_setup_or_env_or_cfg(
    "ROBOT_REGISTER_SCALE", "robot.modbus.register_scale", "robot.modbus.register_scale", 100.0
))
ROBOT_REGISTER_ENCODING = str(
    _setup_or_env_or_cfg(
        "ROBOT_REGISTER_ENCODING", "robot.modbus.register_encoding", "robot.modbus.register_encoding", "scaled_int32"
    )
).strip().lower()
ROBOT_TELEMETRY_ENABLED = _as_bool(
    _setup_or_env_or_cfg(
        "ROBOT_TELEMETRY_ENABLED",
        "robot.modbus.telemetry_enabled",
        "robot.modbus.telemetry_enabled",
        False,
    ),
    default=False,
)
ROBOT_TELEMETRY_POSE_REGISTER_BASE = int(_setup_or_env_or_cfg(
    "ROBOT_TELEMETRY_POSE_REGISTER_BASE",
    "robot.modbus.telemetry_pose_register_base",
    "robot.modbus.telemetry_pose_register_base",
    7110,
))
ROBOT_TELEMETRY_JOINT_REGISTER_BASE = int(_setup_or_env_or_cfg(
    "ROBOT_TELEMETRY_JOINT_REGISTER_BASE",
    "robot.modbus.telemetry_joint_register_base",
    "robot.modbus.telemetry_joint_register_base",
    7122,
))
ROBOT_TELEMETRY_SPEED_REGISTER = int(_setup_or_env_or_cfg(
    "ROBOT_TELEMETRY_SPEED_REGISTER",
    "robot.modbus.telemetry_speed_register",
    "robot.modbus.telemetry_speed_register",
    7134,
))
ROBOT_GRIPPER_REGISTER = int(_setup_or_env_or_cfg(
    "ROBOT_GRIPPER_REGISTER", "robot.gripper.register", "robot.modbus.gripper_register", 7098
))
ROBOT_GRIPPER_CLOSE_VALUE = int(_setup_or_env_or_cfg(
    "ROBOT_GRIPPER_CLOSE_VALUE", "robot.gripper.close_value", "robot.modbus.gripper_close_value", 1
))
ROBOT_GRIPPER_OPEN_VALUE = int(_setup_or_env_or_cfg(
    "ROBOT_GRIPPER_OPEN_VALUE", "robot.gripper.open_value", "robot.modbus.gripper_open_value", 0
))
ROBOT_GRIPPER_FEEDBACK_ENABLED = _as_bool(_setup_or_env_or_cfg(
    "ROBOT_GRIPPER_FEEDBACK_ENABLED",
    "robot.gripper.feedback_enabled",
    "robot.modbus.gripper_feedback_enabled",
    True,
), default=True)
ROBOT_GRIPPER_STATUS_REGISTER = int(_setup_or_env_or_cfg(
    "ROBOT_GRIPPER_STATUS_REGISTER", "robot.gripper.status_register", "robot.modbus.gripper_status_register", 7103
))
ROBOT_GRIPPER_OPENED_VALUE = int(_setup_or_env_or_cfg(
    "ROBOT_GRIPPER_OPENED_VALUE", "robot.gripper.opened_value", "robot.modbus.gripper_opened_value", 0
))
ROBOT_GRIPPER_CLOSED_VALUE = int(_setup_or_env_or_cfg(
    "ROBOT_GRIPPER_CLOSED_VALUE", "robot.gripper.closed_value", "robot.modbus.gripper_closed_value", 1
))
ROBOT_GRIPPER_ERROR_VALUE = int(_setup_or_env_or_cfg(
    "ROBOT_GRIPPER_ERROR_VALUE", "robot.gripper.error_value", "robot.modbus.gripper_error_value", 2
))
ROBOT_GRIPPER_FEEDBACK_TIMEOUT_SEC = float(_setup_or_env_or_cfg(
    "ROBOT_GRIPPER_FEEDBACK_TIMEOUT_SEC",
    "robot.gripper.feedback_timeout_sec",
    "robot.modbus.gripper_feedback_timeout_sec",
    2.0,
))
ROBOT_GRIPPER_CLOSE_SCRIPT = str(
    _setup_or_env_or_cfg("ROBOT_GRIPPER_CLOSE_SCRIPT", "robot.gripper.close_script", "robot.techmanpy.gripper_close_script", "")
)
ROBOT_GRIPPER_OPEN_SCRIPT = str(
    _setup_or_env_or_cfg("ROBOT_GRIPPER_OPEN_SCRIPT", "robot.gripper.open_script", "robot.techmanpy.gripper_open_script", "")
)
ROBOT_GRIPPER_CLOSE_DWELL_SEC = float(_setup_or_env_or_cfg(
    "ROBOT_GRIPPER_CLOSE_DWELL_SEC", "robot.gripper.close_dwell_sec", "robot.modbus.gripper_close_dwell_sec", 0.5
))
ROBOT_GRIPPER_OPEN_DWELL_SEC = float(_setup_or_env_or_cfg(
    "ROBOT_GRIPPER_OPEN_DWELL_SEC", "robot.gripper.open_dwell_sec", "robot.modbus.gripper_open_dwell_sec", 0.5
))
ROBOT_VERIFY_STATUS_ON_CONNECT = _as_bool(
    _setup_or_env_or_cfg(
        "ROBOT_VERIFY_STATUS_ON_CONNECT",
        "robot.modbus.verify_status_on_connect",
        "robot.modbus.verify_status_on_connect",
        False,
    ),
    default=False,
)

# Board
BOARD_ROWS = 10
BOARD_COLS = 9
FILES = "abcdefghi"
RANKS = [9, 8, 7, 6, 5, 4, 3, 2, 1, 0]
