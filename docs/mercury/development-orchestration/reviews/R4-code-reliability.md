# R4 — Code and reliability review (devorch.py, resume, configuration)

Status: IN PROGRESS (saved early after a container restart; adversarial tests being run).

Preliminary findings (to be confirmed by tests):
- check-result skips all path/branch checks when `commits` is empty.
- `ready` keys tasks by merc_issue; review contracts share the merc_issue of the implementation.
- record does not detect an in-place contract edit (security_sensitive flip) without contract_revised.
- verify-ledger parses every file in ledger/ (LOCK, ESCALATIONS.md live there).
- git diff --name-only with rename detection hides the source path of a rename.
- fnmatch: `**/x` does not match root files; `*` crosses `/`.
