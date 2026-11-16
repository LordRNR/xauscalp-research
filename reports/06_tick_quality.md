# Estudio 6 — Ticks del bróker: cobertura, completitud y spreads reales

Fuente: `XAUUSD_ticks_1759276800_1761955200.csv` (servidor MetaQuotes-Demo, build 6320), regla horaria `base_dst:120:Europe/London` (verificada en el estudio 4). Ventana leída: **2025-09-30 22:00 → 2025-10-31 20:56 UTC**, toda **anterior al periodo reservado** (2025-11-01): los lectores se detienen en el límite y no leen más filas.

## Tres cosas distintas
|  | ¿Cumplido? |
|---|---|
| Ticks exportados | **Sí**: 2,622,575 ticks exportados |
| Histórico suficientemente completo (coste/spread) | **Sí, para este mes** |
| Estrategia validada y rentable | **No**: nada de este informe valida una estrategia |

## 1. Integridad
|  | valor |
|---|---|
| n | 2622575 |
| non_finite | 0 |
| non_positive | 0 |
| crossed | 0 |
| dropped | 0 |
| zero_spread | 0 |
| same_timestamp_pairs | 435 |
| monotonic | True |
| consecutive_identical_quotes | 1319 |

Flags observados (`MqlTick.flags`): 1158: 2,529,801, 1154: 34,998, 1028: 33,803, 134: 22,059, 4: 1,075, 130: 839. La documentación oficial solo describe los bits BID/ASK/LAST/VOLUME/BUY/SELL; los bits 128 y 1024 aparecen en casi todos los ticks y **su significado no está verificado** (no afectan a la validez de bid/ask: todas las filas tienen ambos).

## 2. Cobertura por día
**Por día del servidor** (así lo cuenta el script de exportación): 8 días sin ticks: 04-Oct (Sat), 05-Oct (Sun), 11-Oct (Sat), 12-Oct (Sun), 18-Oct (Sat), 19-Oct (Sun), 25-Oct (Sat), 26-Oct (Sun). 
**Por día UTC**: 32 días; laborables 24, todos con ticks (sí); sábados con ticks: 0; domingos con ticks: 4 (es la apertura semanal del domingo por la tarde UTC). Días parciales en los bordes de la ventana: 2025-09-30 (5,782 ticks). 
Ticks por día laborable completo: mín 85,489 · mediana 114,575 · máx 132,930.


## 3. Silencios entre ticks
| category | count |
|---|---|
| 30 s - 5 min | 54 |
| 5 - 30 min (silence) | 4 |
| 30 min - 6 h (daily break) | 18 |
| > 6 h (weekly close) | 4 |

Silencios > 5 min en horario de mercado y si las velas del servidor también faltan:
|  | start_utc | end_utc | seconds | server_bars_inside | toca ventana ORB |
|---|---|---|---|---|---|
| 0 | 2025-10-10 12:55:23.395+00:00 | 2025-10-10 13:12:50.045+00:00 | 1047 | 0 | True |
| 1 | 2025-10-13 18:45:00.144+00:00 | 2025-10-13 18:52:35.711+00:00 | 456 | 0 | False |
| 2 | 2025-10-23 18:58:30.751+00:00 | 2025-10-23 19:07:09.355+00:00 | 519 | 0 | False |
| 3 | 2025-10-27 06:37:21.693+00:00 | 2025-10-27 06:44:59.145+00:00 | 457 | 0 | False |

## 4. ¿Reproducen los ticks las velas M1 del propio servidor?
Es la prueba de completitud que importa: si el servidor construyó sus velas con más ticks de los exportados, el histórico exportado está incompleto. `tick_volume` cuenta los ticks que cambian el **bid** (las velas son de bid): los ticks que solo cambian el ask (flag sin bit BID) explican la diferencia entre el total exportado y `tick_volume`, por eso la comparación válida es `bidtick_*`.
|  | valor |
|---|---|
| bars_in_window | 31562 |
| bars_with_ticks | 31562 |
| bars_without_ticks | 0 |
| minutes_with_ticks_without_bar | 110 |
| ohlc_open_equal | 1.000 |
| ohlc_open_maxdiff | 0.000 |
| ohlc_high_equal | 1.000 |
| ohlc_high_maxdiff | 0.000 |
| ohlc_low_equal | 1.000 |
| ohlc_low_maxdiff | 0.000 |
| ohlc_close_equal | 1.000 |
| ohlc_close_maxdiff | 0.180 |
| tickcount_equal_share | 0.473 |
| tickcount_ratio_q | {0.01: 1.0, 0.05: 1.0, 0.5: 1.0099, 0.95: 1.0508, 0.99: 1.0941} |
| tickcount_total_ratio | 1.013 |
| bidtick_equals_tickvolume_share | 1.000 |
| bidtick_total_ratio | 1.000 |
| bar_spread_equals | {'first_tick': 0.545, 'last_tick': 0.5536, 'min_in_minute': 0.9998, 'max_in_minute': 0.0546, 'time_weighted_mean': 0.418} |
| bar_spread_vs_min_signed_q | {0.05: -0.0, 0.5: 0.0, 0.95: 0.0} |

