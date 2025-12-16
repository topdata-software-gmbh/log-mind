---
filename: "ai-plans/251216__IMPLEMENTATION_REPORT__fix-context-window-exceeded.md"
title: "Report: Fix Context Window Exceeded Error in Ingestion"
createdAt: 2025-12-16 13:25
updatedAt: 2025-12-16 13:25
planFile: "ai-plans/251216__IMPLEMENTATION_PLAN__fix-context-window-exceeded.md"
project: "logmind"
status: completed
filesCreated: 0
filesModified: 3
filesDeleted: 0
tags: [bugfix, ai, stability]
documentType: IMPLEMENTATION_REPORT
---

## Summary
Fixed the critical crash during ingestion of large files caused by `ContextWindowExceededError`. The ingestion pipeline now truncates oversized entries before calling the embedding API, retries once with a hard truncate if needed, and skips entries that still fail, ensuring the batch can complete.

## Files Changed
- **Modified `logmind/config.py`**: Added `MAX_EMBEDDING_INPUT_CHARS` (24,000) safety constant.
- **Modified `logmind/core/ai.py`**:
  - `get_embedding` now returns `Optional[List[float]]` and performs pre-emptive truncation.
  - Added targeted handling for `ContextWindowExceededError` with a retry using aggressive truncation and graceful fallback to `None`.
- **Modified `logmind/commands/ingest_cmd.py`**:
  - Skip records whose embeddings fail and track skipped counts.
  - Only store vectors/logs that succeeded; emit user-facing summary messages.

## Key Changes
- **Safety Guardrail**: New `MAX_EMBEDDING_INPUT_CHARS` limit constrains requests to an estimated safe size for the 8k model context window.
- **Resilient Embedding Calls**: AIClient now handles empty text, truncates proactively, retries once on context errors, and returns `None` instead of raising.
- **Graceful Ingestion**: Ingestion command now tolerates failures by skipping problematic entries and reporting the number skipped instead of aborting the entire job.

## Testing Notes
1. Run ingestion on the large CSV: `logmind ingest shopware6-api-error-logs__2025-12-16_1151.csv`.
2. Observe warnings when entries exceed the limit; pipeline continues processing.
3. Confirm final output reports skipped entries and completes without crashing.
