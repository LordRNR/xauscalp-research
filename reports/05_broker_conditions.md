# Estudio 5 — Condiciones reales de la cuenta MT5 frente a los supuestos de la ORB

Fuente: `xau_feasibility.csv` generado 2026.11.12 23:33:24 GMT en **MetaQuotes-Demo** (MetaQuotes Ltd.). MetaQuotes-Demo es el servidor de demostración del fabricante de MT5, **no un bróker que ejecute órdenes reales**: sus spreads y su apalancamiento no prueban nada sobre el coste real de operar.

## 1. Supuesto a supuesto
| area | config_value | broker_value | status | note |
|---|---|---|---|---|
| account mode | DEMO required | ACCOUNT_TRADE_MODE_DEMO | MATCH | the EA refuses non-demo accounts |
| contract_size (oz/lot) | 100 | 100 | MATCH |  |
| volume_min (lots) | 0.01 | 0.01 | MATCH |  |
| volume_step (lots) | 0.01 | 0.01 | MATCH |  |
| volume_max (lots) | 50 | 100 | CONFIG_MORE_CONSERVATIVE | cap only; risk % decides the size |
| account currency | EUR | EUR | MATCH | P&L converted with OrderCalcProfit |
| leverage | 20 | 100 | CONFIG_MORE_CONSERVATIVE | config keeps the ESMA retail cap for gold (20:1) for planning a real EU account; margin at the demo's leverage is lower |
| margin mode | 1 position (enforced by us) | ACCOUNT_MARGIN_MODE_RETAIL_HEDGING | INFO | hedging allows several positions: the risk guard counts ANY position on the symbol |
| stops/freeze level (points) | checked by the EA | 0/0 | MATCH | 0 = no minimum distance today (can change; checked live) |
| max_spread_usd filter | 0.6 | bar p50 0.18 / p90 0.33 / p99 0.42 | INFO | bar spread is usually the bar MINIMUM (optimistic); confirm with ticks |
| research cost model | Dukascopy spread + 0.15 | bar p50 0.18 | UNKNOWN | not comparable yet: different dates and bar-min spreads. Calibrate with broker M1/tick exports on the SAME pre-holdout dates. A cheaper demo is never adopted as the cost model |
| commission (per lot, round turn) | 0 | not exposed by SymbolInfo | UNKNOWN | read DEAL_COMMISSION of a real broker's demo fill before Stage C |
| slippage | risk 0.1 / backtest 0.05 | unknown (no fills yet) | UNKNOWN | measure in DEMO (Stage C) |
| swap (points/lot/night) | not modelled (intraday) | long -12.6 / short -4.6 | INFO | ORB exits <= 150 min after the session open, far from the rollover |
| server - GMT now (s) | never assumed | 7200 | INFO | one moment only; historical rule must be verified (study 04) |
| OrderCheck | must pass before Stage C | 10027 AutoTrading disabled by client | INFO | 10027 = AutoTrading disabled in the terminal (deliberate) |

Estados: MATCH = coincide · CONFIG_MORE_CONSERVATIVE = la configuración es más prudente (se mantiene) · BROKER_WORSE = el bróker es peor que lo supuesto (requiere acción) · UNKNOWN = no medible todavía · INFO = dato a tener en cuenta.

**Cambios en `config/default.yaml`: ninguno numérico.** Los valores de símbolo coinciden; apalancamiento y volumen máximo de la configuración son más prudentes; comisión y deslizamiento siguen sin medir; el modelo de costes no se abarata con datos de una demo.

## 2. ¿Con qué capital se podrían dimensionar las rupturas ORB?
Rupturas técnicas (antes de filtros de coste) del tramo reciente de investigación (2025-09-03 → 2025-10-31, oro mediano 3,940 $; hoy 3,877 $). Distancia del SL en $ por onza; 0,01 lotes pierden **0.9 EUR por cada 1 $** de recorrido (OrderCalcProfit del bróker).
| sl_atr | count | 25% | 50% | 75% | 90% | loss_0.01lot_p50_EUR | equity_for_0.5pct_p50_EUR |
|---|---|---|---|---|---|---|---|
| 1.0 | 138 | 2.85 | 3.68 | 5.74 | 7.11 | 3.31 | 680.16 |
| 1.5 | 138 | 4.28 | 5.52 | 8.61 | 10.67 | 4.97 | 1011.24 |
| 2.0 | 138 | 5.71 | 7.36 | 11.48 | 14.23 | 6.62 | 1342.32 |

Gestor de riesgo **sin cambios** (riesgo 0.5 %, margen máx. 30 % del libre, slippage 0.1 $), especificación real del símbolo, tipo USD→EUR = 0.9047 y spread fijado en el p90 del bróker (0.33 $) para aislar la pregunta de capital.

### cuenta demo 1:100 — SL = 1×ATR(M5)
| equity_EUR | breakouts | sizeable | pct | MIN_VOLUME_EXCEEDS_RISK | INSUFFICIENT_MARGIN | other |
|---|---|---|---|---|---|---|
| 20 | 138 | 0 | 0 | 138 | 0 | 0 |
| 500 | 138 | 25 | 18 | 113 | 0 | 0 |
| 1000 | 138 | 97 | 70 | 41 | 0 | 0 |
| 2000 | 138 | 133 | 96 | 5 | 0 | 0 |
| 5000 | 138 | 138 | 100 | 0 | 0 | 0 |