### Velas que faltan en la exportación M1 (hay ticks, no hay vela)
|  | start_utc | end_utc | minutes | toca ventana ORB |
|---|---|---|---|---|
| 0 | 2025-10-23 17:09:00+00:00 | 2025-10-23 18:58:00+00:00 | 110 | False |

Es un agujero de la **exportación M1**, no de los ticks. Si toca una ventana ORB, Python/EA trabajarían con velas incompletas ese día (usar la fuente de ticks).

## 5. Criterios de completitud (decisión explícita)
> Los criterios 3 y 4 se **refinaron tras ver la primera ejecución**: la versión inicial no distinguía la pausa diaria programada ni los cortes del servidor de una pérdida de la exportación. Son criterios de integridad de datos, no de estrategia.
|  | cumple |
|---|---|
| 1. Ticks válidos (sin cruzados/no finitos) y en orden | sí |
| 2. Todos los días laborables tienen ticks | sí |
| 3. Pausas coherentes con el calendario (18 diarias, 4 semanales) | sí |
| 4. Todo silencio > 5 min está también vacío en las velas del servidor (corte del servidor, no pérdida de la exportación) | sí |
| 5. Toda vela M1 del servidor tiene ticks | sí |
| 6. OHLC (bid) de los ticks = OHLC de las velas del servidor (≥ 99 %) | sí |
| 7. Ticks que cambian el bid = tick_volume del servidor (≥ 99,9 % de las velas) | sí |

**Veredicto: COMPLETO para este mes** — con 4 cortes de cotización del servidor (41 min en total) y 110 minutos sin vela en la exportación M1.

## 6. Spread real (ask − bid) de los ticks
Ponderado por tiempo (cada cotización pesa lo que duró, máx. 60 s) frente a ponderado por tick (los momentos de mucha actividad pesan más).
|  | ponderado por tiempo | ponderado por tick |
|---|---|---|
| p50 | 0.170 | 0.170 |
| p75 | 0.170 | 0.170 |
| p90 | 0.180 | 0.190 |
| p95 | 0.210 | 0.210 |
| p99 | 0.300 | 0.350 |

Media por tiempo 0.170 $ · máximo 2.30 $ · tiempo con spread > 0.3 $: 1.02 % · 0.6 $: 0.09 % · 1 $: 0.01 %.

Por hora UTC:
| hour_utc | ticks | tw_mean | p50 | p90 | p99 | time>0.6 |
|---|---|---|---|---|---|---|
| 0 | 116269 | 0.167 | 0.160 | 0.180 | 0.260 | 0.001 |
| 1 | 125236 | 0.167 | 0.160 | 0.180 | 0.260 | 0.000 |
| 2 | 109802 | 0.168 | 0.170 | 0.180 | 0.240 | 0.000 |
| 3 | 103697 | 0.168 | 0.170 | 0.180 | 0.240 | 0.000 |
| 4 | 98160 | 0.169 | 0.170 | 0.180 | 0.240 | 0.001 |
| 5 | 111358 | 0.168 | 0.170 | 0.190 | 0.250 | 0.001 |
| 6 | 115686 | 0.167 | 0.170 | 0.180 | 0.240 | 0.000 |
| 7 | 117450 | 0.169 | 0.170 | 0.180 | 0.250 | 0.001 |
| 8 | 116980 | 0.169 | 0.170 | 0.180 | 0.280 | 0.001 |
| 9 | 113023 | 0.169 | 0.170 | 0.180 | 0.270 | 0.001 |
| 10 | 109465 | 0.167 | 0.170 | 0.180 | 0.240 | 0.001 |
| 11 | 111773 | 0.168 | 0.170 | 0.180 | 0.250 | 0.000 |
| 12 | 124033 | 0.171 | 0.170 | 0.190 | 0.340 | 0.001 |
| 13 | 132366 | 0.173 | 0.170 | 0.200 | 0.390 | 0.002 |
| 14 | 134397 | 0.174 | 0.170 | 0.200 | 0.390 | 0.001 |
| 15 | 127811 | 0.169 | 0.170 | 0.180 | 0.260 | 0.000 |
| 16 | 123219 | 0.169 | 0.170 | 0.180 | 0.240 | 0.000 |
| 17 | 118282 | 0.167 | 0.170 | 0.180 | 0.230 | 0.000 |
| 18 | 112266 | 0.166 | 0.160 | 0.180 | 0.230 | 0.001 |
| 19 | 118116 | 0.166 | 0.160 | 0.180 | 0.230 | 0.000 |
| 20 | 82500 | 0.187 | 0.170 | 0.200 | 0.500 | 0.000 |
| 22 | 99741 | 0.178 | 0.170 | 0.190 | 0.600 | 0.008 |
| 23 | 100945 | 0.165 | 0.160 | 0.170 | 0.220 | 0.000 |

