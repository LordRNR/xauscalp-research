# Estudio 7 — ORB sobre el histórico del bróker (walk-forward, costes realistas)

> Nivel de evidencia 1 (velas M1 del feed de MetaQuotes-Demo; Ask = Bid + spread mínimo de la vela). No es un bróker real ni ticks reales. Periodo reservado (≥ 2025-11-01) **no leído**. Escenarios y regla de veredicto fijados antes de ejecutar.

**Veredicto: SIN EVIDENCIA DE VENTAJA NETA**

- ✅ validable (folds suficientes)
- ✅ n_trades >= 100
- ❌ IC95 (bloques semanales) de la expectativa > 0
- ❌ p vs dirección aleatoria < 0,05
- ❌ expectativa > 0 también en C (estrés)

Datos: 2021-01-03 → 2025-10-31, 1,707,302 barras, cobertura 98.1 % (1246/1261 días). Folds válidos: 15. Configuraciones evaluadas por escenario: 36 (selección walk-forward por sesión). Señales retiradas por noticias (primario): 933.

## Escenarios de coste (fijados antes)
| escenario | spread extra | slippage | comisión USD/lote RT |
|---|---|---|---|
| A_demo_as_is | 0.000 | 0.050 | 0.000 |
| B_base | 0.150 | 0.100 | 7.000 |
| C_stress | 0.300 | 0.300 | 7.000 |

## Comparación de escenarios (resultado OOS conjunto)
```
{
 "B_base": {
  "n": 222,
  "exp_R": -0.11301049577236416,
  "IC95_bloques": [
   -0.2526755403619112,
   0.02637322585879475
  ],
  "PF": 0.8056238936860536,
  "win": 0.42342342342342343,
  "p_vs_random": 0.5169660678642715,
  "exp_R_coste_cero": -0.023475284775886555,
  "exp_R_direcci\u00f3n_invertida": -0.1016452685384394
 },
 "A_demo_as_is": {
  "n": 1172,
  "exp_R": -0.06129661441914605,
  "IC95_bloques": [
   -0.12126188877282375,
   -0.0016632699619455748
  ],
  "PF": 0.8904561218874902,
  "win": 0.4052901023890785,
  "p_vs_random": 0.3972055888223553,
  "exp_R_coste_cero": -0.02831060377797779,
  "exp_R_direcci\u00f3n_invertida": -0.08016637558562487
 },
 "C_stress": {
  "n": 84,
  "exp_R": -0.2897123130390674,
  "IC95_bloques": [
   -0.5467640733307364,
   -0.01844052771290089
  ],
  "PF": 0.5776638931660553,
  "win": 0.3333333333333333,
  "p_vs_random": 0.9161676646706587,
  "exp_R_coste_cero": -0.17257614341694477,
  "exp_R_direcci\u00f3n_invertida": -0.004250288998302093
 },
 "B_base (sin noticias)": {
  "n": 169,
  "exp_R": -0.1438964992974616,
  "IC95_bloques": [
   -0.2938039368158702,
   0.022072911470144767
  ],
  "PF": 0.7575991401641871,
  "win": 0.40236686390532544,
  "p_vs_random": 0.8003992015968064,
  "exp_R_coste_cero": -0.06929889479435856,
  "exp_R_direcci\u00f3n_invertida": -0.03469131667074898
 }
}
```

