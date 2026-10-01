"""Case-scoped search of sourced business contacts and authorized case records.

No remote requests. Capability keys authorize individual case roles; only key
digests are stored. SQLite transactions make imports and audit events atomic.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


DEFAULT_DATABASE = Path(__file__).resolve().parents[2] / "data/osint/cases.sqlite3"
MAX_RECORDS = 1000
ROLES = {"viewer": 1, "editor": 2, "owner": 3}
RECORD_FIELDS = {"name", "entity_type", "phones", "emails", "payment_identifiers", "notes"}


class CaseError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value, label: str, maximum: int = 500, required: bool = True) -> str:
    if not isinstance(value, str):
        raise CaseError(f"{label} must be text")
    value = value.strip()
    if (required and not value) or len(value) > maximum:
        raise CaseError(f"{label} must contain 1–{maximum} characters" if required else f"{label} exceeds {maximum} characters")
    return value


def normalize_name(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def normalize_phone(value: str) -> str:
    value = _text(value, "Phone", 40)
    if not re.fullmatch(r"[+\d\s().-]+", value, re.ASCII):
        raise CaseError("Phone must contain digits, an optional country prefix and separators")
    digits = re.sub(r"\D", "", value)
    if value.startswith("+"):
        if value.count("+") != 1:
            raise CaseError("Phone has an invalid country prefix")
    elif value.startswith("00"):
        digits = digits[2:]
    elif "+" in value:
        raise CaseError("The phone country prefix must be at the start")
    elif len(digits) == 10:
        digits = "91" + digits
    elif not (len(digits) == 12 and digits.startswith("91")):
        raise CaseError("Use +country-code for international numbers; bare 10-digit numbers assume India")
    if not 8 <= len(digits) <= 15 or digits.startswith("0"):
        raise CaseError("Phone length or country prefix is invalid")
    return "+" + digits


def _list(raw: dict, field: str, maximum: int = 10) -> list[str]:
    values = raw.get(field, [])
    if not isinstance(values, list) or len(values) > maximum:
        raise CaseError(f"{field} must be a list with at most {maximum} values")
    return list(dict.fromkeys(_text(value, field, 254) for value in values))


def _record(raw, source_type: str) -> dict:
    if not isinstance(raw, dict) or set(raw) - RECORD_FIELDS:
        raise CaseError("Record fields must be name, entity_type, phones, emails, payment_identifiers, notes")
    entity_type = raw.get("entity_type", "business" if source_type == "public_business" else "person")
    if not isinstance(entity_type, str) or entity_type not in {"person", "business"}:
        raise CaseError("entity_type must be person or business")
    if source_type == "public_business" and entity_type != "business":
        raise CaseError("Public-source imports are limited to published business contacts")
    name = _text(raw.get("name", ""), "Record name", 200, False)
    phones = _list(raw, "phones")
    normalized_phones = list(dict.fromkeys(normalize_phone(phone) for phone in phones))
    if not name and not phones:
        raise CaseError("Every record needs a name or phone number")
    emails = _list(raw, "emails")
    if any(not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) for email in emails):
        raise CaseError("Email identifiers must use an email address format")
    return {
        "name": name,
        "entity_type": entity_type,
        "phones": phones,
        "normalized_phones": normalized_phones,
        "emails": emails,
        "payment_identifiers": _list(raw, "payment_identifiers"),
        "notes": _text(raw.get("notes", ""), "Record notes", 2000, False),
    }


def _source(raw) -> dict:
    if not isinstance(raw, dict):
        raise CaseError("Source must be an object")
    kind = raw.get("source_type")
    if not isinstance(kind, str) or kind not in {"public_business", "authorized_case_record"}:
        raise CaseError("Source type must be public_business or authorized_case_record")
    reference = _text(raw.get("source_reference", ""), "Source reference", 2048)
    if kind == "public_business":
        parsed = urlparse(reference)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise CaseError("Public business sources need a HTTP(S) URL without credentials")
    observed_at = _text(raw.get("observed_at", ""), "Observation timestamp", 80)
    try:
        date = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        if date.tzinfo is None:
            raise ValueError()
        observed_at = date.astimezone(timezone.utc).isoformat()
    except ValueError as exc:
        raise CaseError("Observation timestamp must be ISO 8601 with timezone") from exc
    if raw.get("authorized") is not True:
        raise CaseError("Confirm that these records are authorized for this case")
    return {
        "source_type": kind,
        "source_reference": reference,
        "observed_at": observed_at,
        "authorization_reference": _text(raw.get("authorization_reference", ""), "Authorization reference", 500),
        "access_basis": _text(raw.get("access_basis", ""), "Access basis", 1000),
    }


class CaseStore:
    def __init__(self, database: str | Path = DEFAULT_DATABASE):
        self.path = Path(database)

    @contextmanager
    def _connection(self):
        if self.path.is_symlink() or self.path.parent.is_symlink():
            raise CaseError("Case storage cannot be a symbolic link", 500)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.path.parent, 0o700)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        os.chmod(self.path, 0o600)
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS cases (
                    id TEXT PRIMARY KEY, reference TEXT NOT NULL, purpose TEXT NOT NULL,
                    created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS members (
                    id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id),
                    actor TEXT NOT NULL, role TEXT NOT NULL, key_hash TEXT UNIQUE NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS records (
                    id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id),
                    name_norm TEXT NOT NULL, payload TEXT NOT NULL, provenance TEXT NOT NULL,
                    fingerprint TEXT NOT NULL, imported_at TEXT NOT NULL,
                    UNIQUE(case_id, fingerprint));
                CREATE INDEX IF NOT EXISTS records_by_case ON records(case_id);
                CREATE TABLE IF NOT EXISTS phones (
                    record_id TEXT NOT NULL REFERENCES records(id), phone TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS phones_by_number ON phones(phone);
                CREATE TABLE IF NOT EXISTS audit (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_id TEXT NOT NULL REFERENCES cases(id), event TEXT NOT NULL,
                    previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL);
            """)
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _audit(self, db, case_id: str, actor: str, action: str, details: dict):
        row = db.execute("SELECT event_hash FROM audit WHERE case_id=? ORDER BY sequence DESC LIMIT 1", (case_id,)).fetchone()
        previous = row["event_hash"] if row else "0" * 64
        event = _json({"case_id": case_id, "actor": actor, "action": action, "timestamp": _now(), "details": details})
        db.execute("INSERT INTO audit(case_id,event,previous_hash,event_hash) VALUES(?,?,?,?)", (case_id, event, previous, _digest(previous + event)))

    def _member(self, db, case_id: str, key: str, role: str = "viewer"):
        if not isinstance(key, str) or len(key) < 20 or len(key) > 200:
            raise CaseError("Valid case access key required", 403)
        row = db.execute("SELECT * FROM members WHERE case_id=? AND key_hash=? AND active=1", (case_id, _digest(key))).fetchone()
        if row is None:
            raise CaseError("Case access denied", 403)
        if ROLES[row["role"]] < ROLES[role]:
            raise CaseError(f"This operation requires {role} case access", 403)
        return row

    def _new_member(self, db, case_id: str, actor: str, role: str) -> dict:
        key = secrets.token_urlsafe(32)
        member_id = uuid.uuid4().hex
        db.execute("INSERT INTO members(id,case_id,actor,role,key_hash) VALUES(?,?,?,?,?)", (member_id, case_id, actor, role, _digest(key)))
        return {"member_id": member_id, "actor": actor, "role": role, "access_key": key}

    def dispatch(self, action: str, payload: dict, key: str = "") -> dict:
        try:
            return self._dispatch(action, payload, key)
        except CaseError as exc:
            # Authorization failures are recorded independently of the failed
            # operation's rolled-back transaction. Never retain the access key.
            if exc.status == 403 and isinstance(payload, dict):
                case_id = payload.get("case_id")
                if isinstance(case_id, str) and len(case_id) <= 64:
                    with self._connection() as db:
                        if db.execute("SELECT 1 FROM cases WHERE id=?", (case_id,)).fetchone():
                            known = db.execute("SELECT actor FROM members WHERE case_id=? AND key_hash=?", (case_id, _digest(key))).fetchone() if isinstance(key, str) else None
                            self._audit(db, case_id, known["actor"] if known else "unknown", "access_denied", {"requested_action": action})
            raise

    def _dispatch(self, action: str, payload: dict, key: str = "") -> dict:
        if not isinstance(payload, dict):
            raise CaseError("Request must be a JSON object")
        if action == "create":
            reference = _text(payload.get("reference", ""), "Case reference", 120)
            purpose = _text(payload.get("purpose", ""), "Case purpose", 1000)
            actor = _text(payload.get("actor", ""), "Owner name", 120)
            with self._connection() as db:
                case_id = uuid.uuid4().hex
                db.execute("INSERT INTO cases VALUES(?,?,?,?)", (case_id, reference, purpose, _now()))
                member = self._new_member(db, case_id, actor, "owner")
                self._audit(db, case_id, actor, "case_created", {"member_id": member["member_id"]})
                return {"case_id": case_id, "reference": reference, **member}

        required = {"overview": "viewer", "search": "viewer", "record": "viewer", "import": "editor", "grant": "owner", "revoke": "owner", "audit": "owner"}
        if action not in required:
            raise CaseError("Unknown OSINT action", 404)
        case_id = _text(payload.get("case_id", ""), "Case ID", 64)
        with self._connection() as db:
            member = self._member(db, case_id, key, required[action])
            actor = member["actor"]
            if action == "overview":
                case = dict(db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone())
                case["role"] = member["role"]
                case["actor"] = actor
                case["record_count"] = db.execute("SELECT COUNT(*) FROM records WHERE case_id=?", (case_id,)).fetchone()[0]
                if member["role"] == "owner":
                    case["members"] = [dict(row) for row in db.execute("SELECT id,actor,role,active FROM members WHERE case_id=?", (case_id,))]
                self._audit(db, case_id, actor, "case_opened", {})
                return case
            if action == "grant":
                role = payload.get("role")
                if not isinstance(role, str) or role not in {"viewer", "editor"}:
                    raise CaseError("Grant role must be viewer or editor")
                new_member = self._new_member(db, case_id, _text(payload.get("actor", ""), "Member name", 120), role)
                self._audit(db, case_id, actor, "access_granted", {"member_id": new_member["member_id"], "actor": new_member["actor"], "role": role})
                return new_member
            if action == "revoke":
                member_id = _text(payload.get("member_id", ""), "Member ID", 64)
                target = db.execute("SELECT role FROM members WHERE id=? AND case_id=? AND active=1", (member_id, case_id)).fetchone()
                if target is None or target["role"] == "owner":
                    raise CaseError("Select an active non-owner member to revoke")
                db.execute("UPDATE members SET active=0 WHERE id=?", (member_id,))
                self._audit(db, case_id, actor, "access_revoked", {"member_id": member_id})
                return {"revoked": member_id}
            if action == "import":
                return self._import(db, case_id, actor, payload)
            if action == "search":
                return self._search(db, case_id, actor, payload)
            if action == "record":
                record_id = _text(payload.get("record_id", ""), "Record ID", 64)
                row = db.execute("SELECT * FROM records WHERE id=? AND case_id=?", (record_id, case_id)).fetchone()
                if row is None:
                    raise CaseError("Record not found in this case", 404)
                self._audit(db, case_id, actor, "record_viewed", {"record_id": record_id})
                return self._view(row)
            self._audit(db, case_id, actor, "audit_viewed", {})
            rows = db.execute("SELECT * FROM audit WHERE case_id=? ORDER BY sequence", (case_id,)).fetchall()
            expected = "0" * 64
            valid = True
            events = []
            for row in rows:
                valid = valid and hmac.compare_digest(expected, row["previous_hash"]) and hmac.compare_digest(_digest(row["previous_hash"] + row["event"]), row["event_hash"])
                expected = row["event_hash"]
                events.append({"sequence": row["sequence"], **json.loads(row["event"]), "event_hash": row["event_hash"], "previous_hash": row["previous_hash"]})
            return {"events": events, "chain_valid": valid, "note": "The hash chain detects edits; it is not independently anchored and is not tamper-proof against a database administrator."}

    def _import(self, db, case_id: str, actor: str, payload: dict) -> dict:
        source = _source(payload.get("source"))
        raw_records = payload.get("records")
        if not isinstance(raw_records, list) or not 1 <= len(raw_records) <= MAX_RECORDS:
            raise CaseError(f"Import must contain 1–{MAX_RECORDS} records")
        records = [_record(raw, source["source_type"]) for raw in raw_records]
        imported_at = _now()
        batch_hash = _digest(_json({"source": payload["source"], "records": raw_records}))
        provenance = {**source, "collected_by": actor, "imported_at": imported_at, "import_sha256": batch_hash}
        count = 0
        for record in records:
            fingerprint = _digest(_json({"source": source, "record": record}))
            record_id = uuid.uuid4().hex
            inserted = db.execute("INSERT OR IGNORE INTO records VALUES(?,?,?,?,?,?,?)", (record_id, case_id, normalize_name(record["name"]), _json(record), _json(provenance), fingerprint, imported_at))
            if inserted.rowcount:
                count += 1
                db.executemany("INSERT INTO phones VALUES(?,?)", [(record_id, number) for number in record["normalized_phones"]])
        self._audit(db, case_id, actor, "evidence_imported", {"import_sha256": batch_hash, "imported": count, "duplicates_skipped": len(records) - count, "source_type": source["source_type"]})
        return {"imported": count, "duplicates_skipped": len(records) - count, "import_sha256": batch_hash}

    def _view(self, row) -> dict:
        return {"record_id": row["id"], "case_id": row["case_id"], **json.loads(row["payload"]), "provenance": json.loads(row["provenance"]), "identity_status": "unverified_source_claim"}

    def _search(self, db, case_id: str, actor: str, payload: dict) -> dict:
        kind = payload.get("kind")
        query = _text(payload.get("query", ""), "Search query", 200)
        purpose = _text(payload.get("purpose", ""), "Search purpose", 500)
        if kind == "phone":
            normalized = normalize_phone(query)
            rows = db.execute("SELECT DISTINCT r.* FROM records r JOIN phones p ON p.record_id=r.id WHERE r.case_id=? AND p.phone=? ORDER BY r.imported_at DESC LIMIT 101", (case_id, normalized)).fetchall()
        elif kind == "name":
            normalized = normalize_name(query)
            if len(normalized) < 3:
                raise CaseError("Name searches need at least 3 characters")
            escaped = normalized.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            rows = db.execute("SELECT * FROM records WHERE case_id=? AND name_norm LIKE ? ESCAPE '\\' ORDER BY (name_norm=?) DESC, imported_at DESC LIMIT 101", (case_id, "%" + escaped + "%", normalized)).fetchall()
        else:
            raise CaseError("Search kind must be name or phone")
        results = []
        for row in rows[:100]:
            item = self._view(row)
            item["match_basis"] = "exact_normalized_phone" if kind == "phone" else "exact_normalized_name" if row["name_norm"] == normalized else "partial_name"
            results.append(item)
        self._audit(db, case_id, actor, "records_searched", {"query_sha256": _digest(_json({"kind": kind, "query": normalized})), "kind": kind, "purpose": purpose, "returned": len(results), "record_ids": [item["record_id"] for item in results], "truncated": len(rows) > 100})
        return {
            "matches": results,
            "truncated": len(rows) > 100,
            "searched_scope": "Authorized records imported into this case only",
            "warnings": [
                "Matches are source claims, not confirmed identities. Names can be shared; phone numbers can be reused or shared.",
                "Listed emails and payment identifiers are copied from the cited source. They are not inferred, validated with a bank, or confirmed as belonging to the searched person.",
                "Bare 10-digit phone numbers assume India (+91); supply +country-code for other countries.",
            ],
        }
