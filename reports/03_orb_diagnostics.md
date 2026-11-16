# Estudio 3 — Diagnóstico ORB: ¿por qué (no) opera?

> Cobertura del tramo de investigación: **6.9 %** (87/1261 días utilizables). Con esta cobertura el estudio es **descriptivo** de los segmentos disponibles; no estima rentabilidad.

Segmentos de datos usados:
```
                              desde                      hasta  barras
segmento                                                              
0         2021-01-03 23:00:00+00:00  2021-03-04 23:59:00+00:00   60298
1         2021-03-12 00:00:00+00:00  2021-03-23 23:59:00+00:00    9720
2         2021-03-28 22:00:00+00:00  2021-03-28 23:59:00+00:00     120
3         2025-09-03 00:00:00+00:00  2025-09-24 23:59:00+00:00   20700
4         2025-10-02 00:00:00+00:00  2025-10-31 20:59:00+00:00   28860
```
Reglas sin cambios (filtro coste/SL = 20%, spread máx. = 0.6 $ incl. 0.15 $ extra de bróker).

## Embudo por configuración
| config | días-sesión | sin datos/ATR | evaluables | sin señal técnica | señal técnica | rechazo spread | rechazo coste/SL | operables |
|---|---|---|---|---|---|---|---|---|
| london or15 sl1.0 | 1260 | 1173 | 87 | 5 | 82 | 43 | 38 | 1 |
| london or15 sl1.5 | 1260 | 1173 | 87 | 5 | 82 | 43 | 33 | 6 |
| london or15 sl2.0 | 1260 | 1173 | 87 | 5 | 82 | 43 | 23 | 16 |
| london or30 sl1.0 | 1260 | 1173 | 87 | 19 | 68 | 40 | 28 | 0 |
| london or30 sl1.5 | 1260 | 1173 | 87 | 19 | 68 | 40 | 23 | 5 |
| london or30 sl2.0 | 1260 | 1173 | 87 | 19 | 68 | 40 | 17 | 11 |
| newyork or15 sl1.0 | 1260 | 1173 | 87 | 5 | 82 | 46 | 33 | 3 |
| newyork or15 sl1.5 | 1260 | 1173 | 87 | 5 | 82 | 46 | 19 | 17 |
| newyork or15 sl2.0 | 1260 | 1173 | 87 | 5 | 82 | 46 | 5 | 31 |
| newyork or30 sl1.0 | 1260 | 1173 | 87 | 9 | 78 | 44 | 31 | 3 |
| newyork or30 sl1.5 | 1260 | 1173 | 87 | 9 | 78 | 44 | 11 | 23 |
| newyork or30 sl2.0 | 1260 | 1173 | 87 | 9 | 78 | 44 | 3 | 31 |

## Breakouts técnicos: ¿cuánto pesa el coste frente al stop?
`cost_frac` = (spread + 2×slippage) / distancia del SL. El filtro exige ≤ 0.20.
| config | breakouts | tradable | cost_frac_p25 | cost_frac_med | cost_frac_p75 | spread_med | atr_med | sl_usd_med |
|---|---|---|---|---|---|---|---|---|
| london or15 sl1.0 | 82.000 | 1.000 | 0.245 | 0.354 | 0.431 | 0.600 | 1.957 | 1.957 |
| london or15 sl1.5 | 82.000 | 6.000 | 0.163 | 0.236 | 0.288 | 0.600 | 1.957 | 2.936 |
| london or15 sl2.0 | 82.000 | 16.000 | 0.122 | 0.177 | 0.216 | 0.600 | 1.957 | 3.915 |
| london or30 sl1.0 | 68.000 | 0.000 | 0.238 | 0.320 | 0.415 | 0.630 | 2.033 | 2.033 |
| london or30 sl1.5 | 68.000 | 5.000 | 0.159 | 0.213 | 0.276 | 0.630 | 2.033 | 3.049 |
| london or30 sl2.0 | 68.000 | 11.000 | 0.119 | 0.160 | 0.207 | 0.630 | 2.033 | 4.066 |
| newyork or15 sl1.0 | 82.000 | 3.000 | 0.213 | 0.288 | 0.342 | 0.611 | 2.546 | 2.546 |
| newyork or15 sl1.5 | 82.000 | 17.000 | 0.142 | 0.192 | 0.228 | 0.611 | 2.546 | 3.819 |
| newyork or15 sl2.0 | 82.000 | 31.000 | 0.107 | 0.144 | 0.171 | 0.611 | 2.546 | 5.092 |
| newyork or30 sl1.0 | 78.000 | 3.000 | 0.206 | 0.252 | 0.304 | 0.617 | 2.698 | 2.698 |
| newyork or30 sl1.5 | 78.000 | 23.000 | 0.137 | 0.168 | 0.202 | 0.617 | 2.698 | 4.046 |
| newyork or30 sl2.0 | 78.000 | 31.000 | 0.103 | 0.126 | 0.152 | 0.617 | 2.698 | 5.395 |

