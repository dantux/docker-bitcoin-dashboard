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

    def test_knots_version_label_from_subversion(self):
        self.assertEqual(
            app.knots_version_label("/Satoshi:29.3.0/Knots:20260210/"),
            "29.3.0 (Knots 20260210)",
        )

    def test_knots_version_label_is_empty_when_missing(self):
        self.assertEqual(app.knots_version_label(None), "")
        self.assertEqual(app.knots_version_label(""), "")

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

    def test_collect_status_skips_optional_rpc_work_during_initial_block_download(self):
        calls = []

        def fake_bitcoin_rpc(method, params=None):
            calls.append(method)
            responses = {
                "getblockchaininfo": {
                    "chain": "main",
                    "blocks": 0,
                    "headers": 1,
                    "initialblockdownload": True,
                },
                "getnetworkinfo": {"connections": 0, "networks": []},
                "uptime": 1,
            }
            if method not in responses:
                raise AssertionError(f"unexpected RPC method: {method}")
            return responses[method]

        with patch.dict(os.environ, {}, clear=True), patch.object(
            app, "bitcoin_rpc", side_effect=fake_bitcoin_rpc
        ):
            status = app.collect_status()

        self.assertEqual(calls, ["getblockchaininfo", "getnetworkinfo", "uptime"])
        self.assertEqual(status["recent_blocks"], [])
        self.assertEqual(status["peers"], [])
        self.assertEqual(status["mempool"]["fee_estimates"], {})

    def test_collect_status_skips_optional_rpc_work_when_ibd_state_is_unknown(self):
        calls = []

        def fake_bitcoin_rpc(method, params=None):
            calls.append(method)
            if method == "getblockchaininfo":
                raise TimeoutError("timed out")
            responses = {
                "getnetworkinfo": {"connections": 0, "networks": []},
                "uptime": 1,
            }
            if method not in responses:
                raise AssertionError(f"unexpected RPC method: {method}")
            return responses[method]

        with patch.dict(os.environ, {}, clear=True), patch.object(
            app, "bitcoin_rpc", side_effect=fake_bitcoin_rpc
        ):
            status = app.collect_status()

        self.assertEqual(calls, ["getblockchaininfo", "getnetworkinfo", "uptime"])
        self.assertEqual(status["recent_blocks"], [])
        self.assertEqual(status["peers"], [])
        self.assertEqual(status["mempool"]["fee_estimates"], {})
        self.assertEqual(status["errors"][0]["source"], "getblockchaininfo")


class PageStructureTests(unittest.TestCase):
    def test_latest_blocks_appears_before_services(self):
        html = Path(app.APP_DIR / "index.html").read_text(encoding="utf-8")

        self.assertLess(html.index("<h2>Latest Blocks</h2>"), html.index("<h2>Services</h2>"))

    def test_header_includes_knots_version(self):
        html = Path(app.APP_DIR / "index.html").read_text(encoding="utf-8")

        self.assertIn('id="knots-version"', html)

    def test_desktop_metric_grid_uses_seven_columns(self):
        css = Path(app.APP_DIR / "styles.css").read_text(encoding="utf-8")
        desktop_css = css.split("@media", 1)[0]

        self.assertIn("grid-template-columns: repeat(7, minmax(0, 1fr));", desktop_css)

    def test_desktop_metric_grid_uses_eight_columns_when_tor_is_visible(self):
        css = Path(app.APP_DIR / "styles.css").read_text(encoding="utf-8")
        desktop_css = css.split("@media", 1)[0]

        self.assertIn(
            '.metric-grid:has(> .metric[data-feature="tor"]:not(.hidden))',
            desktop_css,
        )
        self.assertIn("repeat(8, minmax(0, 1fr))", desktop_css)

    def test_one_hour_fee_card_is_not_rendered(self):
        html = Path(app.APP_DIR / "index.html").read_text(encoding="utf-8")

        self.assertNotIn('id="fee-1h"', html)


if __name__ == "__main__":
    unittest.main()
