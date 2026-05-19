import logging
import os
import sys
import io
import queue
from logging.handlers import RotatingFileHandler, QueueHandler, QueueListener
from backend.utils import config

# --- Global Logging Infrastructure ---
_log_queue = queue.Queue(maxsize=max(1, int(getattr(config, "LOG_QUEUE_SIZE", 10000))))
_listener = None
_log_dir = "logs"
os.makedirs(_log_dir, exist_ok=True)

# Common Formatter
_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def _setup_shared_handlers():
    """Initializes the physical handlers that process the queue."""
    level_name = getattr(logging, config.LOG_LEVEL, logging.INFO)

    # Console Handler (UTF-8 forced)
    stream = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8') if hasattr(sys.stdout, 'buffer') else sys.stdout
    ch = logging.StreamHandler(stream)
    ch.setLevel(level_name)
    ch.setFormatter(_formatter)

    # File Handler
    log_file = os.path.join(_log_dir, "app.log")
    fh = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
    fh.setLevel(level_name)
    fh.setFormatter(_formatter)

    return ch, fh

def setup_logger(name: str = "system") -> logging.Logger:
    global _listener
    logger = logging.getLogger(name)

    # Avoid duplicate handlers if setup_logger is called multiple times for same name
    if not logger.handlers:
        level_name = getattr(logging, config.LOG_LEVEL, logging.INFO)
        logger.setLevel(level_name)
        logger.propagate = False

        # All loggers send records to the global queue
        queue_handler = QueueHandler(_log_queue)
        logger.addHandler(queue_handler)

        # Initialize Shared Listener once
        if _listener is None:
            ch, fh = _setup_shared_handlers()
            _listener = QueueListener(_log_queue, ch, fh, respect_handler_level=True)
            _listener.start()

    return logger

def get_logger(module_name: str) -> logging.Logger:
    """Standard entry point for module-specific loggers."""
    return setup_logger(module_name)

# Default global logger instance
logger = setup_logger("system")
