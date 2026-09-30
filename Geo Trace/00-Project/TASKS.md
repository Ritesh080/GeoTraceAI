# Tasks

| ID | Task | Status | Owner |
|---|---|---|---|
| WS-01 | Preserve existing vault and add shared project context | Done | Workspace setup |
| WS-02 | Configure Agent Client paths for Claude, Codex, and Gemini | In progress | Workspace setup |
| WS-03 | Verify authenticated agents read the shared context | In progress | Workspace setup |
| P-01 | Review developer handbook and confirm requirements | Proposed | Unassigned |
| P-02 | Reproduce current image-analysis pipeline | Proposed | Unassigned |
| P-03 | Agree on tests and acceptance criteria | Proposed | Unassigned |
| P-04 | Integrate EXIF, GeoCLIP, Oceanir, and GeoSpy/Graylark behind one evidence-preserving consensus pipeline | Done | Codex |
| P-05 | Add and run a local web interface for the GeoTrace analysis pipeline | Done | Codex |
| P-06 | Replace vendor-facing web controls with local visual clues and social-media evidence intake | Done | Codex |
| P-07 | Add automatic collection of public social-media preview images without platform APIs | Done | Codex |
| P-08 | Add multimodal Instagram evidence fusion with a local India place-name index | Done | Codex |
| P-09 | Allow text-only social-media evidence when no image is available | Done | Codex |
| P-10 | Integrate, validate, commit, and push the local social-evidence work to GitHub | Done | Codex |
| P-11 | Reject generic Instagram previews and abstain from uncorroborated social locations | Done | Codex |

P-04 affected files: `backend/cyber/main.py`, `remote_geolocation.py`,
`consensus_service.py`, related tests and README, plus the shared architecture,
decisions, context, and handoff notes.

P-05 affected files: `backend/cyber/web_app.py`, `backend/cyber/web/index.html`,
the cyber README, and the shared architecture, tasks, and handoff notes.

P-06 affected files: `backend/cyber/main.py`, `local_clue_service.py`,
`vision_ocr.swift`, related tests, `web_app.py`, `web/index.html`, the cyber
README, and shared architecture, decisions, tasks, and handoff notes.

P-07 affected files: `backend/cyber/social_collection_service.py`, related
tests, `web_app.py`, `web/index.html`, the cyber README, and shared architecture,
decisions, tasks, and handoff notes.

P-08 affected files: `backend/cyber/build_india_gazetteer.py`,
`text_location_service.py`, `main.py`, `web_app.py`, `web/index.html`, related
tests and documentation, the local generated GeoNames index, and shared
research, architecture, tasks, and handoff notes.

Before editing, claim a task and list the affected files. On completion, record validation and the next handoff. Do not have multiple agents edit the same file concurrently.
