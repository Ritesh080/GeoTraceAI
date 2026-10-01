import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from case_osint_service import CaseError, CaseStore, normalize_phone


class CaseOsintTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = CaseStore(Path(self.directory.name) / "private/cases.sqlite3")
        self.owner = self.store.dispatch("create", {"reference": "QA-01", "purpose": "Synthetic test records", "actor": "Test Owner"})
        self.case = self.owner["case_id"]
        self.key = self.owner["access_key"]
        self.source = {
            "source_type": "authorized_case_record",
            "source_reference": "QA-FIXTURE-01",
            "observed_at": "2026-10-01T10:00:00+05:30",
            "authorization_reference": "QA-only records",
            "access_basis": "Synthetic fixture approved for automated checks",
            "authorized": True,
        }
        self.record = {"name": "Example Business", "entity_type": "business", "phones": ["+1 (202) 555-0101"], "emails": ["contact@example.invalid"], "payment_identifiers": ["DEMO-ONLY"]}

    def call(self, action, key=None, **values):
        return self.store.dispatch(action, {"case_id": self.case, **values}, self.key if key is None else key)

    def import_records(self, records=None, key=None, source=None):
        return self.call("import", key, source=source or self.source, records=records or [self.record])

    def test_search_phone_normalizes_and_preserves_source_claim(self):
        imported = self.import_records()
        result = self.call("search", kind="phone", query="+12025550101", purpose="Match supplied fixture")
        match = result["matches"][0]
        self.assertEqual(match["match_basis"], "exact_normalized_phone")
        self.assertEqual(match["identity_status"], "unverified_source_claim")
        self.assertEqual(match["emails"], ["contact@example.invalid"])
        self.assertEqual(match["provenance"]["collected_by"], "Test Owner")
        self.assertEqual(match["provenance"]["observed_at"], "2026-10-01T04:30:00+00:00")
        self.assertEqual(match["provenance"]["import_sha256"], imported["import_sha256"])
        self.assertEqual(len(result["warnings"]), 3)

    def test_same_name_does_not_merge_distinct_records_or_case_scopes(self):
        self.import_records([self.record, {**self.record, "phones": ["+12025550102"]}])
        result = self.call("search", kind="name", query="  EXAMPLE   Business ", purpose="Ambiguity review")
        self.assertEqual(len(result["matches"]), 2)
        other = self.store.dispatch("create", {"reference": "QA-02", "purpose": "Other case", "actor": "Other"})
        result = self.store.dispatch("search", {"case_id": other["case_id"], "kind": "name", "query": "Example", "purpose": "Isolation check"}, other["access_key"])
        self.assertEqual(result["matches"], [])
        with self.assertRaises(CaseError) as err:
            self.store.dispatch("record", {"case_id": other["case_id"], "record_id": self.call("search", kind="name", query="Example", purpose="Fixture")["matches"][0]["record_id"]}, other["access_key"])
        self.assertEqual(err.exception.status, 404)

    def test_viewers_cannot_import_or_grant_and_revocation_is_enforced(self):
        viewer = self.call("grant", actor="Test Reader", role="viewer")
        self.call("overview", viewer["access_key"])
        for action, values in [("import", {"source": self.source, "records": [self.record]}), ("grant", {"actor": "Another", "role": "editor"}), ("audit", {})]:
            with self.assertRaises(CaseError) as err:
                self.call(action, viewer["access_key"], **values)
            self.assertEqual(err.exception.status, 403)
        self.call("revoke", member_id=viewer["member_id"])
        with self.assertRaises(CaseError):
            self.call("overview", viewer["access_key"])
        denials = [event for event in self.call("audit")["events"] if event["action"] == "access_denied"]
        self.assertEqual(len(denials), 4)
        self.assertEqual(denials[-1]["actor"], "Test Reader")

    def test_editor_can_import_but_not_manage_access(self):
        editor = self.call("grant", actor="Test Editor", role="editor")
        self.import_records(key=editor["access_key"])
        result = self.call("search", kind="name", query="Example", purpose="Check collector")
        self.assertEqual(result["matches"][0]["provenance"]["collected_by"], "Test Editor")
        with self.assertRaises(CaseError):
            self.call("grant", editor["access_key"], actor="Invalid", role="viewer")

    def test_duplicate_import_and_atomic_validation(self):
        self.assertEqual(self.import_records()["imported"], 1)
        self.assertEqual(self.import_records()["duplicates_skipped"], 1)
        with self.assertRaises(CaseError):
            self.import_records([{**self.record, "name": "Should roll back"}, {"name": "Invalid", "phones": ["not a phone"]}])
        self.assertEqual(self.call("overview")["record_count"], 1)

    def test_public_import_requires_business_source_and_authorized_provenance(self):
        public = {**self.source, "source_type": "public_business", "source_reference": "https://example.invalid/contact"}
        self.assertEqual(self.import_records(source=public)["imported"], 1)
        with self.assertRaises(CaseError):
            self.import_records([{**self.record, "entity_type": "person"}], source=public)
        for field, bad in [("source_type", "leaked_records"), ("authorized", False), ("authorization_reference", ""), ("observed_at", "2026-10-01T10:00:00")]:
            with self.assertRaises(CaseError):
                self.import_records(source={**self.source, field: bad})

    def test_audit_tracks_searches_and_detects_edited_events_without_keys(self):
        self.import_records()
        self.call("search", kind="name", query="Example", purpose="Review fixture")
        audit = self.call("audit")
        self.assertTrue(audit["chain_valid"])
        self.assertIn("records_searched", [event["action"] for event in audit["events"]])
        self.assertNotIn(self.key, json.dumps(audit))
        with closing(sqlite3.connect(self.store.path)) as db:
            self.assertNotIn(self.key, str(db.execute("SELECT * FROM members").fetchall()))
            db.execute("UPDATE audit SET event='{}' WHERE sequence=(SELECT MIN(sequence) FROM audit)")
            db.commit()
        self.assertFalse(self.call("audit")["chain_valid"])
        self.assertEqual(os.stat(self.store.path).st_mode & 0o777, 0o600)

    def test_name_search_escapes_sql_wildcards_and_requires_purpose(self):
        self.import_records()
        self.assertEqual(self.call("search", kind="name", query="%%%", purpose="Literal match")["matches"], [])
        with self.assertRaises(CaseError):
            self.call("search", kind="name", query="Example", purpose="")

    def test_indian_and_international_numbers_have_explicit_normalization(self):
        self.assertEqual(normalize_phone("9000000001"), "+919000000001")
        self.assertEqual(normalize_phone("0091 9000000001"), "+919000000001")
        self.assertEqual(normalize_phone("+1-202-555-0101"), "+12025550101")
        with self.assertRaises(CaseError):
            normalize_phone("12025550101")


if __name__ == "__main__":
    unittest.main()
