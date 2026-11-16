# Documentation index

The working documents in this folder were written in Spanish while the project was being built. This index gives the English title of each one and says what it is for, so that a reader who does not read Spanish can find the right file. Nothing in it is a translation of the documents' conclusions: for those, the English [README](../README.md) and the reports in [`reports/`](../reports/) are the reference.

| File | Title in English | What it is |
|---|---|---|
| [`00_viabilidad.md`](00_viabilidad.md) | Phase 0: economic and technical feasibility | Whether the idea is worth testing at all, before any strategy work |
| [`01_arquitectura.md`](01_arquitectura.md) | Architecture | Comparison of four architectures and why research is in Python with a separate MetaTrader 5 component |
| [`02_plan_fases.md`](02_plan_fases.md) | Plan by phases with verifiable criteria | The phase plan and its status matrix |
| [`04_fuentes_de_datos.md`](04_fuentes_de_datos.md) | Data sources for XAUUSD | How data enters the code and what quality metadata must accompany any result |
| [`05_mt5_instalacion_y_pruebas.md`](05_mt5_instalacion_y_pruebas.md) | MT5: compilation, exports, time zone, tester and parity | How to compile and run the read-only MQL5 programs and the parity check. It also mentions an order-sending component that is **not** part of this repository |
| [`06_hipotesis_alternativas.md`](06_hipotesis_alternativas.md) | Alternative strategies: preregistered hypotheses and criteria | The hypotheses and verdict rules of study 8, as recorded before it ran |
| [`07_propfirm_viabilidad.md`](07_propfirm_viabilidad.md) | The prop-firm challenge: technical and economic diagnosis | Background for study 9 (simulation only; nothing was bought) |
| [`08_hipotesis_multiactivo.md`](08_hipotesis_multiactivo.md) | Other instruments: preregistered hypotheses (no data yet) | Design of the multi-asset study, which was **not run** |
| [`10_exportacion_multiactivo_y_ftmo.md`](10_exportacion_multiactivo_y_ftmo.md) | Data export for other instruments | Procedure for exporting data from a demo account and from a prop-firm free trial |
| [`auditoria_2026-11-12.md`](auditoria_2026-11-12.md) | Technical audit, 2026-11-12 (public version) | Severity-ranked findings, fixes and regression tests. Findings about the AI tool's own configuration are omitted |
| [`decisiones.md`](decisiones.md) | Decision record (ADR) | One row per decision, with its reason and evidence. Some rows refer to files that are not published |
