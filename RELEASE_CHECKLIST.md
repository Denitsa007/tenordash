# Release Checklist

Use this checklist before and after merging changes to `main`.

## 1) Pre-Release

- [ ] Confirm PR scope and linked issue(s) are complete.
- [ ] Ensure CI is green on the PR.
- [ ] Run local checks:
  - [ ] `python3 -m py_compile $(git ls-files '*.py')`
  - [ ] `python3 -m unittest discover -s tests -v`
- [ ] Review migration risk (if schema/data logic changed).
- [ ] Prepare rollback notes (commit hash to revert, impacted files, DB implications).

## 2) Data Safety (Before Merge)

- [ ] Backup SQLite DB file:
  - [ ] Copy `fixed_advances.db` to a timestamped backup (for example `backups/fixed_advances_YYYYMMDD_HHMM.db`).
- [ ] Confirm backup file is readable and non-empty.
- [ ] If change affects exports, verify export destination has enough disk space.

## 3) Release

- [ ] Merge PR to `main` (no failing checks).
- [ ] Pull latest `main` locally.
- [ ] Record release note entry in PR description or changelog (if maintained).

## 4) Post-Release Smoke Test

- [ ] App starts successfully (`python3 app.py`).
- [ ] Dashboard loads without errors.
- [ ] CRUD sanity checks:
  - [ ] Create/edit/delete a bank.
  - [ ] Create/edit/delete a credit line.
  - [ ] Create/edit/delete an advance.
- [ ] Verify continuation suggestion endpoint works from UI flow.
- [ ] Verify CL capacity warning flow still works.
- [ ] Verify currency add/delete flows behave as expected.
- [ ] Confirm `.xlsx` export file is generated/updated after saving an advance.
- [ ] Confirm print action opens and output is readable (landscape, clean tables, FX footer).
- [ ] Confirm Excel import preview and execute work with a test file.

## 5) Rollback Plan

If critical issues appear post-merge:

- [ ] Stop making additional data mutations in the app.
- [ ] Revert the offending commit(s) on `main` via a new PR.
- [ ] If data corruption is suspected, restore the latest known-good DB backup.
- [ ] Re-run smoke tests after rollback.
- [ ] Document root cause and prevention follow-up issue.
