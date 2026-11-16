# MQL5 code

| File | Phase | Trades? | Status |
|---|---|---|---|
| `Scripts/XAU_FeasibilityReport.mq5` | 0 | **No** (OrderCheck only) | COMPILED 0/0 · run on MetaQuotes-Demo 2026-11-12 |
| `Scripts/XAU_ExportHistory.mq5` | 1 | **No** | COMPILED 0/0 · not yet run |
| `Scripts/XAU_ExportTicks.mq5` | 1 | **No** | COMPILED 0/0 · not yet run |
| `Experts/XauScalp_ReadOnly.mq5` + `Include/XauScalp/*.mqh` | 5 (stage A) | **No** (read-only) | COMPILED 0/0 · not yet run in the Strategy Tester |

"COMPILED 0/0" = 0 errors, 0 warnings with MetaEditor's command line (2026-11-14,
`reports/mt5_build/SUMMARY.md`). Compiling proves syntax only.

Install + compile from the Mac (copies only this project's files, never deletes, refuses
to copy code with trading calls):

    uv run python -m xauscalp.mt5_build all

Edit the sources HERE, not in MetaEditor. Step-by-step usage: `docs/05_mt5_instalacion_y_pruebas.md`.
