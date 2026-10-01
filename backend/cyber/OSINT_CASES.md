# GeoTrace OSINT cases

Start the existing local web server and open `http://127.0.0.1:8787/osint`.
The image-analysis homepage links to **OSINT case workspace**.

## Workflow

1. Create a case with its reference, purpose, and investigator name. Save the
   generated case ID and owner key securely. Keys are displayed once; the
   server stores only SHA-256 key digests. Refreshing or locking the page clears
   the browser's in-memory key. Reopen a case with the saved ID/key.
2. Import CSV or JSON records under **Import evidence**. Supply the source URL
   or internal reference, observation time, authorization reference, access
   basis, and authorization confirmation. Select the correct source category.
3. Search by name or phone, recording the reason for the query. Read each
   record's provenance before linking it to a person. Partial names are marked
   separately from exact normalized names. Phone matches are exact after
   normalization. Bare 10-digit numbers assume India (+91); use +country-code
   for international numbers.
4. Owners can issue named viewer/editor keys, revoke those keys, and read or
   download the audit JSON. Viewers can search and read; editors can also import.

No external database or search engine is connected by default. Searches cover
only the selected case's imported records. Public business contacts must be
entered from a cited public page or an authorized export. This module makes no
network calls and does not collect leaked datasets, look up account holders,
or verify payment identifiers with payment providers.

## Evidence files

Limits: 4 MB per API request (including provenance), 1–1,000 records per import,
and at most 10 values in each identifier list. Imports validate every row before
writing. Reimporting identical records with identical source details skips
duplicates without overwriting previous evidence. Changed observations remain
separate records. A failed row rolls back the entire batch.

CSV headers:

```csv
name,entity_type,phones,emails,payment_identifiers,notes
```

Separate multiple identifier values with semicolons. Quote fields containing
commas or newlines. Download an empty CSV template from the import form.

JSON accepts an array of records, for example this **synthetic** business:

```json
[
  {
    "name": "Example Business",
    "entity_type": "business",
    "phones": ["+12025550101"],
    "emails": ["contact@example.invalid"],
    "payment_identifiers": ["DEMO-ONLY"],
    "notes": "Synthetic formatting example; not investigative evidence"
  }
]
```

Source categories:

- `public_business`: only business records, with a HTTP(S) source URL.
- `authorized_case_record`: person or business records with a source reference
  and documented authorization. Authorization is an operator declaration; it
  does not establish legal authority by itself.

Identifiers are preserved as source claims. Shared names, recycled/shared
phones, stale sources and transcription errors can produce misleading matches.
No identity is automatically confirmed or merged. Results are capped at 100;
the UI flags truncation and asks for a narrower query.

Each record includes its source category/reference, observation time,
authorization reference, access basis, importing key's named member, import
time, and SHA-256 of the submitted JSON evidence envelope. This hash represents
the normalized submitted envelope, not the original CSV file bytes.

## Access and storage

The API is enabled only on a loopback binding. It rejects foreign `Host` and
browser `Origin` headers. Case keys must be supplied as `Authorization: Bearer`
headers, never URL parameters. All actions enforce the role on the server;
changing UI controls or sending a role field cannot grant permissions.

The SQLite store lives at `data/osint/cases.sqlite3`. The directory is mode
700, the database is mode 600, and case storage is excluded from Git. No real
records or case keys are included in source code. Local filesystem permissions
protect access; the database contents are not encrypted by this module.

The local prototype uses possession of a named case key, not verified
institutional identity. Anyone with local access can create an empty case;
opening an existing case requires its key. Owners cannot recover lost keys.
Use institutional authentication, encrypted storage, managed backups and an
externally anchored audit service before multi-user government deployment.

Audit events cover case creation/opening, imports, searches (query digest,
purpose, returned record IDs), record reads, permission grants/revocations,
denied case access, and audit reads. Unknown-origin requests are rejected
before case processing. Per-case hash chaining detects inconsistent event
edits, but cannot prevent a database administrator from rewriting a complete
chain or truncating its end. It is not a certified tamper-proof ledger.

## Local API

`POST /api/osint/{action}` takes JSON. Creation needs `reference`, `purpose`,
and `actor`. All other actions need `case_id` and a bearer key:

| Action | Minimum role | Other fields |
|---|---|---|
| `overview` | Viewer | None |
| `search` | Viewer | `kind` (`name`/`phone`), `query`, `purpose` |
| `record` | Viewer | `record_id` |
| `import` | Editor | `source`, `records` |
| `grant` | Owner | `actor`, `role` (`viewer`/`editor`) |
| `revoke` | Owner | `member_id` |
| `audit` | Owner | None |

The FastAPI/hosted website remains a separate existing interface; this case
module is served by the local `backend/cyber/web_app.py` only.

## Verification

```sh
.venv/bin/python -m unittest discover -s backend/cyber -p 'test_case_osint*.py'
node --test tests/test_osint_csv.cjs
```

Checks cover cross-case isolation, role enforcement, revoked keys, denied
access auditing, source restrictions, atomic invalid imports, duplicate imports,
name ambiguity, phone normalization, audit edit detection, local-origin checks,
public-binding rejection, and quoted/malformed CSV imports. Tests use only
synthetic fixtures in temporary databases.
