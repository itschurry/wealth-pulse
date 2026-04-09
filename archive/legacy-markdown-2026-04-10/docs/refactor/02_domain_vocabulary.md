# WealthPulse Domain Vocabulary

## Standard lifecycle terms
- `signal`: strategy or model output before operational promotion
- `candidate`: saved or computed candidate that is not yet active in runtime
- `validated`: candidate passed validation checks
- `approved`: operator-approved candidate ready for runtime promotion
- `applied`: candidate currently used by runtime
- `blocked`: order or candidate blocked by validation, guardrail, or runtime rule
- `stale`: data or judgment is old and needs refresh
- `data_missing`: required input data is unavailable
- `revalidate_required`: candidate must be validated again before promotion

## Naming rules
- Server may keep `snake_case`, client may keep `camelCase`, but the semantic term must stay identical.
- Internal compatibility names such as `ready`, `live`, and `runtimeCandidateSourceMode` are not allowed in new user-facing text.
- `effective_*` is allowed only when it describes analytical clipping or calculation context, not lifecycle state.

## Current compatibility mapping
- strategy registry UI label:
  - `draft -> candidate`
  - `ready -> approved`
  - `enabled -> applied`
- legacy routes remain for compatibility.
- user-visible workspace pages are:
  - `operations-dashboard`
  - `orders-execution`
  - `strategy-operations`
  - `lab`
  - `research-ai`
  - `settings`
- these pages still map internally to the three product modes:
  - operations
  - lab
  - analysis
