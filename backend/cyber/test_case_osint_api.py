import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import web_app
from case_osint_service import CaseStore


class CaseOsintApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.patch = patch.object(web_app, "CASE_STORE", CaseStore(Path(self.directory.name) / "cases.sqlite3"))
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), web_app.GeoTraceHandler)
        self.addCleanup(self.server.server_close)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.shutdown)
        self.port = self.server.server_port

    def post(self, action, body, key="", **headers):
        connection = http.client.HTTPConnection("127.0.0.1", self.port)
        self.addCleanup(connection.close)
        options = {"Content-Type": "application/json", **headers}
        if key:
            options["Authorization"] = "Bearer " + key
        connection.request("POST", "/api/osint/" + action, json.dumps(body), options)
        response = connection.getresponse()
        return response.status, json.loads(response.read())

    def test_http_case_creation_search_and_authentication(self):
        code, case = self.post("create", {"reference": "HTTP-QA", "purpose": "Synthetic records", "actor": "QA"})
        self.assertEqual(code, 200)
        query = {"case_id": case["case_id"], "kind": "name", "query": "Example", "purpose": "Fixture"}
        self.assertEqual(self.post("search", query)[0], 403)
        code, result = self.post("search", query, case["access_key"])
        self.assertEqual(code, 200)
        self.assertEqual(result["matches"], [])
        code, result = self.post("import", {
            "case_id": case["case_id"],
            "source": {
                "source_type": "public_business",
                "source_reference": "https://example.invalid/contact",
                "observed_at": "2026-10-01T10:00:00Z",
                "authorization_reference": "Public business QA fixture",
                "access_basis": "Synthetic test data",
                "authorized": True,
            },
            "records": [{"name": "Example Business", "phones": ["+12025550101"], "emails": ["contact@example.invalid"]}],
        }, case["access_key"])
        self.assertEqual(code, 200)
        self.assertEqual(result["imported"], 1)
        code, result = self.post("search", query, case["access_key"])
        self.assertEqual(result["matches"][0]["emails"], ["contact@example.invalid"])

    def test_osint_is_disabled_on_public_server_bindings(self):
        self.server.server_address = ("0.0.0.0", self.port)
        body = {"reference": "Blocked", "purpose": "Binding check", "actor": "QA"}
        self.assertEqual(self.post("create", body)[0], 403)

    def test_foreign_origins_and_hosts_cannot_create_cases(self):
        body = {"reference": "Blocked", "purpose": "CSRF test", "actor": "QA"}
        self.assertEqual(self.post("create", body, Origin="https://example.invalid")[0], 403)
        self.assertEqual(self.post("create", body, Host="example.invalid")[0], 403)
        self.assertEqual(self.post("create", body, Origin=f"http://127.0.0.1:{self.port}")[0], 200)

    def test_nonobject_json_and_unsupported_content_types_are_rejected(self):
        self.assertEqual(self.post("create", ["not an object"])[0], 400)
        self.assertEqual(self.post("create", {}, **{"Content-Type": "text/plain"})[0], 415)


if __name__ == "__main__":
    unittest.main()
