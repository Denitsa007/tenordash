import os
import tempfile
import unittest
import importlib.util

import db

if importlib.util.find_spec("flask") is not None:
    import app as app_module
else:
    app_module = None


@unittest.skipUnless(app_module is not None, "flask is not installed in this environment")
class SettingsApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        db_path = os.path.join(self.tmpdir.name, "test_settings.db")

        orig_db_path = db.DB_PATH
        self.addCleanup(setattr, db, "DB_PATH", orig_db_path)
        db.DB_PATH = db_path
        db.init_db()

        orig_testing = app_module.app.config.get("TESTING")
        orig_propagate = app_module.app.config.get("PROPAGATE_EXCEPTIONS")
        self.addCleanup(app_module.app.config.__setitem__, "TESTING", orig_testing)
        self.addCleanup(app_module.app.config.__setitem__, "PROPAGATE_EXCEPTIONS", orig_propagate)
        app_module.app.config["TESTING"] = True
        app_module.app.config["PROPAGATE_EXCEPTIONS"] = False
        self.client = app_module.app.test_client()

    # ── Browse Dirs ──

    def test_browse_dirs_home(self):
        res = self.client.get("/api/browse-dirs")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("path", data)
        self.assertIn("dirs", data)
        self.assertIn("writable", data)
        self.assertIsInstance(data["dirs"], list)

    def test_browse_dirs_explicit_path(self):
        res = self.client.get(f"/api/browse-dirs?path={self.tmpdir.name}")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["path"], self.tmpdir.name)

    def test_browse_dirs_nonexistent(self):
        res = self.client.get("/api/browse-dirs?path=/nonexistent/xyz")
        self.assertEqual(res.status_code, 400)

    def test_browse_dirs_relative(self):
        res = self.client.get("/api/browse-dirs?path=relative")
        self.assertEqual(res.status_code, 400)

    def test_browse_dirs_hides_dotfiles(self):
        os.makedirs(os.path.join(self.tmpdir.name, ".hidden"))
        os.makedirs(os.path.join(self.tmpdir.name, "visible"))
        res = self.client.get(f"/api/browse-dirs?path={self.tmpdir.name}")
        data = res.get_json()
        self.assertNotIn(".hidden", data["dirs"])
        self.assertIn("visible", data["dirs"])

    def test_browse_dirs_sorted(self):
        os.makedirs(os.path.join(self.tmpdir.name, "zebra"))
        os.makedirs(os.path.join(self.tmpdir.name, "alpha"))
        os.makedirs(os.path.join(self.tmpdir.name, "mango"))
        res = self.client.get(f"/api/browse-dirs?path={self.tmpdir.name}")
        data = res.get_json()
        visible = [d for d in data["dirs"] if d in ("alpha", "mango", "zebra")]
        self.assertEqual(visible, ["alpha", "mango", "zebra"])

    def test_browse_dirs_writable(self):
        res = self.client.get(f"/api/browse-dirs?path={self.tmpdir.name}")
        data = res.get_json()
        self.assertTrue(data["writable"])

    # ── Settings API ──

    def test_get_settings_defaults(self):
        res = self.client.get("/api/settings")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("export_path", data)

    def test_save_and_load_export_path(self):
        export_dir = os.path.join(self.tmpdir.name, "exports")
        os.makedirs(export_dir)
        res = self.client.put("/api/settings", json={"export_path": export_dir})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["ok"])

        res = self.client.get("/api/settings")
        self.assertEqual(res.get_json()["export_path"], export_dir)

    def test_save_nonexistent_path_fails(self):
        res = self.client.put("/api/settings", json={"export_path": "/nonexistent/xyz"})
        self.assertEqual(res.status_code, 400)

    def test_save_relative_path_fails(self):
        res = self.client.put("/api/settings", json={"export_path": "relative/path"})
        self.assertEqual(res.status_code, 400)

    def test_unknown_key_rejected(self):
        res = self.client.put("/api/settings", json={"unknown_key": "value"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("Unknown setting", res.get_json()["error"])

    def test_unknown_key_mixed_with_valid_rejected(self):
        """If any unknown key is present, the entire request is rejected."""
        export_dir = os.path.join(self.tmpdir.name, "exports2")
        os.makedirs(export_dir)
        res = self.client.put("/api/settings", json={
            "export_path": export_dir,
            "bad_key": "value",
        })
        self.assertEqual(res.status_code, 400)


if __name__ == "__main__":
    unittest.main()
