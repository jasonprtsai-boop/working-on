import structlog
import logging
import sys

# Configure standard library logging for external dependencies
logging.basicConfig(
    format="%(message)s",
    stream=sys.stdout,
    level=logging.INFO,
)

# Configure structlog for industrial-grade JSON/Structured output
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

def log_move_cycle(context, move, confidence, status):
    """
    Standardized logging for the move lifecycle.
    Attaches trace_id and session_id to every log entry for cross-system correlation.
    """
    logger.info(
        "move_cycle_execution",
        trace_id=context.trace_id,
        session_id=context.session_id,
        move=move,
        confidence=confidence,
        status=status
    )
