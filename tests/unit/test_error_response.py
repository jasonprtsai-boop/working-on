import unittest
from unittest.mock import patch

from flask import Flask

from backend.interfaces.api.shared import error_response


class TestErrorResponse(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)

    def test_server_error_publishes_diagnostics(self):
        with self.app.test_request_context("/api/unit", method="POST"):
            with patch("backend.interfaces.api.shared.publish_error_diagnostic") as publish:
                response, status = error_response(
                    "internal_error",
                    "unit failure",
                    500,
                    trace_id="trace-api",
                    recoverable=False,
                )

        self.assertEqual(status, 500)
        payload = response.get_json()
        self.assertEqual(payload["code"], "internal_error")
        publish.assert_called_once()
        kwargs = publish.call_args.kwargs
        self.assertEqual(kwargs["code"], "internal_error")
        self.assertEqual(kwargs["trace_id"], "trace-api")
        self.assertEqual(kwargs["details"]["path"], "/api/unit")

    def test_client_error_does_not_emit_system_diagnostics(self):
        with self.app.test_request_context("/api/unit", method="POST"):
            with patch("backend.interfaces.api.shared.publish_error_diagnostic") as publish:
                _response, status = error_response(
                    "validation_failed",
                    "invalid payload",
                    400,
                    recoverable=True,
                )

        self.assertEqual(status, 400)
        publish.assert_not_called()


if __name__ == "__main__":
    unittest.main()
