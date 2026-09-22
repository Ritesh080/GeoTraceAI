# GeoTrace AI — saved project checkpoint

Saved September 16, 2026 at the user's request. Work is paused; preserve the current website and resume with future feature/change requests. The user has not yet approved proceeding to section 2. Do not rebuild from scratch.

Later on September 16, the user requested a research pipeline for contradiction detection, source-dependency handling, and calibrated uncertainty. It is saved separately at `../geotrace-research/`, with its own README, runnable Python code, synthetic experiment, and tests. The website remains unchanged; backend/frontend integration is future work.

On September 17, the user requested connecting the frontend to the GitHub backend. The site now contains a snapshot of `Ritesh080/GeoTraceAI` backend commit `9ab9438a824bb67dbce805020483f5e6d6e2cf7f`, a FastAPI bridge at `backend/api.py`, and a live upload/analyzer component at `components/live-analyzer.tsx`. The API caps uploads at 20 MB, validates formats, runs the existing pipeline, omits raw ExifTool output from the public response, and deletes temporary files. The frontend checks `/health`, posts images to `/analyze`, and renders the returned forensic result. End-to-end testing with the repository sample image returned SHA-256 `988db07c...40e17f`, dimensions 1150×1310, and reliability 59/100. Build and typecheck passed. The local frontend and backend were left running for review. The frontend has not been published because GitHub does not execute the Python service and no hosted Python API origin has been supplied.

On September 19, the OSINT handoff was connected to the analyzer. `backend/osint_stage.py` converts the file hash and normalized metadata into privacy-preserving manual verification actions for exact-hash search, reverse-image providers, and map checks when valid GPS exists. All clues derived from the submitted image remain in one dependency group. The response contains conflict and uncertainty fields and abstains with `insufficient_evidence` until independent sources are collected. The frontend renders these actions, the dependency explanation, and the abstention decision. No image is automatically sent to an external OSINT provider.

The public static site also has an in-browser fallback for uploads when no API URL is configured. It computes SHA-256, file type, extension, dimensions, and OSINT verification links with Web Crypto and browser image decoding. The image stays on the device. The UI shows the forensic reliability score as unavailable because EXIF and forensic scoring still require the Python service.

The browser pipeline was then extended with `exifr` and `tesseract.js`. It now checks EXIF/GPS, recognizes English text, labels the dominant writing system, adds coordinate-map or OCR-search actions, and creates a location candidate when valid embedded GPS exists. The decision remains `candidate_needs_corroboration` for a lone GPS source and `insufficient_evidence` without one. Landmark recognition remains a provider adapter because client code cannot safely contain service credentials.

## Location and reference

- Project: `/Users/riteshbhardwaj/Documents/Codex/2026-09-16/de/outputs/geotrace-ai`
- Product reference: https://github.com/Ritesh080/GeoTraceAI
- Architecture reference: https://github.com/Ritesh080/GeoTraceAI/blob/main/CYBER_PIPELINE.md
- Original brief is preserved as `DESIGN_BRIEF.txt` in this project.
- Local preview used http://127.0.0.1:3000/. This is a local server, not a permanent hosted URL. No deployment or changes to the reference repository were made.

## Completed

Only section 1: responsive hero, navigation to the reference repository, and an interactive product concept with location hypothesis, forensic signals, and report preview tabs. Headline: “Trace what images don’t say.” CTA focuses and scrolls to the workspace. Tabs support arrow keys, Home, and End. Reduced-motion support and a skip link are included.

Visual direction: dark enterprise forensics aesthetic; asymmetric editorial layout; navy #0F172A, surface #1E293B, restrained blue accents; locally bundled Inter variable font. Centralized design tokens in `app/globals.css`. Main page in `app/page.tsx`; shared Radix/shadcn-style Button in `components/ui/button.tsx`.

Stack: Next.js 15 App Router, TypeScript, Tailwind 4, Framer Motion, Lucide React. Axios and React Dropzone installed for future demo work. Static export configured. No actual uploads, backend analysis, or data submission implemented.

The map is an abstract evidence-convergence diagram, not a real geographic map. New Delhi is explicitly an illustrative candidate. All results are concept data. Preserve the distinction between forensic reliability and geolocation confidence. Reference docs listed evidence integration, conflict detection, and final reports as upcoming, as of this checkpoint.

## Validation at checkpoint

Production build and TypeScript check passed. Browser verified tab clicks, keyboard navigation, CTA navigation, and mobile layout at 390px with no horizontal overflow. Do not imply a full accessibility audit or Lighthouse test was performed.

## Remaining scope and user preferences

The original brief requires section-by-section implementation, a preview and short explanation after each major section, and user confirmation before moving to the next. User has now paused development for future work.

Remaining sections: problem framing; interactive pipeline (Upload → Cyber Analysis → AI Analysis/RAG → Evidence Fusion → Final Investigation Report); simulated upload demo; capabilities; forensic rigor/architecture; final CTA/footer. The repository describes AI and cyber analysis as parallel branches feeding fusion, which the pipeline visualization should reflect.

Avoid generic gradients, repeated feature-card grids, emoji icons, unsupported accuracy claims, and gratuitous animation. Preserve responsive restructuring and reduced-motion behavior.

## Resume

Read this checkpoint and the original brief, inspect current source, then apply the user's next request. `npm run build` exports to `out/`. For a static preview run `python3 -m http.server 3000 --bind 127.0.0.1 --directory out` from this project, if no existing server is running. `npm run dev` is also available. Do not run build and development servers concurrently against the same `.next` directory. The previous environment required a writable npm cache at `/private/tmp/geotrace-npm-cache` and `curl --noproxy '*'` for local readiness checks.
