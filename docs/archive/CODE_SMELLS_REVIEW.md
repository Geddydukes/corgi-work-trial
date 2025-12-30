# Codebase Code Smell Review (best-effort)

This review highlights notable design and maintainability issues observed across the repository. It is not an exhaustive line-by-line audit but focuses on concrete problems encountered during inspection and test runs.

## Frontend (Next.js)
- `frontend/app/components/BatchProcessor.tsx`: Heavy console logging and multiple fetches per tracking number run on the client; no debounce on input parsing and no cancellation of in-flight `fetch` when unmounting. **Recommendation:** Gate debug logging to dev, debounce input parsing, and use abort controllers/cleanup to avoid leaks and duplicate requests.
- `frontend/app/components/BatchProcessor.tsx`: Hardcoded Google Drive folder ID (`DEFAULT_DRIVE_FOLDER_ID`) and API URLs concatenated inline. **Recommendation:** Move to env-config with validation; surface missing config to the user instead of silently failing.
- `frontend/app/components/DecisionViewer.tsx`, `DecisionSummary.tsx`, `LineItemsList.tsx`: Minimal loading/error states; large payloads render synchronously without virtualization. **Recommendation:** Add skeleton/loading guards and consider windowing for long line-item lists to avoid main-thread jank.
- `frontend/app/components/VarianceTracker.tsx`: No error handling around API usage; assumes data shape. **Recommendation:** Add defensive parsing and surface user-facing errors; cache/stale-while-revalidate if data is reused.
- `frontend/app/layout.tsx` / `globals.css`: No CSS containment or font loading strategy defined; could block rendering. **Recommendation:** Preload fonts or rely on system stack to reduce layout shift; scope global styles to avoid bleed-through.

## Decision Service (backend)
- `decision_service/engine/document_analyzer.py`: Imports `google.generativeai` at module import time. Without the dependency, any import of `DecisionEngine` explodes before tests can stub the network. **Recommendation:** Lazy-load SDK inside call sites with try/except; provide a test-mode stub and configuration flag to bypass network.
- `decision_service/engine/decision_engine.py`: Per-claim async lock is in-memory only; will not prevent concurrent workers from double-processing. **Recommendation:** Use DB/Redis advisory locks or a claim-level mutex persisted externally.
- `decision_service/engine/rule_evaluator.py`: Sanity cap now clamps invoice_total relative to claim_amount; tests/spec expect uncapped totals. **Recommendation:** Make the multiplier environment-driven and allow disabling in test/dev; document policy and update tests accordingly.
- `decision_service/engine/reconciliation.py`: References `all_items` (undefined), causing NameError and forcing parser fallbacks. **Recommendation:** Replace with a composed list of `line_items + credits + taxes + fees`, add unit tests for negative amounts.
- `decision_service/engine/invoice_parser_advanced.py`: Industry/edge-case parsing is fragile; numerous keyword assertions fail when reconciliation falls back. **Recommendation:** Strengthen phrase detection (cleaning/utility/maintenance/code keywords), avoid swallowing exceptions, and add regression tests per failing fixtures.
- `decision_service/engine/deterministic_rules.py`: No guard for missing/invalid amounts before Decimal conversion; malformed input throws. **Recommendation:** Validate/normalize amounts before categorization.
- `decision_service/services/batch_service.py`: Retries added but backoff and error aggregation are in-memory; persistent tracking is absent. **Recommendation:** Record retries/failures in storage and expose metrics to avoid silent drops.

## Document Service (backend)
- `document_service/ocr/service.py`: Only `pdfplumber` import is guarded; `PyPDF2`, Tesseract, and other OCR deps are assumed present. **Recommendation:** Guard all optional deps, log once, and skip unavailable tiers to keep service up.
- `document_service/processor.py`: No dependency checks for Pillow/reportlab, and no short-circuit when OCR tiers unavailable; risk of long error chains. **Recommendation:** Add startup validation and fast-fail with actionable errors; provide a minimal mock in test mode.
- `document_service/processor.py`: Caches dedup results but silently disables cache on a single Redis hiccup. **Recommendation:** Add limited retries and a timed cool-off before permanently disabling caching.

## Shared/Infrastructure/Performance
- `shared/deduplication.py`: Imports `redis` unguarded; missing dependency crashes import. Also disables caching permanently after one failure. **Recommendation:** Guard the import, add an in-memory fallback for tests, and re-enable caching after a cooldown.
- `shared/config.py`: Loads `.env` at import and exposes many env-based toggles but lacks a “test/offline” mode to stub external services. **Recommendation:** Add a `TEST_MODE`/`OFFLINE_MODE` flag to bypass networked providers and tighten validation of required vs optional settings.
- `tests/performance_benchmark.py` and `tests/test_performance.py`: Marked slow but no isolation; risk of running heavy benchmarks unintentionally. **Recommendation:** Gate with explicit markers and CI filters; ensure benchmarks mock external services.

## Archived Scripts and Tests
- `scripts/archive/test_first_5_files.py` and `test_single_file.py`: Async tests require CLI-style params and live Gemini calls; they fail under pytest collection. **Recommendation:** Move to scripts/integration folder, add `if __name__ == "__main__"` entrypoints, or mark with `pytest.skip`/xfail by default.

## Logging and Error Handling
- Mixed log levels across modules; warnings often mask real failures (OCR fallbacks, cache disablement). **Recommendation:** Standardize levels and add structured context (claim_id/doc_id) for traceability.
- Error messages surfaced to users (batch service) are still technical in places. **Recommendation:** Provide user-facing summaries with remediation steps.

## Test Suite Gaps
- Heavy reliance on live external services (Gemini/OCR/Redis) with no mocks makes the suite brittle and slow. **Recommendation:** Provide fixtures/mocks and default to offline/test-mode behavior.
