# Estudio 8 — Estrategias alternativas en XAUUSD (preregistrado)

> Hipótesis, rejilla, costes, protocolo y criterios fijados en `docs/06_hipotesis_alternativas.md` y `src/xauscalp/strategies/alt.py` **antes** de ejecutar. Nivel de evidencia 1 (M1 del bróker de MetaQuotes-Demo; Ask = Bid + spread de la vela). Periodo reservado (≥ 2025-11-01) **no leído**.

**Veredicto global: SIN EVIDENCIA DE VENTAJA NETA EN NINGUNA FAMILIA**
Configuraciones evaluadas: 22 en 4 familias; los resultados siguientes son de la ejecución B (base) salvo indicación.

## Resumen por familia (B = costes base)
| familia | n OOS | exp R (B) | IC95 inf | exp R (A) | exp R (C) | R a coste cero | R invertida | p aleat. | cumple 8/8 |
|---|---|---|---|---|---|---|---|---|---|
| trend_donchian | 159 | 0.2421 | -0.0241 | 0.1271 | 0.2075 | 0.2565 | -0.0824 | 0.0160 | no |
| momentum_tsmom | 578 | -0.0482 | -0.1382 | -0.0426 | -0.1057 | -0.0165 | -0.0434 | 0.6727 | no |
| pullback | 267 | 0.0168 | -0.1329 | 0.0901 | -0.0387 | 0.0600 | -0.0816 | 0.1816 | no |
| mean_reversion | 48 | -0.1130 | -0.3745 | -0.0457 | nan | -0.0736 | -0.0139 | 0.7126 | no |

## trend_donchian

| criterio | cumple | dato |
|---|---|---|
| 1 validable (≥ 4 folds) | ✅ | 15 folds |
| 2 ≥ 150 operaciones | ✅ | n=159 |
| 3 IC95 bloques semanales > 0 | ❌ | [-0.024, 0.534] |
| 4 p vs dirección aleatoria < 0.0125 | ❌ | p=0.016 |
| 5 expectativa > 0 con costes C | ✅ | C: 0.207 R |
| 6 ≥ 60% folds y ≥ 3/5 años positivos | ❌ | folds+ 67%, años+ 2/3 |
| 7 dirección invertida < 0 | ✅ | -0.082 R |
| 8 reproducible (mismo hash en 2 ejecuciones) | ✅ | c23aae38ec34d974 |

OOS por año:
| year | n | expectancy_r | win_rate | total_r | sem_r |
|---|---|---|---|---|---|
| 2022 | 34.000 | -0.114 | 0.294 | -3.891 | 0.281 |
| 2024 | 60.000 | 0.090 | 0.350 | 5.404 | 0.225 |
| 2025 | 65.000 | 0.569 | 0.508 | 36.973 | 0.224 |

R por fold OOS:
| test_start | n | sum_r |
|---|---|---|
| 2022-01-01 | 17.00 | 0.18 |
| 2022-04-01 | 17.00 | -4.07 |
| 2024-01-01 | 17.00 | -0.81 |
| 2024-04-01 | 13.00 | -1.28 |
| 2024-07-01 | 13.00 | 7.06 |
| 2024-10-01 | 17.00 | 0.43 |
| 2025-01-01 | 19.00 | 15.28 |
| 2025-04-01 | 21.00 | 13.05 |
| 2025-07-01 | 25.00 | 8.64 |

Viabilidad de capital (aparte): SL mediano 19.3 USD → 0,01 lotes arriesgan ≈ 19.3 USD; para un riesgo del 0,5 % haría falta ≈ 3,861 USD de capital.

## momentum_tsmom

| criterio | cumple | dato |
|---|---|---|
| 1 validable (≥ 4 folds) | ✅ | 15 folds |
| 2 ≥ 150 operaciones | ✅ | n=578 |
| 3 IC95 bloques semanales > 0 | ❌ | [-0.138, 0.046] |
| 4 p vs dirección aleatoria < 0.0125 | ❌ | p=0.673 |
| 5 expectativa > 0 con costes C | ❌ | C: -0.106 R |
| 6 ≥ 60% folds y ≥ 3/5 años positivos | ❌ | folds+ 40%, años+ 2/4 |
| 7 dirección invertida < 0 | ✅ | -0.043 R |
| 8 reproducible (mismo hash en 2 ejecuciones) | ✅ | 6b0cb6dd41b8a818 |