## 7. Spread en las ventanas de la ORB
Ventana = apertura → +75 min (rango de apertura de 15 min + 60 min de entrada).
| session | ticks | tw_p50 | tw_p90 | tw_p99 | max | time>0.60 |
|---|---|---|---|---|---|---|
| london | 150112.000 | 0.170 | 0.180 | 0.300 | 1.800 | 0.001 |
| newyork | 159244.000 | 0.170 | 0.190 | 0.350 | 1.760 | 0.001 |

Primer tick de cada minuto relativo a la apertura (mediana/p90 entre días):
|  | n | p50 | p90 | max |
|---|---|---|---|---|
| ('london', -10) | 23 | 0.160 | 0.180 | 0.200 |
| ('london', 0) | 23 | 0.170 | 0.208 | 0.230 |
| ('london', 5) | 23 | 0.160 | 0.180 | 0.200 |
| ('london', 10) | 23 | 0.170 | 0.196 | 0.220 |
| ('london', 15) | 23 | 0.160 | 0.200 | 0.590 |
| ('london', 30) | 23 | 0.170 | 0.204 | 0.450 |
| ('london', 45) | 23 | 0.170 | 0.178 | 0.220 |
| ('london', 60) | 23 | 0.160 | 0.204 | 0.320 |
| ('london', 75) | 23 | 0.170 | 0.218 | 0.380 |
| ('newyork', -10) | 23 | 0.170 | 0.180 | 0.210 |
| ('newyork', 0) | 23 | 0.180 | 0.280 | 0.350 |
| ('newyork', 5) | 23 | 0.170 | 0.180 | 0.210 |
| ('newyork', 10) | 23 | 0.170 | 0.474 | 0.520 |
| ('newyork', 15) | 23 | 0.170 | 0.180 | 0.210 |
| ('newyork', 30) | 23 | 0.170 | 0.210 | 0.550 |
| ('newyork', 45) | 22 | 0.170 | 0.219 | 0.310 |
| ('newyork', 60) | 23 | 0.170 | 0.180 | 0.390 |
| ('newyork', 75) | 23 | 0.170 | 0.220 | 0.340 |

## 8. Bróker vs. Dukascopy (mismos minutos)
|  | p50 | p90 | p99 |
|---|---|---|---|
| Dukascopy ask_c-bid_c | 0.670 | 0.910 | 1.407 |
| Dukascopy + 0.15 (modelo) | 0.820 | 1.060 | 1.557 |
| bróker: último tick del minuto | 0.170 | 0.180 | 0.310 |
| bróker: media ponderada en el tiempo | 0.170 | 0.186 | 0.243 |

|  | valor |
|---|---|
| minutos comparados | 28794 |
| mediana (bróker − Dukascopy) $ | 0.252 |
| |dif| p95 $ | 0.585 |
| |dif| p99 $ | 0.822 |
| % minutos con |dif| ≤ 0,30 $ | 62.131 |
| correlación de retornos 1 min | 0.992 |

## 9. Efecto sobre los filtros de la ORB (mismas rupturas, solo cambia el spread)
Rupturas ORB en las velas del bróker dentro de la ventana de ticks (todas las combinaciones del grid, **sin filtros**, solo las que tienen además dato de Dukascopy en ese minuto: su octubre está incompleto); filtros sin cambios: spread ≤ 0.6 $ y (spread + 2×0.05) / SL ≤ 0.20. Con OR 15 / SL 1,5×ATR hay **41** rupturas: lejos de las ≥ 200 operaciones que exige la fase 3.
| SL×ATR | rupturas | Dukascopy + extra (supuesto actual) | bróker: spread de la vela (lo que ve Python) | bróker: primer tick de la vela siguiente (lo que ve el EA) |
|---|---|---|---|---|
| 1.0 | 80 | 4 (5 %) | 80 (100 %) | 80 (100 %) |
| 1.5 | 80 | 5 (6 %) | 80 (100 %) | 80 (100 %) |
| 2.0 | 80 | 5 (6 %) | 80 (100 %) | 80 (100 %) |

|  | rechaza spread | rechaza coste/SL | pasan |
|---|---|---|---|
| Dukascopy + extra (supuesto actual) | 225 | 1 | 14 |
| bróker: spread de la vela (lo que ve Python) | 0 | 0 | 240 |
| bróker: primer tick de la vela siguiente (lo que ve el EA) | 0 | 0 | 240 |

El spread de la vela (Python) coincide con el del primer tick de la vela siguiente (EA) en el **34 %** de las rupturas; diferencia (tick − vela) p5/p50/p95 = {0.05: -0.0, 0.5: 0.01, 0.95: 0.19}.

## Qué NO se puede concluir
- **Un solo mes** (octubre de 2025) y un solo régimen (oro con subida fuerte): sirve para calibrar costes, no para validar nada.
- Es el feed de **MetaQuotes-Demo**, que no ejecuta órdenes reales: que su spread sea bajo y casi constante **no** implica que un bróker real lo ofrezca. Antes de cambiar `extra_spread_usd` o `max_spread_usd` hace falta el mismo análisis con la demo del bróker elegido y una comisión conocida.
- Ninguna cifra de este informe es evidencia de rentabilidad.