### cuenta demo 1:100 — SL = 1.5×ATR(M5)
| equity_EUR | breakouts | sizeable | pct | MIN_VOLUME_EXCEEDS_RISK | INSUFFICIENT_MARGIN | other |
|---|---|---|---|---|---|---|
| 20 | 138 | 0 | 0 | 138 | 0 | 0 |
| 500 | 138 | 0 | 0 | 138 | 0 | 0 |
| 1000 | 138 | 67 | 49 | 71 | 0 | 0 |
| 2000 | 138 | 124 | 90 | 14 | 0 | 0 |
| 5000 | 138 | 138 | 100 | 0 | 0 | 0 |

### cuenta demo 1:100 — SL = 2×ATR(M5)
| equity_EUR | breakouts | sizeable | pct | MIN_VOLUME_EXCEEDS_RISK | INSUFFICIENT_MARGIN | other |
|---|---|---|---|---|---|---|
| 20 | 138 | 0 | 0 | 138 | 0 | 0 |
| 500 | 138 | 0 | 0 | 138 | 0 | 0 |
| 1000 | 138 | 30 | 22 | 108 | 0 | 0 |
| 2000 | 138 | 97 | 70 | 41 | 0 | 0 |
| 5000 | 138 | 138 | 100 | 0 | 0 | 0 |

### cuenta real UE (ESMA) 1:20 — SL = 1×ATR(M5)
| equity_EUR | breakouts | sizeable | pct | MIN_VOLUME_EXCEEDS_RISK | INSUFFICIENT_MARGIN | other |
|---|---|---|---|---|---|---|
| 20 | 138 | 0 | 0 | 138 | 0 | 0 |
| 500 | 138 | 0 | 0 | 113 | 25 | 0 |
| 1000 | 138 | 72 | 52 | 41 | 25 | 0 |
| 2000 | 138 | 108 | 78 | 5 | 25 | 0 |
| 5000 | 138 | 106 | 77 | 0 | 32 | 0 |

### cuenta real UE (ESMA) 1:20 — SL = 1.5×ATR(M5)
| equity_EUR | breakouts | sizeable | pct | MIN_VOLUME_EXCEEDS_RISK | INSUFFICIENT_MARGIN | other |
|---|---|---|---|---|---|---|
| 20 | 138 | 0 | 0 | 138 | 0 | 0 |
| 500 | 138 | 0 | 0 | 138 | 0 | 0 |
| 1000 | 138 | 67 | 49 | 71 | 0 | 0 |
| 2000 | 138 | 124 | 90 | 14 | 0 | 0 |
| 5000 | 138 | 138 | 100 | 0 | 0 | 0 |

### cuenta real UE (ESMA) 1:20 — SL = 2×ATR(M5)
| equity_EUR | breakouts | sizeable | pct | MIN_VOLUME_EXCEEDS_RISK | INSUFFICIENT_MARGIN | other |
|---|---|---|---|---|---|---|
| 20 | 138 | 0 | 0 | 138 | 0 | 0 |
| 500 | 138 | 0 | 0 | 138 | 0 | 0 |
| 1000 | 138 | 30 | 22 | 108 | 0 | 0 |
| 2000 | 138 | 97 | 70 | 41 | 0 | 0 |
| 5000 | 138 | 138 | 100 | 0 | 0 | 0 |

## 3. *What-if* de filtros de coste con los spreads de este servidor (NO adoptado)
Filtros sin cambios: spread ≤ 0.6 $ y (spread + 2×0.05) / SL ≤ 0.20. Solo ilustra qué filtro dejaría de ser el cuello de botella **si** un bróker real ofreciera estos spreads en esas mismas fechas. Fechas distintas y spreads mínimos de barra: no es evidencia.
| spread usado | spread_med | cost_frac_med | pasan spread | pasan ambos filtros | breakouts |
|---|---|---|---|---|---|
| Dukascopy + extra (modelo actual) | 0.74 | 0.15 | 24 | 20 | 414 |
| bróker p50 | 0.18 | 0.05 | 414 | 414 | 414 |
| bróker p90 | 0.33 | 0.08 | 414 | 410 | 414 |
| bróker p99 | 0.42 | 0.09 | 414 | 395 | 414 |

## 4. Spread medio por hora del servidor (muestra reciente del bróker)
Desfase actual servidor−GMT: +2 h (solo para la fecha del informe). Con ese desfase, la apertura de Londres (08:00 Londres) cae a las 10:00 servidor y COMEX (08:20 Nueva York) a las 15:20 servidor en horario de invierno.
| hora servidor | spread_mean |
|---|---|
| 0 | 0.21 |
| 1 | 0.31 |
| 2 | 0.27 |
| 3 | 0.23 |
| 4 | 0.22 |
| 5 | 0.22 |
| 6 | 0.21 |
| 7 | 0.21 |
| 8 | 0.21 |
| 9 | 0.20 |
| 10 | 0.19 |
| 11 | 0.19 |
| 12 | 0.19 |
| 13 | 0.19 |
| 14 | 0.19 |
| 15 | 0.17 |
| 16 | 0.17 |
| 17 | 0.17 |
| 18 | 0.17 |
| 19 | 0.18 |
| 20 | 0.18 |
| 21 | 0.17 |
| 22 | 0.20 |

## Conclusiones
- La especificación del símbolo coincide con la configuración: el sizing de investigación ya usaba contrato 100 oz y mínimo 0,01.
- **20 € no alcanzan ni el margen de 0,01 lotes** (35.08 EUR a 1:100; ×5 a 1:20).
- La capacidad de dimensionar depende del SL en dólares: ver tablas del apartado 2.
- Ninguna cifra de este estudio es evidencia de rentabilidad.