OOS por año:
| year | n | expectancy_r | win_rate | total_r | sem_r |
|---|---|---|---|---|---|
| 2022 | 179.000 | -0.124 | 0.413 | -22.164 | 0.074 |
| 2023 | 152.000 | -0.100 | 0.362 | -15.239 | 0.104 |
| 2024 | 143.000 | 0.007 | 0.378 | 0.936 | 0.116 |
| 2025 | 104.000 | 0.083 | 0.442 | 8.614 | 0.118 |

R por fold OOS:
| test_start | n | sum_r |
|---|---|---|
| 2022-01-01 | 46.00 | -12.88 |
| 2022-04-01 | 45.00 | -2.32 |
| 2022-07-01 | 44.00 | -2.17 |
| 2022-10-01 | 44.00 | -4.80 |
| 2023-01-01 | 33.00 | 12.03 |
| 2023-04-01 | 40.00 | -8.91 |
| 2023-07-01 | 43.00 | -11.83 |
| 2023-10-01 | 36.00 | -6.52 |
| 2024-01-01 | 33.00 | 2.45 |
| 2024-04-01 | 40.00 | -8.04 |
| 2024-07-01 | 36.00 | 5.14 |
| 2024-10-01 | 34.00 | 1.39 |
| 2025-01-01 | 34.00 | 3.70 |
| 2025-04-01 | 36.00 | -4.99 |
| 2025-07-01 | 34.00 | 9.90 |

Viabilidad de capital (aparte): SL mediano 14.3 USD → 0,01 lotes arriesgan ≈ 14.3 USD; para un riesgo del 0,5 % haría falta ≈ 2,869 USD de capital.

## pullback

| criterio | cumple | dato |
|---|---|---|
| 1 validable (≥ 4 folds) | ✅ | 15 folds |
| 2 ≥ 150 operaciones | ✅ | n=267 |
| 3 IC95 bloques semanales > 0 | ❌ | [-0.133, 0.179] |
| 4 p vs dirección aleatoria < 0.0125 | ❌ | p=0.182 |
| 5 expectativa > 0 con costes C | ❌ | C: -0.039 R |
| 6 ≥ 60% folds y ≥ 3/5 años positivos | ❌ | folds+ 54%, años+ 2/4 |
| 7 dirección invertida < 0 | ✅ | -0.082 R |
| 8 reproducible (mismo hash en 2 ejecuciones) | ✅ | e15775fcdac23734 |

OOS por año:
| year | n | expectancy_r | win_rate | total_r | sem_r |
|---|---|---|---|---|---|
| 2022 | 58.000 | -0.090 | 0.328 | -5.204 | 0.161 |
| 2023 | 79.000 | 0.186 | 0.430 | 14.681 | 0.163 |
| 2024 | 79.000 | 0.000 | 0.392 | 0.023 | 0.150 |
| 2025 | 51.000 | -0.098 | 0.314 | -5.012 | 0.204 |

R por fold OOS:
| test_start | n | sum_r |
|---|---|---|
| 2022-01-01 | 22.00 | -1.85 |
| 2022-04-01 | 17.00 | -5.59 |
| 2022-10-01 | 19.00 | 2.24 |
| 2023-01-01 | 18.00 | 10.28 |
| 2023-04-01 | 20.00 | 1.32 |
| 2023-07-01 | 23.00 | -0.25 |
| 2023-10-01 | 18.00 | 3.34 |
| 2024-01-01 | 24.00 | -2.53 |
| 2024-04-01 | 17.00 | 2.50 |
| 2024-07-01 | 21.00 | 1.74 |
| 2024-10-01 | 17.00 | -1.69 |
| 2025-01-01 | 26.00 | 6.00 |
| 2025-04-01 | 25.00 | -11.01 |

Viabilidad de capital (aparte): SL mediano 11.9 USD → 0,01 lotes arriesgan ≈ 11.9 USD; para un riesgo del 0,5 % haría falta ≈ 2,371 USD de capital.

## mean_reversion

| criterio | cumple | dato |
|---|---|---|
| 1 validable (≥ 4 folds) | ✅ | 15 folds |
| 2 ≥ 150 operaciones | ❌ | n=48 |
| 3 IC95 bloques semanales > 0 | ❌ | [-0.374, 0.247] |
| 4 p vs dirección aleatoria < 0.0125 | ❌ | p=0.713 |
| 5 expectativa > 0 con costes C | ❌ | C: nan R |
| 6 ≥ 60% folds y ≥ 3/5 años positivos | ❌ | folds+ 0%, años+ 0/1 |
| 7 dirección invertida < 0 | ✅ | -0.014 R |
| 8 reproducible (mismo hash en 2 ejecuciones) | ✅ | 1d96213d74d7c3f5 |

OOS por año:
| year | n | expectancy_r | win_rate | total_r | sem_r |
|---|---|---|---|---|---|
| 2022 | 48.000 | -0.113 | 0.396 | -5.422 | 0.136 |

