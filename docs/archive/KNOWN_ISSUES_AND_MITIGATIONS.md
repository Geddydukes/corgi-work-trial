# Known Issues and Mitigations (2025-12-29)

- Drive downloads can fail with `[SSL] record layer failure` / `ResponseNotReady` under concurrent processing.  
  **Mitigation:** Reduce Drive download concurrency; add retries around `files().get().execute()`; prefer batching metadata and filtering to addendum/move-out/invoice PDFs to shrink the download set.

- Gemini/LLM calls run concurrently per claim and across claims without global rate limiting.  
  **Mitigation:** Add a shared async semaphore around Gemini calls, reuse a single client instance, and set per-call timeouts/backoff.

- Invoice parser reconciliation bug (`all_items` undefined) forces fallbacks and test failures.  
  **Mitigation:** Fix reference to use the composed item list and add regression coverage for negative amounts/credits.

- Optional deps (google.generativeai, Tesseract, Redis) not always guarded. Missing deps can break imports or silently disable features.  
  **Mitigation:** Guard imports, add a TEST/OFFLINE mode, and log clear fallbacks.

- Frontend UX limits: long line-item lists render without virtualization; error states are minimal in variance/decision views.  
  **Mitigation:** Add windowing for large lists, richer error banners, and loading/skeleton states where data can be large.

- Sanity caps and approval-leaning defaults may diverge from legacy expectations.  
  **Mitigation:** Document config multipliers and default assumptions; align tests/spec or gate with env flags.
