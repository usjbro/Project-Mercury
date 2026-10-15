# 09 — Resource and Cost Management Strategy

**Planning constraint, not a measurement:** the operator's development machine is a MacBook Air M2 with 16 GB RAM. This design session runs in a Linux cloud container (Claude Code on the web), which does not load the Mac at all.

## 1. Where work runs

| Work | Where | Why |
|---|---|---|
| Orchestrator + agent-only tasks (T0–T3, CI) | Claude Code cloud session (preferred) or the Mac | Cloud sessions leave the Mac free for validation |
| Mac validation tasks (T4/T5/ⓗ/[ROOT]) | Operator on the Mac, from scripts prepared by agents | Only the real Mac can produce this evidence |
| macOS-specific automated tests (both SQLite drivers, `F_FULLFSYNC` logic, Seatbelt profile parsing) | GitHub-hosted macOS runners in MERCURY's own CI | Offloads the Mac lane (scenario C′). Cannot run nested VMs |
| Power-loss tests | macOS guest VM (operator-run, MERC-802) | TDD RD-24 |

Using several parallel **cloud** sessions as extra workers (the `create_session` capability seen in this environment) is **not configured and not verified**. It needs operator authorization (DOD-07) because of cost, and because each remote session holds the operator's GitHub authorization. Cloud execution is a *development* convenience. It changes nothing in production MERCURY's local-first architecture.

## 2. Concurrency limits

| Limit | Initial value | Rationale |
|---|---|---|
| Concurrent implementation agents | **3** (scenario B) | The model shows no gain beyond 3 (`05-…` §4) |
| Concurrent review agents | 2 (in addition) | Reviews are short and read-only |
| Concurrent Mac-lane tasks | 1 | One operator, one Mac |
| Open PRs awaiting the operator | **≤ 4** (plus ≤ 2 stacked) | Keep human review quality (RISK-22) |
| Tasks per agent instance | 1 | No reuse of context across tasks (independence, context hygiene) |

When the orchestrator runs on the Mac rather than in the cloud, start at **2** implementation agents and raise to 3 only if the §3 metrics stay green for 5 working days.

## 3. Measurements

Every result reports `usage` (turns, wall minutes, tokens and cost where available). The orchestrator also appends one line per tick to `reports/metrics.jsonl`:

| Metric | Source | Red threshold (initial) |
|---|---|---|
| Memory pressure / swap (Mac runs) | `memory_pressure`, `vm_stat` via a Mac-lane script | Swap growth > 1 GB/h, or pressure "critical" |
| CPU utilization | `top -l 1` (Mac) / container metrics | > 85 % sustained 10 min |
| Process count | `ps` count of `claude`/`node` processes | > 40 |
| Agent duration vs `max_wall_minutes` | Ledger timestamps | > 80 % of budget on 3 consecutive tasks |
| API usage / estimated cost | `usage.cost_usd` or token × price | Daily cap (DOD-08); 80 % → stop new dispatch |
| Context utilization | Agent reports `partial` with context reason | Any → split future tasks of that type |
| Throughput | Tasks reaching G2 per day | Trend only |
| Failure / retry rate | `attempt_failed` / `assigned` | > 30 % over 10 tasks |
| Review rejection rate | `code_review_changes_required` / reviews | > 50 % → improve contracts |
| Human queue | Open PRs AWAITING_HUMAN | > 4 → stop opening PRs |

## 4. Adjusting concurrency (control rule)

Evaluate at each wave boundary, or every 5 working days:

1. Any red resource metric → **decrease** concurrency by 1, minimum 1.
2. All green, implementation agents at capacity for > 50 % of the period, READY queue ≥ 2 × workers, and human queue < 4 → **increase** by 1, maximum 4.
3. Refit the schedule model's speed factor from completed tasks: actual agent wall-days ÷ P50. Re-run `schedule_model.py`, and report the new estimate as **measured-based** with its sample size.

## 5. Cost controls

- **Daily cost cap** (DOD-08) and per-task `budget.max_cost_usd`. Dispatch stops at 80 % of the daily cap.
- **Cheap work on cheaper models.** `model: inherit` by default. The TPM and report generation may be pinned to a cheaper model later, through an operator-approved change to the generator.
- **Short, bounded tasks.** Issues with P50 > 3 days are split before READY, as issue-breakdown already requires.
- **No idle work.** No speculative work, duplicate exploration, or agents "kept busy".
