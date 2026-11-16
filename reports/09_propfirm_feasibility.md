# Estudio 9 — Viabilidad frente a un challenge de prop firm (simulación)

> Entradas: operaciones OOS de los estudios 7 y 8 (M1 del bróker, costes B incluidos en R). Reglas: `config/propfirm_ftmo_2step.yaml` (leídas el 2026-11-15; **lo no verificado está listado en el fichero**). Cuenta simulada 10,000, cuota 89 €, riesgo fijo por operación sobre el capital inicial. Incertidumbre: bootstrap por semanas (100 re-muestreos × 200 trayectorias; entre corchetes percentiles 5–95 %). **Control nulo**: mismas semanas con la expectativa neta desplazada a 0.

## Datos de entrada
| estrategia | n | R medio | R desv | MAE medio (R) | semanas | op/semana |
|---|---|---|---|---|---|---|
| ORB (estudio 7) | 222.000 | -0.113 | 1.078 | 0.845 | 117.000 | 1.897 |
| tendencia Donchian | 159.000 | 0.242 | 1.760 | 0.822 | 195.000 | 0.815 |
| pullback | 267.000 | 0.017 | 1.367 | 0.781 | 183.000 | 1.459 |
| momentum | 578.000 | -0.048 | 1.215 | 0.752 | 196.000 | 2.949 |

## Evaluación PRINCIPAL: riesgo operativo del proyecto (0,5 % por operación; también 0,25 %)
Horizonte 104 semanas por fase (FTMO no tiene límite de tiempo).
| estrategia | riesgo %/op | P(Challenge) | P(Challenge+Verif.) | P(suspender) | sin resolver 104 sem | NULO P(Ch.+Ver.) | EV € (mediana) | EV nulo € |
|---|---|---|---|---|---|---|---|---|
| ORB (estudio 7) | 0.25 | 0.0% [0.0%–4.1%] | 0.0% [0.0%–1.5%] | 11.2% [0.0%–66.2%] | 88.8% [33.8%–99.5%] | 0.0% [0.0%–1.0%] | -89.00 | -89.00 |
| ORB (estudio 7) | 0.50 | 1.0% [0.0%–14.1%] | 0.0% [0.0%–5.5%] | 69.8% [28.0%–97.0%] | 30.2% [3.0%–66.0%] | 8.5% [4.0%–13.1%] | -89.00 | -79.45 |
| tendencia Donchian | 0.25 | 13.5% [0.5%–54.7%] | 9.2% [0.0%–50.6%] | 0.0% [0.0%–0.5%] | 90.8% [49.4%–99.5%] | 0.0% [0.0%–1.0%] | -77.73 | -89.00 |
| tendencia Donchian | 0.50 | 58.7% [18.4%–89.0%] | 49.2% [9.0%–87.5%] | 2.5% [0.0%–21.0%] | 49.2% [12.0%–75.5%] | 9.0% [4.0%–14.5%] | 11.09 | -77.07 |
| pullback | 0.25 | 2.0% [0.0%–27.0%] | 0.8% [0.0%–19.1%] | 0.5% [0.0%–9.5%] | 96.8% [80.9%–99.5%] | 0.0% [0.0%–1.0%] | -88.47 | -89.00 |
| pullback | 0.50 | 26.8% [3.4%–73.1%] | 17.5% [0.5%–65.3%] | 17.0% [2.5%–73.7%] | 59.5% [21.4%–71.5%] | 9.8% [6.0%–15.5%] | -66.14 | -75.59 |
| momentum | 0.25 | 0.5% [0.0%–7.6%] | 0.0% [0.0%–3.5%] | 15.2% [0.5%–68.1%] | 84.7% [31.9%–96.5%] | 1.0% [0.0%–2.5%] | -89.00 | -88.25 |
| momentum | 0.50 | 10.8% [0.5%–50.0%] | 3.5% [0.0%–35.2%] | 59.5% [21.9%–90.2%] | 33.0% [9.8%–47.5%] | 15.0% [10.5%–20.0%] | -85.47 | -67.24 |

## Sensibilidad separada: 1 % por operación (techo duro del proyecto; NO es la configuración operativa)
Solo para ver cuánto cambia el resultado con más riesgo; no se usa para decidir nada.
| estrategia | riesgo %/op | P(Challenge) | P(Challenge+Verif.) | P(suspender) | sin resolver 104 sem | NULO P(Ch.+Ver.) | EV € (mediana) | EV nulo € |
|---|---|---|---|---|---|---|---|---|
| ORB (estudio 7) | 1.00 | 12.0% [1.5%–45.7%] | 3.8% [0.0%–31.0%] | 92.0% [61.9%–100.0%] | 3.5% [0.0%–11.0%] | 27.5% [21.0%–34.5%] | -85.18 | -29.06 |
| tendencia Donchian | 1.00 | 79.2% [42.4%–96.5%] | 67.0% [26.4%–94.5%] | 24.0% [4.5%–61.0%] | 6.0% [1.0%–16.0%] | 25.5% [20.5%–31.0%] | 155.27 | -34.38 |
| pullback | 1.00 | 52.8% [23.0%–86.5%] | 36.0% [8.0%–78.0%] | 55.2% [19.5%–86.6%] | 5.0% [1.5%–10.5%] | 28.5% [24.0%–34.0%] | -4.36 | -24.18 |
| momentum | 1.00 | 30.0% [9.9%–62.0%] | 15.0% [2.5%–44.7%] | 83.5% [55.3%–97.5%] | 1.0% [0.0%–3.0%] | 30.0% [25.0%–35.0%] | -58.39 | -9.90 |

## Reproducción histórica exacta (fase 1, riesgo 0,5 %, equity flotante M1)
| estrategia | inicios (cada 4 sem.) | PASSED | FAILED | sin resolver |
|---|---|---|---|---|
| ORB (estudio 7) | 28 | 0 | 21 | 7 |
| tendencia Donchian | 48 | 43 | 0 | 5 |
| pullback | 45 | 10 | 0 | 35 |
| momentum | 48 | 0 | 20 | 28 |

**Ninguna de estas probabilidades valida una estrategia.** En particular la tendencia Donchian NO queda validada por aprobar el challenge simulado: su ventaja no es estadísticamente significativa (estudio 8) y proviene de operaciones largas en un mercado alcista; la tasa de aprobación hereda esa incertidumbre. Lectura: si P(Challenge+Verif.) de una estrategia **no supera claramente** la del control nulo, el resultado de un challenge sería suerte; el valor esperado es la cuota perdida menos/más los pagos. Una estrategia sin ventaja demostrada **no justifica pagar**.