## Primario (B_base + noticias): detalle
```
{
 "n_trades": 222,
 "win_rate": 0.4234,
 "profit_factor": 0.8056,
 "expectancy_r": -0.113,
 "expectancy_r_ci95_iid": [
  -0.2542,
  0.0283
 ],
 "expectancy_r_ci95_weekblock": [
  -0.2527,
  0.0264
 ],
 "p_expectancy_le_0": 0.9412,
 "expectancy_usd_per_001lot": -0.4449,
 "avg_win_r": 1.1062,
 "avg_loss_r": -1.0084,
 "payoff_ratio": 1.097,
 "total_r": -25.0883,
 "total_usd_per_001lot": -98.7775,
 "max_drawdown_r": 32.2795,
 "longest_underwater_trades": 219,
 "sharpe_daily_annualised": -1.6828,
 "sortino_daily_annualised": -1.7643,
 "avg_cost_r": 0.1497,
 "avg_cost_usd_per_001lot": 0.5687,
 "avg_hold_min": 22.491,
 "exit_reasons": {
  "SL": 120,
  "TP": 90,
  "TIME": 12
 },
 "ambiguous_bar_frac": 0.0,
 "exposure_frac": 0.0036,
 "trades_per_week": 1.6104
}
```
### Benchmarks
```
{
 "signals_universe": 222,
 "actual_exp_r": -0.113,
 "random_dir_exp_r_median": -0.1107,
 "random_dir_exp_r_p95": 0.0022,
 "p_value_vs_random_dir": 0.517,
 "faded_direction_exp_r": -0.1016,
 "zero_cost_exp_r": -0.0235
}
```
### Monte Carlo de drawdown (R)
```
{
 "dd_r_median": 32.5745,
 "dd_r_p95": 55.5934,
 "p_dd_ge_8R": 0.999,
 "p_dd_ge_16R": 0.9328,
 "p_dd_ge_20R": 0.8576
}
```
### Selección por fold
| session | train | test | cov_train | cov_test | chosen | train_exp_r | train_n | test_signals |
|---|---|---|---|---|---|---|---|---|
| london | 2021-01-01→2022-01-01 | 2022-01-01→2022-04-01 | 0.990 | 1.000 | ABSTAIN | -0.027 | 59 | nan |
| newyork | 2021-01-01→2022-01-01 | 2022-01-01→2022-04-01 | 0.990 | 1.000 | ABSTAIN | -0.041 | 205 | nan |
| london | 2021-04-01→2022-04-01 | 2022-04-01→2022-07-01 | 0.990 | 0.980 | ABSTAIN | -0.048 | 152 | nan |
| newyork | 2021-04-01→2022-04-01 | 2022-04-01→2022-07-01 | 0.990 | 0.980 | ABSTAIN | -0.081 | 204 | nan |
| london | 2021-07-01→2022-07-01 | 2022-07-01→2022-10-01 | 0.990 | 1.000 | ABSTAIN | -0.174 | 170 | nan |
| newyork | 2021-07-01→2022-07-01 | 2022-07-01→2022-10-01 | 0.990 | 1.000 | ABSTAIN | -0.075 | 201 | nan |
| london | 2021-10-01→2022-10-01 | 2022-10-01→2023-01-01 | 0.990 | 0.980 | ABSTAIN | -0.165 | 165 | nan |
| newyork | 2021-10-01→2022-10-01 | 2022-10-01→2023-01-01 | 0.990 | 0.980 | ABSTAIN | -0.084 | 199 | nan |
| london | 2022-01-01→2023-01-01 | 2023-01-01→2023-04-01 | 0.990 | 0.980 | ABSTAIN | -0.096 | 177 | nan |
| newyork | 2022-01-01→2023-01-01 | 2023-01-01→2023-04-01 | 0.990 | 0.980 | ABSTAIN | -0.095 | 202 | nan |
| london | 2022-04-01→2023-04-01 | 2023-04-01→2023-07-01 | 0.990 | 0.980 | ABSTAIN | -0.141 | 189 | nan |
| newyork | 2022-04-01→2023-04-01 | 2023-04-01→2023-07-01 | 0.990 | 0.980 | ABSTAIN | -0.066 | 204 | nan |
| london | 2022-07-01→2023-07-01 | 2023-07-01→2023-10-01 | 0.990 | 1.000 | ABSTAIN | -0.041 | 171 | nan |
| newyork | 2022-07-01→2023-07-01 | 2023-07-01→2023-10-01 | 0.990 | 1.000 | orb_newyork_or30_sl1.0_tp2.0 | 0.104 | 53 | 8.000 |
| london | 2022-10-01→2023-10-01 | 2023-10-01→2024-01-01 | 0.990 | 0.980 | orb_london_or30_sl1.5_tp2.0 | 0.072 | 63 | 5.000 |
| newyork | 2022-10-01→2023-10-01 | 2023-10-01→2024-01-01 | 0.990 | 0.980 | orb_newyork_or30_sl1.0_tp2.0 | 0.043 | 45 | 9.000 |
| london | 2023-01-01→2024-01-01 | 2024-01-01→2024-04-01 | 0.990 | 0.970 | ABSTAIN | -0.050 | 39 | nan |
| newyork | 2023-01-01→2024-01-01 | 2024-01-01→2024-04-01 | 0.990 | 0.970 | ABSTAIN | -0.042 | 203 | nan |
| london | 2023-04-01→2024-04-01 | 2024-04-01→2024-07-01 | 0.980 | 1.000 | ABSTAIN | -0.025 | 91 | nan |
| newyork | 2023-04-01→2024-04-01 | 2024-04-01→2024-07-01 | 0.980 | 1.000 | ABSTAIN | -0.028 | 197 | nan |
| london | 2023-07-01→2024-07-01 | 2024-07-01→2024-10-01 | 0.990 | 1.000 | orb_london_or30_sl2.0_tp2.0 | 0.005 | 110 | 31.000 |
| newyork | 2023-07-01→2024-07-01 | 2024-07-01→2024-10-01 | 0.990 | 1.000 | ABSTAIN | -0.158 | 202 | nan |
| london | 2023-10-01→2024-10-01 | 2024-10-01→2025-01-01 | 0.990 | 0.980 | ABSTAIN | -0.026 | 135 | nan |
| newyork | 2023-10-01→2024-10-01 | 2024-10-01→2025-01-01 | 0.990 | 0.980 | ABSTAIN | -0.087 | 206 | nan |
| london | 2024-01-01→2025-01-01 | 2025-01-01→2025-04-01 | 0.990 | 0.980 | ABSTAIN | -0.100 | 165 | nan |
| newyork | 2024-01-01→2025-01-01 | 2025-01-01→2025-04-01 | 0.990 | 0.980 | orb_newyork_or15_sl1.5_tp1.0 | 0.001 | 156 | 55.000 |
| london | 2024-04-01→2025-04-01 | 2025-04-01→2025-07-01 | 0.990 | 0.980 | ABSTAIN | -0.071 | 131 | nan |
| newyork | 2024-04-01→2025-04-01 | 2025-04-01→2025-07-01 | 0.990 | 0.980 | orb_newyork_or15_sl1.5_tp1.0 | 0.042 | 182 | 58.000 |
| london | 2024-07-01→2025-07-01 | 2025-07-01→2025-10-01 | 0.990 | 0.970 | ABSTAIN | -0.123 | 201 | nan |
| newyork | 2024-07-01→2025-07-01 | 2025-07-01→2025-10-01 | 0.990 | 0.970 | orb_newyork_or15_sl1.5_tp1.0 | 0.081 | 182 | 56.000 |

