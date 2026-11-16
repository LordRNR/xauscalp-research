# Estudio 2 — ORB (London / COMEX open): walk-forward fuera de muestra

> Veredicto de datos: **NO VALIDABLE**: solo 0 folds con cobertura ≥ 90% (se exigen 4). Cualquier cifra de abajo es DIAGNÓSTICO, no evidencia.
> Cobertura del tramo de investigación: 6.9 % (87/1261 días utilizables). Nivel de evidencia: 1 — aproximación con velas M1 (no ticks reales, no DEMO).

Periodo solicitado: 2021-01-01 → 2025-10-31 · holdout ≥ 2025-11-01 **no leído**. Folds: train 12m / test 3m. Configuraciones probadas: 36.

## Resultado OOS — simulación conjunta (1 posición, orden cronológico)
```
{
 "n_trades": 0
}
```
## Benchmarks sobre las MISMAS señales OOS
_sin señales OOS_
## Monte Carlo de drawdown (R)
_n/a_
## Selección por fold
| session | train | test | cov_train | cov_test | chosen |
|---|---|---|---|---|---|
| london | 2021-01-01→2022-01-01 | 2022-01-01→2022-04-01 | 0.200 | 0.000 | INSUFFICIENT_DATA |
| newyork | 2021-01-01→2022-01-01 | 2022-01-01→2022-04-01 | 0.200 | 0.000 | INSUFFICIENT_DATA |
| london | 2021-04-01→2022-04-01 | 2022-04-01→2022-07-01 | 0.000 | 0.000 | INSUFFICIENT_DATA |
| newyork | 2021-04-01→2022-04-01 | 2022-04-01→2022-07-01 | 0.000 | 0.000 | INSUFFICIENT_DATA |
| london | 2021-07-01→2022-07-01 | 2022-07-01→2022-10-01 | 0.000 | 0.000 | INSUFFICIENT_DATA |
| newyork | 2021-07-01→2022-07-01 | 2022-07-01→2022-10-01 | 0.000 | 0.000 | INSUFFICIENT_DATA |
| london | 2021-10-01→2022-10-01 | 2022-10-01→2023-01-01 | 0.000 | 0.000 | INSUFFICIENT_DATA |
| newyork | 2021-10-01→2022-10-01 | 2022-10-01→2023-01-01 | 0.000 | 0.000 | INSUFFICIENT_DATA |
| london | 2022-01-01→2023-01-01 | 2023-01-01→2023-04-01 | 0.000 | 0.000 | INSUFFICIENT_DATA |
| newyork | 2022-01-01→2023-01-01 | 2023-01-01→2023-04-01 | 0.000 | 0.000 | INSUFFICIENT_DATA |
| london | 2022-04-01→2023-04-01 | 2023-04-01→2023-07-01 | 0.000 | 0.000 | INSUFFICIENT_DATA |
| newyork | 2022-04-01→2023-04-01 | 2023-04-01→2023-07-01 | 0.000 | 0.000 | INSUFFICIENT_DATA |
| london | 2022-07-01→2023-07-01 | 2023-07-01→2023-10-01 | 0.000 | 0.000 | INSUFFICIENT_DATA |
| newyork | 2022-07-01→2023-07-01 | 2023-07-01→2023-10-01 | 0.000 | 0.000 | INSUFFICIENT_DATA |
| london | 2022-10-01→2023-10-01 | 2023-10-01→2024-01-01 | 0.000 | 0.000 | INSUFFICIENT_DATA |
| newyork | 2022-10-01→2023-10-01 | 2023-10-01→2024-01-01 | 0.000 | 0.000 | INSUFFICIENT_DATA |
| london | 2023-01-01→2024-01-01 | 2024-01-01→2024-04-01 | 0.000 | 0.000 | INSUFFICIENT_DATA |
| newyork | 2023-01-01→2024-01-01 | 2024-01-01→2024-04-01 | 0.000 | 0.000 | INSUFFICIENT_DATA |
| london | 2023-04-01→2024-04-01 | 2024-04-01→2024-07-01 | 0.000 | 0.000 | INSUFFICIENT_DATA |
| newyork | 2023-04-01→2024-04-01 | 2024-04-01→2024-07-01 | 0.000 | 0.000 | INSUFFICIENT_DATA |
| london | 2023-07-01→2024-07-01 | 2024-07-01→2024-10-01 | 0.000 | 0.000 | INSUFFICIENT_DATA |
| newyork | 2023-07-01→2024-07-01 | 2024-07-01→2024-10-01 | 0.000 | 0.000 | INSUFFICIENT_DATA |
| london | 2023-10-01→2024-10-01 | 2024-10-01→2025-01-01 | 0.000 | 0.000 | INSUFFICIENT_DATA |
| newyork | 2023-10-01→2024-10-01 | 2024-10-01→2025-01-01 | 0.000 | 0.000 | INSUFFICIENT_DATA |
| london | 2024-01-01→2025-01-01 | 2025-01-01→2025-04-01 | 0.000 | 0.000 | INSUFFICIENT_DATA |
| newyork | 2024-01-01→2025-01-01 | 2025-01-01→2025-04-01 | 0.000 | 0.000 | INSUFFICIENT_DATA |
| london | 2024-04-01→2025-04-01 | 2025-04-01→2025-07-01 | 0.000 | 0.000 | INSUFFICIENT_DATA |
| newyork | 2024-04-01→2025-04-01 | 2025-04-01→2025-07-01 | 0.000 | 0.000 | INSUFFICIENT_DATA |
| london | 2024-07-01→2025-07-01 | 2025-07-01→2025-10-01 | 0.000 | 0.230 | INSUFFICIENT_DATA |
| newyork | 2024-07-01→2025-07-01 | 2025-07-01→2025-10-01 | 0.000 | 0.230 | INSUFFICIENT_DATA |