## Simulación de las señales operables (solo recuento)
| config | signals | simulated | valid | invalid_data_gap |
|---|---|---|---|---|
| london or15 sl1.0 | 1 | 1 | 1 | 0 |
| london or15 sl1.5 | 6 | 6 | 6 | 0 |
| london or15 sl2.0 | 16 | 16 | 16 | 0 |
| london or30 sl1.5 | 5 | 5 | 5 | 0 |
| london or30 sl2.0 | 11 | 11 | 11 | 0 |
| newyork or15 sl1.0 | 3 | 3 | 3 | 0 |
| newyork or15 sl1.5 | 17 | 17 | 17 | 0 |
| newyork or15 sl2.0 | 31 | 31 | 31 | 0 |
| newyork or30 sl1.0 | 3 | 3 | 3 | 0 |
| newyork or30 sl1.5 | 23 | 23 | 23 | 0 |
| newyork or30 sl2.0 | 31 | 31 | 31 | 0 |

## ¿Sería posible con este capital? (Risk Manager, cuenta en USD, apalancamiento 20:1, contrato 100 oz, mínimo 0.01 lotes — valores de configuración, NO del bróker)
| config | equity_usd | signals | approved | MIN_VOLUME_EXCEEDS_RISK | INSUFFICIENT_MARGIN | other |
|---|---|---|---|---|---|---|
| london or15 sl1.0 | 23 | 1 | 0 | 1 | 0 | 0 |
| london or15 sl1.0 | 500 | 1 | 0 | 1 | 0 | 0 |
| london or15 sl1.0 | 1000 | 1 | 0 | 1 | 0 | 0 |
| london or15 sl1.0 | 10000 | 1 | 1 | 0 | 0 | 0 |
| london or15 sl1.0 | 100000 | 1 | 1 | 0 | 0 | 0 |
| london or15 sl1.5 | 23 | 6 | 0 | 6 | 0 | 0 |
| london or15 sl1.5 | 500 | 6 | 0 | 6 | 0 | 0 |
| london or15 sl1.5 | 1000 | 6 | 5 | 1 | 0 | 0 |
| london or15 sl1.5 | 10000 | 6 | 6 | 0 | 0 | 0 |
| london or15 sl1.5 | 100000 | 6 | 6 | 0 | 0 | 0 |
| london or15 sl2.0 | 23 | 16 | 0 | 16 | 0 | 0 |
| london or15 sl2.0 | 500 | 16 | 0 | 16 | 0 | 0 |
| london or15 sl2.0 | 1000 | 16 | 14 | 2 | 0 | 0 |
| london or15 sl2.0 | 10000 | 16 | 16 | 0 | 0 | 0 |
| london or15 sl2.0 | 100000 | 16 | 16 | 0 | 0 | 0 |
| london or30 sl1.5 | 23 | 5 | 0 | 5 | 0 | 0 |
| london or30 sl1.5 | 500 | 5 | 0 | 5 | 0 | 0 |
| london or30 sl1.5 | 1000 | 5 | 5 | 0 | 0 | 0 |
| london or30 sl1.5 | 10000 | 5 | 5 | 0 | 0 | 0 |
| london or30 sl1.5 | 100000 | 5 | 5 | 0 | 0 | 0 |
| london or30 sl2.0 | 23 | 11 | 0 | 11 | 0 | 0 |
| london or30 sl2.0 | 500 | 11 | 0 | 11 | 0 | 0 |
| london or30 sl2.0 | 1000 | 11 | 11 | 0 | 0 | 0 |
| london or30 sl2.0 | 10000 | 11 | 11 | 0 | 0 | 0 |
| london or30 sl2.0 | 100000 | 11 | 11 | 0 | 0 | 0 |
| newyork or15 sl1.0 | 23 | 3 | 0 | 3 | 0 | 0 |
| newyork or15 sl1.0 | 500 | 3 | 0 | 3 | 0 | 0 |
| newyork or15 sl1.0 | 1000 | 3 | 2 | 1 | 0 | 0 |
| newyork or15 sl1.0 | 10000 | 3 | 3 | 0 | 0 | 0 |
| newyork or15 sl1.0 | 100000 | 3 | 3 | 0 | 0 | 0 |
| newyork or15 sl1.5 | 23 | 17 | 0 | 17 | 0 | 0 |
| newyork or15 sl1.5 | 500 | 17 | 0 | 17 | 0 | 0 |
| newyork or15 sl1.5 | 1000 | 17 | 14 | 3 | 0 | 0 |
| newyork or15 sl1.5 | 10000 | 17 | 17 | 0 | 0 | 0 |
| newyork or15 sl1.5 | 100000 | 17 | 17 | 0 | 0 | 0 |
| newyork or15 sl2.0 | 23 | 31 | 0 | 31 | 0 | 0 |
| newyork or15 sl2.0 | 500 | 31 | 0 | 31 | 0 | 0 |
| newyork or15 sl2.0 | 1000 | 31 | 18 | 13 | 0 | 0 |
| newyork or15 sl2.0 | 10000 | 31 | 31 | 0 | 0 | 0 |
| newyork or15 sl2.0 | 100000 | 31 | 31 | 0 | 0 | 0 |
| newyork or30 sl1.0 | 23 | 3 | 0 | 3 | 0 | 0 |
| newyork or30 sl1.0 | 500 | 3 | 0 | 3 | 0 | 0 |
| newyork or30 sl1.0 | 1000 | 3 | 2 | 1 | 0 | 0 |
| newyork or30 sl1.0 | 10000 | 3 | 3 | 0 | 0 | 0 |
| newyork or30 sl1.0 | 100000 | 3 | 3 | 0 | 0 | 0 |
| newyork or30 sl1.5 | 23 | 23 | 0 | 23 | 0 | 0 |
| newyork or30 sl1.5 | 500 | 23 | 0 | 23 | 0 | 0 |
| newyork or30 sl1.5 | 1000 | 23 | 21 | 2 | 0 | 0 |
| newyork or30 sl1.5 | 10000 | 23 | 23 | 0 | 0 | 0 |
| newyork or30 sl1.5 | 100000 | 23 | 23 | 0 | 0 | 0 |
| newyork or30 sl2.0 | 23 | 31 | 0 | 31 | 0 | 0 |
| newyork or30 sl2.0 | 500 | 31 | 0 | 31 | 0 | 0 |
| newyork or30 sl2.0 | 1000 | 31 | 18 | 13 | 0 | 0 |
| newyork or30 sl2.0 | 10000 | 31 | 31 | 0 | 0 | 0 |
| newyork or30 sl2.0 | 100000 | 31 | 31 | 0 | 0 | 0 |
