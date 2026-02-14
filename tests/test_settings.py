import os
import tempfile
import unittest
import importlib.util

import db
import helpers

if importlib.util.find_spec("flask") is not None:
    import app as app_module
else:
    app_module = None


class SettingsDbTests(unittest.TestCase):
    """Tests for settings table helpers in db.py."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        db_path = os.path.join(self.tmpdir.name, "test_settings.db")

        self._orig_db_path = db.DB_PATH
        self.addCleanup(setattr, db, "DB_PATH", self._orig_db_path)
        db.DB_PATH = db_path
        db.init_db()

    def test_get_setting_returns_default_when_missing(self):
        conn = db.get_db()
        try:
            result = db.get_setting(conn, "nonexistent", default="fallback")
            self.assertEqual(result, "fallback")
        finally:
            conn.close()

    def test_get_setting_returns_none_when_missing_no_default(self):
        conn = db.get_db()
        try:
            result = db.get_setting(conn, "nonexistent")
            self.assertIsNone(result)
        finally:
            conn.close()

    def test_set_setting_inserts_new_key(self):
        conn = db.get_db()
        try:
            db.set_setting(conn, "test_key", "test_value")
            result = db.get_setting(conn, "test_key")
            self.assertEqual(result, "test_value")
        finally:
            conn.close()

    def test_set_setting_upserts_existing_key(self):
        conn = db.get_db()
        try:
            db.set_setting(conn, "display_unit", "full")
            result = db.get_setting(conn, "display_unit")
            self.assertEqual(result, "full")

            db.set_setting(conn, "display_unit", "thousands")
            result = db.get_setting(conn, "display_unit")
            self.assertEqual(result, "thousands")
        finally:
            conn.close()

    def test_get_all_settings_returns_seeded_defaults(self):
        conn = db.get_db()
        try:
            settings = db.get_all_settings(conn)
            self.assertIn("display_unit", settings)
            self.assertIn("export_path", settings)
            self.assertEqual(settings["display_unit"], "millions")
        finally:
            conn.close()

    def test_seed_settings_idempotent(self):
        """Calling init_db again should not overwrite changed settings."""
        conn = db.get_db()
        try:
            db.set_setting(conn, "display_unit", "full")
        finally:
            conn.close()

        # Re-init should not reset the value
        db.init_db()

        conn = db.get_db()
        try:
            result = db.get_setting(conn, "display_unit")
            self.assertEqual(result, "full")
        finally:
            conn.close()


class FormatThousandsTests(unittest.TestCase):
    def test_format_millions(self):
        self.assertEqual(helpers.format_amount_thousands(80_000_000), "80,000K")

    def test_format_thousands(self):
        self.assertEqual(helpers.format_amount_thousands(50_000), "50K")

    def test_format_small(self):
        self.assertEqual(helpers.format_amount_thousands(500), "0K")


@unittest.skipUnless(app_module is not None, "flask is not installed")
class SettingsApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        db_path = os.path.join(self.tmpdir.name, "test_api.db")

        self._orig_db_path = db.DB_PATH
        self.addCleanup(setattr, db, "DB_PATH", self._orig_db_path)
        db.DB_PATH = db_path
        db.init_db()

        orig_testing = app_module.app.config.get("TESTING")
        orig_propagate = app_module.app.config.get("PROPAGATE_EXCEPTIONS")
        self.addCleanup(app_module.app.config.__setitem__, "TESTING", orig_testing)
        self.addCleanup(app_module.app.config.__setitem__, "PROPAGATE_EXCEPTIONS", orig_propagate)
        app_module.app.config["TESTING"] = True
        app_module.app.config["PROPAGATE_EXCEPTIONS"] = False
        self.client = app_module.app.test_client()

    def test_get_settings_returns_defaults(self):
        res = self.client.get("/api/settings")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("display_unit", data)
        self.assertEqual(data["display_unit"], "millions")

    def test_put_valid_display_unit(self):
        for unit in ("full", "thousands", "millions"):
            res = self.client.put("/api/settings", json={"key": "display_unit", "value": unit})
            self.assertEqual(res.status_code, 200)
            self.assertTrue(res.get_json()["ok"])

        # Verify it stuck
        res = self.client.get("/api/settings")
        self.assertEqual(res.get_json()["display_unit"], "millions")

    def test_put_invalid_display_unit(self):
        res = self.client.put("/api/settings", json={"key": "display_unit", "value": "billions"})
        self.assertEqual(res.status_code, 400)
        self.assertFalse(res.get_json()["ok"])

    def test_put_valid_export_path(self):
        path = self.tmpdir.name
        res = self.client.put("/api/settings", json={"key": "export_path", "value": path})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["ok"])

    def test_put_nonexistent_export_path(self):
        res = self.client.put("/api/settings", json={"key": "export_path", "value": "/nonexistent/path/xyz"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("does not exist", res.get_json()["error"])

    def test_put_relative_export_path(self):
        res = self.client.put("/api/settings", json={"key": "export_path", "value": "relative/path"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("absolute", res.get_json()["error"])

    def test_put_unknown_key(self):
        res = self.client.put("/api/settings", json={"key": "unknown_key", "value": "whatever"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("Unknown setting", res.get_json()["error"])


@unittest.skipUnless(app_module is not None, "flask is not installed")
class AmountShortFilterTests(unittest.TestCase):
    """Test that the amount_short filter respects display_unit setting."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        db_path = os.path.join(self.tmpdir.name, "test_filter.db")

        self._orig_db_path = db.DB_PATH
        self.addCleanup(setattr, db, "DB_PATH", self._orig_db_path)
        db.DB_PATH = db_path
        db.init_db()

        app_module.app.config["TESTING"] = True

    def _filter_with_unit(self, unit, value):
        """Call the amount_short filter with a given display_unit."""
        conn = db.get_db()
        try:
            db.set_setting(conn, "display_unit", unit)
        finally:
            conn.close()

        with app_module.app.test_request_context():
            # Load settings into g the same way the context processor does
            from flask import g
            g.settings = db.get_all_settings(db.get_db())
            return app_module.amount_short_filter(value)

    def test_millions_default(self):
        result = self._filter_with_unit("millions", 80_000_000)
        self.assertEqual(result, "80M")

    def test_thousands(self):
        result = self._filter_with_unit("thousands", 80_000_000)
        self.assertEqual(result, "80,000K")

    def test_full(self):
        result = self._filter_with_unit("full", 80_000_000)
        self.assertEqual(result, "80,000,000")

    def test_invalid_value_passthrough(self):
        result = self._filter_with_unit("millions", "not-a-number")
        self.assertEqual(result, "not-a-number")


if __name__ == "__main__":
    unittest.main()
