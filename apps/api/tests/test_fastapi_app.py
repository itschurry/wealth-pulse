from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app


class FastApiAppTests(unittest.TestCase):
    def test_health_endpoint_returns_ok(self):
        client = TestClient(app)

        response = client.get("/health")

        self.assertEqual(200, response.status_code)
        self.assertEqual({"status": "ok"}, response.json())

    def test_legacy_api_route_uses_dispatcher(self):
        client = TestClient(app)

        with patch("app.routers.legacy_api.dispatch_get", return_value=(200, {"ok": True})) as mock_dispatch:
            response = client.get("/api/system/mode")

        self.assertEqual(200, response.status_code)
        self.assertEqual({"ok": True}, response.json())
        mock_dispatch.assert_called_once_with("/api/system/mode", {})
