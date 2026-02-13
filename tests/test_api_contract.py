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
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        db_path = os.path.join(tmpdir.name, "test_api.db")

        orig_db_path = db.DB_PATH
        self.addCleanup(setattr, db, "DB_PATH", orig_db_path)
        db.DB_PATH = db_path
        db.init_db()

        conn = db.get_db()
        try:
            conn.execute(
                "INSERT INTO banks (bank_key, bank_name) VALUES (?, ?)",
                ("B001", "Bank 1"),
            )
            conn.commit()
        finally:
            conn.close()

        orig_testing = app_module.app.config.get("TESTING")
        orig_propagate = app_module.app.config.get("PROPAGATE_EXCEPTIONS")
        self.addCleanup(app_module.app.config.__setitem__, "TESTING", orig_testing)
        self.addCleanup(app_module.app.config.__setitem__, "PROPAGATE_EXCEPTIONS", orig_propagate)
        app_module.app.config["TESTING"] = True
        app_module.app.config["PROPAGATE_EXCEPTIONS"] = False
        self.client = app_module.app.test_client()

    def _credit_line_payload(self):
        return {
            "bank_key": "B001",
            "description": "Syndicated Facility",
            "currency": "CHF",
            "amount": 510_000_000,
            "committed": "Yes",
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "note": "Contract test",
        }

    def _advance_payload(self, cl_id):
        return {
            "bank": "Bank 1",
            "credit_line_id": cl_id,
            "start_date": "2026-01-10",
            "end_date": "2026-02-10",
            "continuation_date": "2026-02-05",
            "currency": "CHF",
            "amount_original": 50_000_000,
            "interest_amount": 196_527.78,
        }

    def _create_credit_line(self):
        res = self.client.post("/credit-lines", json=self._credit_line_payload())
        self.assertEqual(res.status_code, 200)
        return res.get_json()["id"]

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

        res = self.client.get("/api/check-cl-capacity?cl_id=CL001&amount=not-a-number")
        self.assertEqual(res.status_code, 400)

    def test_currency_api_invalid_and_duplicate(self):
        res = self.client.post("/api/currencies", json={"code": "US"})
        self.assertEqual(res.status_code, 400)

        res = self.client.post("/api/currencies", json={"code": "CHF"})
        self.assertEqual(res.status_code, 409)

        res = self.client.delete("/api/currencies/CHF")
        self.assertEqual(res.status_code, 400)

    def test_non_json_payload_returns_400(self):
        res = self.client.post(
            "/banks",
            data="bank_key=B003&bank_name=Bank 3",
            content_type="text/plain",
        )
        self.assertEqual(res.status_code, 400)

    def test_bank_happy_path(self):
        res = self.client.post("/banks", json={"bank_key": "B002", "bank_name": "Bank 2"})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["ok"])

        res = self.client.delete("/banks/B002")
        self.assertEqual(res.status_code, 200)

    def test_credit_line_happy_path(self):
        cl_payload = self._credit_line_payload()
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

        res = self.client.delete(f"/credit-lines/{cl_id}")
        self.assertEqual(res.status_code, 200)

    def test_advance_happy_path(self):
        cl_id = self._create_credit_line()
        adv_payload = self._advance_payload(cl_id)
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

        res = self.client.delete(f"/advances/{fv_id}")
        self.assertEqual(res.status_code, 200)

    def test_check_cl_capacity_happy_path(self):
        cl_id = self._create_credit_line()
        res = self.client.post("/advances", json=self._advance_payload(cl_id))
        self.assertEqual(res.status_code, 200)

        res = self.client.get(f"/api/check-cl-capacity?cl_id={cl_id}&amount=1")
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertIn("facility", body)
        self.assertIn("current_drawn", body)
        self.assertIn("new_drawn", body)
        self.assertIn("exceeded", body)

    def test_not_found_get_endpoints(self):
        res = self.client.get("/credit-lines/CL999")
        self.assertEqual(res.status_code, 404)

        res = self.client.get("/advances/FV9999")
        self.assertEqual(res.status_code, 404)

    def test_credit_line_create_missing_required_field_fails(self):
        payload = self._credit_line_payload()
        payload.pop("bank_key")

        res = self.client.post("/credit-lines", json=payload)
        self.assertEqual(res.status_code, 400)

    def test_advance_create_missing_required_field_fails(self):
        cl_id = self._create_credit_line()
        payload = self._advance_payload(cl_id)
        payload.pop("amount_original")

        res = self.client.post("/advances", json=payload)
        self.assertEqual(res.status_code, 400)

    def test_advance_create_invalid_date_order_fails(self):
        cl_id = self._create_credit_line()
        payload = self._advance_payload(cl_id)
        payload["start_date"] = "2026-02-10"
        payload["end_date"] = "2026-02-10"

        res = self.client.post("/advances", json=payload)
        self.assertEqual(res.status_code, 400)
        self.assertIn("end_date must be later than start_date", res.get_json()["error"])

    def test_advance_update_invalid_date_order_fails(self):
        cl_id = self._create_credit_line()
        payload = self._advance_payload(cl_id)
        create_res = self.client.post("/advances", json=payload)
        self.assertEqual(create_res.status_code, 200)
        fv_id = create_res.get_json()["id"]

        payload["start_date"] = "2026-03-01"
        payload["end_date"] = "2026-02-28"
        update_res = self.client.put(f"/advances/{fv_id}", json=payload)
        self.assertEqual(update_res.status_code, 400)
        self.assertIn("end_date must be later than start_date", update_res.get_json()["error"])

    def test_advance_create_malformed_date_fails(self):
        cl_id = self._create_credit_line()
        payload = self._advance_payload(cl_id)
        payload["start_date"] = "bad-date"

        res = self.client.post("/advances", json=payload)
        self.assertEqual(res.status_code, 400)
        self.assertIn("must be valid ISO dates", res.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
