import os
import tempfile
import threading
import unittest

import db


class AtomicIdGenerationTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "test.db")
        self.orig_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
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

    def tearDown(self):
        db.DB_PATH = self.orig_db_path
        self.tmpdir.cleanup()

    def _create_credit_line(self, idx=1):
        conn = db.get_db()
        try:
            return db.create_credit_line(
                conn,
                {
                    "bank_key": "B001",
                    "description": f"Facility {idx}",
                    "currency": "CHF",
                    "amount": 100_000_000 + idx,
                    "committed": "Yes",
                    "start_date": "2026-01-01",
                    "end_date": None,
                    "note": None,
                },
            )
        finally:
            conn.close()

    def test_credit_line_id_boundary_format(self):
        conn = db.get_db()
        try:
            conn.execute(
                "UPDATE id_sequences SET last_value = ? WHERE name = 'credit_lines'",
                (9,),
            )
            conn.commit()
        finally:
            conn.close()

        cl_id = self._create_credit_line(10)
        self.assertEqual(cl_id, "CL010")

    def test_advance_id_boundary_format(self):
        cl_id = self._create_credit_line(1)
        conn = db.get_db()
        try:
            conn.execute(
                "UPDATE id_sequences SET last_value = ? WHERE name = 'fixed_advances'",
                (999,),
            )
            conn.commit()
            fv_id = db.create_advance(
                conn,
                {
                    "bank": "Bank 1",
                    "credit_line_id": cl_id,
                    "start_date": "2026-01-10",
                    "end_date": "2026-02-10",
                    "continuation_date": "2026-02-05",
                    "currency": "CHF",
                    "amount_original": 10_000_000,
                    "interest_amount": 10_000.0,
                },
            )
        finally:
            conn.close()

        self.assertEqual(fv_id, "FV1000")

    def test_parallel_credit_line_creates_are_unique(self):
        worker_count = 8
        barrier = threading.Barrier(worker_count)
        ids = []
        errors = []
        lock = threading.Lock()

        def worker(i):
            try:
                barrier.wait(timeout=5)
                cl_id = self._create_credit_line(i)
                with lock:
                    ids.append(cl_id)
            except Exception as exc:
                with lock:
                    errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(worker_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        self.assertFalse(errors, f"Unexpected worker errors: {errors}")
        self.assertEqual(len(ids), worker_count)
        self.assertEqual(len(set(ids)), worker_count)

    def test_parallel_advance_creates_are_unique(self):
        worker_count = 8
        barrier = threading.Barrier(worker_count)
        ids = []
        errors = []
        lock = threading.Lock()
        cl_id = self._create_credit_line(1)

        def worker(i):
            try:
                barrier.wait(timeout=5)
                conn = db.get_db()
                try:
                    fv_id = db.create_advance(
                        conn,
                        {
                            "bank": "Bank 1",
                            "credit_line_id": cl_id,
                            "start_date": "2026-01-10",
                            "end_date": "2026-02-10",
                            "continuation_date": "2026-02-05",
                            "currency": "CHF",
                            "amount_original": 1_000_000 + i,
                            "interest_amount": 1_000.0 + i,
                        },
                    )
                finally:
                    conn.close()
                with lock:
                    ids.append(fv_id)
            except Exception as exc:
                with lock:
                    errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(worker_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        self.assertFalse(errors, f"Unexpected worker errors: {errors}")
        self.assertEqual(len(ids), worker_count)
        self.assertEqual(len(set(ids)), worker_count)


if __name__ == "__main__":
    unittest.main()
