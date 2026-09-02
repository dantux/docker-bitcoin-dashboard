import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app


class ConfigurationTests(unittest.TestCase):
    def test_dashboard_instance_name_defaults_to_bitcoin_knots(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(app.dashboard_instance_name(), "bitcoin-knots")

    def test_dashboard_instance_name_prefers_explicit_instance_name(self):
        environment = {
            "DASHBOARD_INSTANCE_NAME": "knots-pi5",
            "NODE_NAME": "legacy-name",
        }
        with patch.dict(os.environ, environment, clear=True):
            self.assertEqual(app.dashboard_instance_name(), "knots-pi5")

    def test_dashboard_instance_name_supports_legacy_node_name(self):
        with patch.dict(os.environ, {"NODE_NAME": "legacy-name"}, clear=True):
            self.assertEqual(app.dashboard_instance_name(), "legacy-name")

    def test_pruning_fields_are_exposed(self):
        sync = app.blockchain_sync_status(
            {
                "verificationprogress": 0.99999,
                "pruned": True,
                "pruneheight": 900000,
                "automatic_pruning": True,
                "prune_target_size": 5_242_880_000,
                "size_on_disk": 5_190_617_191,
            }
        )
        self.assertTrue(sync["pruned"])
        self.assertEqual(sync["prune_height"], 900000)
        self.assertTrue(sync["automatic_pruning"])
        self.assertEqual(sync["prune_target_size_bytes"], 5_242_880_000)
        self.assertEqual(sync["size_on_disk_bytes"], 5_190_617_191)
        self.assertEqual(sync["progress_percent"], 100.0)

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


class PageStructureTests(unittest.TestCase):
    def test_latest_blocks_appears_before_services(self):
        html = Path(app.APP_DIR / "index.html").read_text(encoding="utf-8")

        self.assertLess(html.index("<h2>Latest Blocks</h2>"), html.index("<h2>Services</h2>"))


if __name__ == "__main__":
    unittest.main()
