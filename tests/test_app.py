import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app


class ConfigurationTests(unittest.TestCase):
    def test_optional_features_are_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            features = app.feature_config()
        self.assertFalse(features["electrs"]["enabled"])
        self.assertFalse(features["tor"]["enabled"])
        self.assertFalse(features["mempool_explorer"]["enabled"])
        self.assertFalse(features["host_metrics"]["enabled"])

    def test_optional_features_can_be_enabled(self):
        environment = {
            "ELECTRS_ENABLED": "true",
            "TOR_ENABLED": "1",
            "MEMPOOL_EXPLORER_ENABLED": "yes",
            "MEMPOOL_EXPLORER_URL": "https://mempool.example.test",
            "HOST_METRICS_ENABLED": "on",
        }
        with patch.dict(os.environ, environment, clear=True):
            features = app.feature_config()
        self.assertTrue(features["electrs"]["enabled"])
        self.assertTrue(features["tor"]["enabled"])
        self.assertTrue(features["mempool_explorer"]["enabled"])
        self.assertEqual(
            features["mempool_explorer"]["url"],
            "https://mempool.example.test",
        )
        self.assertTrue(features["host_metrics"]["enabled"])

    def test_disabled_electrs_is_not_contacted(self):
        with patch.dict(os.environ, {"ELECTRS_ENABLED": "false"}, clear=True):
            self.assertIsNone(app.get_electrs_status())

    def test_tor_status_uses_knots_network_reachability(self):
        network = {"networks": [{"name": "onion", "reachable": True}]}
        with patch.dict(os.environ, {"TOR_ENABLED": "true"}, clear=True):
            status = app.get_tor_status(network)
        self.assertTrue(status["running"])
        self.assertEqual(status["status"], "docker")

    def test_rpc_password_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rpc_password"
            path.write_text("correct horse battery staple\n", encoding="utf-8")
            with patch.dict(
                os.environ,
                {"BITCOIN_RPC_PASSWORD_FILE": str(path)},
                clear=True,
            ):
                password = app.read_secret(
                    "BITCOIN_RPC_PASSWORD", "BITCOIN_RPC_PASSWORD_FILE"
                )
        self.assertEqual(password, "correct horse battery staple")


if __name__ == "__main__":
    unittest.main()