### OOS por año
| year | n | expectancy_r | win_rate | total_r | sem_r |
|---|---|---|---|---|---|
| 2023 | 22.000 | -0.105 | 0.318 | -2.318 | 0.310 |
| 2024 | 31.000 | -0.213 | 0.258 | -6.615 | 0.204 |
| 2025 | 169.000 | -0.096 | 0.467 | -16.155 | 0.078 |

### OOS por sesión
| session | n | expectancy_r | win_rate | total_r | sem_r |
|---|---|---|---|---|---|
| london | 36.000 | -0.079 | 0.306 | -2.851 | 0.207 |
| newyork | 186.000 | -0.120 | 0.446 | -22.237 | 0.077 |

## Las 36 combinaciones en todo el periodo (descriptivo, escenario B; NO se usa para elegir)
Con 36 combinaciones el mejor valor está sesgado al alza por azar: no se interpreta. Combinaciones con expectativa > 0: 0 de 36.
| combo | n | exp_r | se |
|---|---|---|---|
| orb_london_or30_sl1.0_tp1.5 | 131.000 | -0.070 | 0.107 |
| orb_london_or30_sl2.0_tp1.0 | 798.000 | -0.086 | 0.034 |
| orb_newyork_or30_sl2.0_tp2.0 | 1009.000 | -0.088 | 0.040 |
| orb_london_or30_sl2.0_tp1.5 | 798.000 | -0.091 | 0.038 |
| orb_london_or30_sl2.0_tp2.0 | 798.000 | -0.093 | 0.040 |
| orb_newyork_or30_sl2.0_tp1.0 | 1009.000 | -0.101 | 0.031 |
| orb_newyork_or30_sl2.0_tp1.5 | 1009.000 | -0.110 | 0.037 |
| orb_london_or15_sl1.5_tp2.0 | 464.000 | -0.110 | 0.060 |
| orb_london_or15_sl1.0_tp2.0 | 145.000 | -0.110 | 0.113 |
| orb_london_or15_sl1.5_tp1.5 | 464.000 | -0.114 | 0.054 |
| orb_london_or15_sl2.0_tp1.0 | 859.000 | -0.120 | 0.033 |
| orb_london_or30_sl1.5_tp1.0 | 441.000 | -0.120 | 0.048 |
| orb_newyork_or15_sl2.0_tp1.0 | 1020.000 | -0.121 | 0.031 |
| orb_london_or15_sl2.0_tp2.0 | 859.000 | -0.121 | 0.039 |
| orb_london_or30_sl1.5_tp1.5 | 441.000 | -0.123 | 0.056 |
| orb_london_or15_sl1.0_tp1.5 | 145.000 | -0.125 | 0.100 |
| orb_london_or15_sl2.0_tp1.5 | 859.000 | -0.126 | 0.037 |
| orb_london_or15_sl1.5_tp1.0 | 464.000 | -0.126 | 0.046 |
| orb_london_or30_sl1.0_tp2.0 | 131.000 | -0.128 | 0.121 |
| orb_newyork_or15_sl2.0_tp1.5 | 1020.000 | -0.130 | 0.037 |
| orb_newyork_or15_sl2.0_tp2.0 | 1020.000 | -0.132 | 0.040 |
| orb_london_or30_sl1.5_tp2.0 | 441.000 | -0.135 | 0.060 |
| orb_newyork_or30_sl1.5_tp2.0 | 866.000 | -0.139 | 0.046 |
| orb_london_or30_sl1.0_tp1.0 | 131.000 | -0.139 | 0.089 |
| orb_newyork_or30_sl1.5_tp1.5 | 866.000 | -0.148 | 0.041 |
| orb_newyork_or30_sl1.5_tp1.0 | 866.000 | -0.162 | 0.034 |
| orb_newyork_or15_sl1.0_tp2.0 | 337.000 | -0.166 | 0.075 |
| orb_london_or15_sl1.0_tp1.0 | 145.000 | -0.167 | 0.084 |
| orb_newyork_or15_sl1.5_tp1.0 | 811.000 | -0.171 | 0.035 |
| orb_newyork_or15_sl1.5_tp2.0 | 811.000 | -0.173 | 0.047 |
| orb_newyork_or15_sl1.5_tp1.5 | 811.000 | -0.177 | 0.042 |
| orb_newyork_or15_sl1.0_tp1.5 | 337.000 | -0.185 | 0.066 |
| orb_newyork_or30_sl1.0_tp2.0 | 430.000 | -0.192 | 0.066 |
| orb_newyork_or30_sl1.0_tp1.5 | 430.000 | -0.197 | 0.058 |
| orb_newyork_or15_sl1.0_tp1.0 | 337.000 | -0.207 | 0.055 |
| orb_newyork_or30_sl1.0_tp1.0 | 430.000 | -0.226 | 0.049 |
