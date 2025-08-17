# Utils package

# Re-export functions from the legacy utils module for backward compatibility
from .legacy import (
    EmailData,
    generate_new_account_email,
    generate_password_reset_token,
    generate_reset_password_email,
    generate_test_email,
    render_email_template,
    send_email,
    verify_password_reset_token,
)

# Export new logging utilities
from .log import (
    StructuredFormatter,
    get_structured_logger,
    log_authentication_event,
    log_database_operation,
    log_telemetry_event,
    set_device_context,
    set_request_context,
    set_user_context,
)
from .logging_deps import (
    get_current_device_with_logging,
    get_current_user_with_logging,
)

__all__ = [
    # Legacy utils functions
    "EmailData",
    "generate_new_account_email",
    "generate_password_reset_token",
    "generate_reset_password_email",
    "generate_test_email",
    "render_email_template",
    "send_email",
    "verify_password_reset_token",
    # New logging utilities
    "StructuredFormatter",
    "get_structured_logger",
    "log_authentication_event",
    "log_database_operation",
    "log_telemetry_event",
    "set_device_context",
    "set_request_context",
    "set_user_context",
    "get_current_device_with_logging",
    "get_current_user_with_logging",
]
