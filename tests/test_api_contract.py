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
class ApiContractTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.orig_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.tmpdir.name, "test_api.db")
        db.init_db()

        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()

    def tearDown(self):
        db.DB_PATH = self.orig_db_path
        self.tmpdir.cleanup()

    def test_suggest_continuation_validation(self):
        res = self.client.get("/api/suggest-continuation")
        self.assertEqual(res.status_code, 400)

        res = self.client.get("/api/suggest-continuation?end_date=bad-date")
        self.assertEqual(res.status_code, 400)

        res = self.client.get("/api/suggest-continuation?end_date=2026-01-12")
        self.assertEqual(res.status_code, 200)
        self.assertIn("continuation_date", res.get_json())

    def test_check_cl_capacity_validation(self):
        res = self.client.get("/api/check-cl-capacity")
        self.assertEqual(res.status_code, 400)

        res = self.client.get("/api/check-cl-capacity?cl_id=CL999&amount=1000")
        self.assertEqual(res.status_code, 404)

    def test_currency_api_invalid_and_duplicate(self):
        res = self.client.post("/api/currencies", json={"code": "US"})
        self.assertEqual(res.status_code, 400)

        res = self.client.post("/api/currencies", json={"code": "CHF"})
        self.assertEqual(res.status_code, 409)

        res = self.client.delete("/api/currencies/CHF")
        self.assertEqual(res.status_code, 400)

    def test_credit_line_and_advance_happy_path(self):
        res = self.client.post("/banks", json={"bank_key": "B001", "bank_name": "Bank 1"})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["ok"])

        cl_payload = {
            "bank_key": "B001",
            "description": "Syndicated Facility",
            "currency": "CHF",
            "amount": 510_000_000,
            "committed": "Yes",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "note": "Contract test",
        }
        res = self.client.post("/credit-lines", json=cl_payload)
        self.assertEqual(res.status_code, 200)
        cl_id = res.get_json()["id"]
        self.assertTrue(cl_id.startswith("CL"))

        res = self.client.get(f"/credit-lines/{cl_id}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["id"], cl_id)

        update_payload = dict(cl_payload)
        update_payload["description"] = "Updated Facility"
        res = self.client.put(f"/credit-lines/{cl_id}", json=update_payload)
        self.assertEqual(res.status_code, 200)

        adv_payload = {
            "bank": "Bank 1",
            "credit_line_id": cl_id,
            "start_date": "2026-01-10",
            "end_date": "2026-02-10",
            "continuation_date": "2026-02-05",
            "currency": "CHF",
            "amount_original": 50_000_000,
            "interest_amount": 196_527.78,
        }
        res = self.client.post("/advances", json=adv_payload)
        self.assertEqual(res.status_code, 200)
        fv_id = res.get_json()["id"]
        self.assertTrue(fv_id.startswith("FV"))

        res = self.client.get(f"/advances/{fv_id}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["id"], fv_id)

        adv_update = dict(adv_payload)
        adv_update["interest_amount"] = 200_000.0
        res = self.client.put(f"/advances/{fv_id}", json=adv_update)
        self.assertEqual(res.status_code, 200)

        res = self.client.get(f"/api/check-cl-capacity?cl_id={cl_id}&amount=1")
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertIn("facility", body)
        self.assertIn("current_drawn", body)
        self.assertIn("new_drawn", body)
        self.assertIn("exceeded", body)

        res = self.client.delete(f"/advances/{fv_id}")
        self.assertEqual(res.status_code, 200)

        res = self.client.delete(f"/credit-lines/{cl_id}")
        self.assertEqual(res.status_code, 200)

        res = self.client.delete("/banks/B001")
        self.assertEqual(res.status_code, 200)

    def test_not_found_get_endpoints(self):
        res = self.client.get("/credit-lines/CL999")
        self.assertEqual(res.status_code, 404)

        res = self.client.get("/advances/FV9999")
        self.assertEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main()