R por fold OOS:
| test_start | n | sum_r |
|---|---|---|
| 2022-10-01 | 48.00 | -5.42 |

Viabilidad de capital (aparte): SL mediano 8.8 USD → 0,01 lotes arriesgan ≈ 8.8 USD; para un riesgo del 0,5 % haría falta ≈ 1,759 USD de capital.

## Las 22 configuraciones en todo el periodo (descriptivo, B; NO se usa para elegir)
Con 22 configuraciones el máximo está sesgado al alza por azar. Con expectativa > 0: 11 de 22.
| config | n | exp_R |
|---|---|---|
| trend_donchian {'n': 96, 'sl_atr': 3.0} | 298.0000 | 0.0757 |
| pullback {'sl_atr': 1.5, 'tp_r': 2.5} | 445.0000 | 0.0675 |
| trend_donchian {'n': 96, 'sl_atr': 2.0} | 345.0000 | 0.0627 |
| trend_donchian {'n': 24, 'sl_atr': 3.0} | 486.0000 | 0.0616 |
| pullback {'sl_atr': 2.5, 'tp_r': 1.5} | 379.0000 | 0.0545 |
| pullback {'sl_atr': 2.5, 'tp_r': 2.5} | 374.0000 | 0.0486 |
| momentum_tsmom {'lookback_h': 72, 'hold_h': 48} | 684.0000 | 0.0414 |
| trend_donchian {'n': 24, 'sl_atr': 2.0} | 592.0000 | 0.0279 |
| momentum_tsmom {'lookback_h': 168, 'hold_h': 24} | 823.0000 | 0.0175 |
| momentum_tsmom {'lookback_h': 72, 'hold_h': 24} | 825.0000 | 0.0118 |
| momentum_tsmom {'lookback_h': 24, 'hold_h': 48} | 689.0000 | 0.0021 |
| pullback {'sl_atr': 1.5, 'tp_r': 1.5} | 463.0000 | -0.0028 |
| trend_donchian {'n': 48, 'sl_atr': 3.0} | 416.0000 | -0.0059 |
| trend_donchian {'n': 48, 'sl_atr': 2.0} | 480.0000 | -0.0150 |
| momentum_tsmom {'lookback_h': 24, 'hold_h': 24} | 828.0000 | -0.0167 |
| momentum_tsmom {'lookback_h': 168, 'hold_h': 48} | 696.0000 | -0.0222 |
| mean_reversion {'z': 3.0, 'sl_atr': 3.0} | 888.0000 | -0.0588 |
| mean_reversion {'z': 2.0, 'sl_atr': 3.0} | 2369.0000 | -0.0679 |
| mean_reversion {'z': 2.5, 'sl_atr': 3.0} | 1497.0000 | -0.0837 |
| mean_reversion {'z': 3.0, 'sl_atr': 2.0} | 1058.0000 | -0.0860 |
| mean_reversion {'z': 2.5, 'sl_atr': 2.0} | 1871.0000 | -0.1001 |
| mean_reversion {'z': 2.0, 'sl_atr': 2.0} | 3028.0000 | -0.1039 |

## Diagnóstico POSTERIOR (post-hoc, 2026-11-15; no cambia el veredicto ni se usa para elegir)
Hecho tras ver los resultados, solo para entender el caso más cercano (`trend_donchian`, 159 operaciones, +0,24 R, IC95 inferior −0,02, p = 0,016):
- **Todo el beneficio viene de los largos**: 92 largos = +58,4 R (+0,63 R de media); 67 cortos = −19,9 R (−0,30 R de media). Los cortos pierden en los tres años con operaciones.
- **Concentración temporal**: 2025 aporta +37,0 R de los +38,5 R totales; 2022 es negativo; 2021 y 2023 no tuvieron operaciones (el walk-forward se abstuvo).
- **Concentración en pocas operaciones**: las 5 mejores suman el 71 % del R total; sin ellas la expectativa baja a +0,07 R.
- Lectura: es compatible con la **tendencia alcista del oro en 2024-2025** (exposición larga) más que con una señal con ventaja propia. El benchmark de «dirección aleatoria» favorece a una señal con sesgo largo en un mercado alcista; hace falta además un control **«siempre largo con las mismas señales/horas»**.
- Los criterios 3, 4 y 6 no se cumplen y no se relajan. **Ninguna conclusión de ejecución.** Un seguimiento exigiría una hipótesis nueva y preregistrada (p. ej. tendencia con control de deriva) sobre datos distintos; el periodo reservado solo lo puede abrir el usuario, una vez.
