# Draft 08: Atomic ID Generation

## Goal
Remove race conditions in `CL` and `FV` ID creation so concurrent requests cannot generate duplicate IDs.

## Current Risk
- Current flow reads max ID, increments in app code, then inserts.
- Two simultaneous requests can calculate the same next ID and one fails.
- A failed insert can surface as a user-facing server error.

## Scope
- `credit_lines.id` generation (`CL001`, `CL002`, ...)
- `fixed_advances.id` generation (`FV0001`, `FV0002`, ...)
- Related create APIs in Flask.

## Recommended Approach
1. Add sequence tables:
- `id_sequences(name TEXT PRIMARY KEY, last_value INTEGER NOT NULL)`
- Seed rows: `('credit_lines', <current max>)`, `('fixed_advances', <current max>)`

2. Generate IDs inside a single DB transaction:
- `BEGIN IMMEDIATE`
- `UPDATE id_sequences SET last_value = last_value + 1 WHERE name = ?`
- `SELECT last_value FROM id_sequences WHERE name = ?`
- Build formatted ID (`CL%03d`, `FV%04d`)
- Insert target row
- `COMMIT`

3. Handle collisions defensively:
- Keep a retry loop (small bounded retries) around transaction for `SQLITE_BUSY`.
- Return clean API errors if retry budget is exceeded.

## Migration Plan
1. Add migration creating `id_sequences`.
2. Backfill sequence values from existing data:
- `credit_lines`: max numeric part of `id` or 0
- `fixed_advances`: max numeric part of `id` or 0
3. Keep existing IDs unchanged.
4. Deploy migration before app logic switch.

## Test Plan
1. Unit test ID formatting boundaries (`CL009` -> `CL010`, `FV0999` -> `FV1000`).
2. Integration test create endpoints return unique IDs sequentially.
3. Concurrency test (parallel creates) verifies no duplicates and no unhandled 500s.
4. Migration test for empty DB and populated DB.

## Acceptance Criteria
- No duplicate `id` failures during parallel create tests.
- Existing records remain intact.
- ID format remains exactly as today.
- Create endpoints return stable success/error responses under load.

## Rollout / Fallback
- Rollout as a single migration + app release.
- Fallback: app can continue with existing tables; migration is additive and low risk.
