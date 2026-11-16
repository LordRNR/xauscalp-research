# Fase 0 — Viabilidad económica y técnica

Fecha: 2026-11-12. Estado: **parcial**. Lo marcado ✅ está verificado en esta sesión;
lo marcado ⏳ depende de ejecutar `mt5/Scripts/XAU_FeasibilityReport.mq5` en tu cuenta demo.

## 1. Veredicto corto

- **Con 20 € no se puede operar XAUUSD con un riesgo razonable** en ningún bróker regulado
  en la UE con lote mínimo 0,01 = 1 onza. No es una cuestión de prudencia excesiva: el
  stop que permitiría un riesgo del 0,5 % (≈ 0,11 $) es **más pequeño que el propio spread**.
- El proyecto sí es viable como **investigación + DEMO** con coste 0 €/mes, y las
  aportaciones periódicas se acumulan sin operar hasta alcanzar el mínimo (§5).
- Ventaja estadística: **desconocida**. Los primeros datos (2021-T1, solo validación del
  pipeline) indican que en scalping de oro los costes son una fracción enorme del
  movimiento: es probable que la respuesta honesta acabe siendo "no hay ventaja
  explotable a esta escala". Descubrirlo en demo es un buen resultado.

## 1b. Actualización 2026-11-12 (auditoría)

- Tu cuenta demo es de **MetaQuotes Ltd** (servidor MetaQuotes-Demo). MetaQuotes desarrolla
  la plataforma; **no es un bróker** con el que operarías con dinero real. Sus condiciones
  (contrato, spread, margen, comisión) sirven para practicar, pero el cálculo definitivo de
  capital mínimo debe repetirse con la demo del bróker regulado que elijas.
- El tipo EURUSD 1,1155 usado abajo es de oct-2026, **periodo reservado** (holdout) de la
  investigación. Solo se usa para planificar capital hoy, nunca para seleccionar
  estrategias. En adelante el cálculo usará `OrderCalcProfit` del propio bróker.
- El estudio de diagnóstico (`reports/03_orb_diagnostics.md`) confirma con la configuración
  de riesgo actual que **ninguna señal sería operable con 23 USD (~20 €) ni con 500 USD**
  (el lote mínimo arriesga más del 0,5 %). Con 1.000 USD se aprobarían 104 de 139 señales
  (75 %); las rechazadas son las de stop más amplio, típicas del oro a ~4.000 $ (ATR M5 ≈ 5 $).
  Son cifras de configuración (contrato 100 oz, mínimo 0,01, 20:1), no del bróker.

## 1c. Condiciones reales de tu demo (informe MT5 del 2026-11-12, estudio 5)
Fuente: `reports/05_broker_conditions.md` (generado desde `data/mt5/xau_feasibility.csv`).
- Cuenta EUR, 1:100, cobertura (*hedging*); XAUUSD 100 oz/lote, mínimo 0,01, paso 0,01;
  stops/freeze level 0; swap −12,6/−4,6 puntos (irrelevante: la ORB cierra en el día).
- **Margen de 0,01 lotes: 35,08 €** a 1:100. Con el apalancamiento ESMA para oro (1:20)
  sería ~175 €. **Con 20 € no se cubre ni el margen de la posición mínima.**
- 0,01 lotes pierden **0,90 € por cada 1 $** de recorrido del oro.
- Stops ORB observados en sep–oct 2025 (SL = 1,5×ATR M5): mediana 5,5 $ → 5,0 € de pérdida
  con 0,01 lotes → con riesgo 0,5 % hacen falta **~1.000 €** para la mitad de las señales.
  Con 1.000 € se podrían dimensionar el 49 % de las rupturas; con 2.000 € el 90 %.
- Spread M1 (mínimos de barra, optimista): mediana 0,18 $, p90 0,33 $, p99 0,42 $. Es
  mucho menor que Dukascopy + 0,15 $ (~0,74 $) que usa la investigación, pero procede de
  una demo, en otras fechas: **no se adopta** (ADR 22). Se calibrará con ticks del bróker
  en fechas anteriores al periodo reservado.
- Comisión: no expuesta por el símbolo; pendiente de una ejecución demo en un bróker real.

## 1d. Spread real medido con ticks (estudio 6, octubre de 2025)
Fuente: `reports/06_tick_quality.md`, 2,6 M de ticks de MetaQuotes-Demo (completos para ese mes).
- Spread real (ponderado por tiempo): **mediana 0,17 $, p99 0,30 $**, máximo 2,30 $; el 0,09 %
  del tiempo supera 0,60 $. Es casi constante: la mediana no cambia en las aperturas de
  Londres ni de COMEX, aunque hay picos puntuales (p90 de 0,47 $ en el minuto +10 de la
  apertura de Nueva York, que coincide con la hora de datos macro de las 8:30; hipótesis
  sin verificar, el calendario de eventos sigue vacío).
- Dukascopy en los mismos minutos: mediana 0,67 $ (0,82 $ con el extra de 0,15 $ del modelo).
  El modelo de investigación es ~5× más pesimista que este feed, y por eso el filtro
  absoluto de 0,60 $ bloquea el 94 % de las rupturas con el modelo y el 0 % con el feed real.
- **No se adopta**: un mes, demo sin ejecución real, sin comisión ni deslizamiento medidos.
  La decisión sobre S1 (límite de spread) espera a la demo de un bróker regulado.
- Los precios también difieren: bid del bróker − bid de Dukascopy = +0,25 $ de mediana, y solo el
  62 % de los minutos coincide en 0,30 $: otro motivo para no mezclar fuentes sin medirlo.

## 2. Spot, CFD y futuros

| | Spot XAUUSD (OTC) | CFD sobre oro (lo que da MT5 retail) | Futuros (COMEX GC/MGC) |
|---|---|---|---|
| Qué es | Compraventa interbancaria de oro, liquidación T+2 | Contrato por diferencias con tu bróker sobre el precio del oro | Contrato estandarizado en bolsa |
| Contraparte | Bancos | **El bróker** | Cámara de compensación |
| Tamaño | Grandes nominales | 1 lote = normalmente 100 oz; mínimo 0,01 = 1 oz ⏳ | GC = 100 oz, MGC = 10 oz |
| Apalancamiento retail UE | — | **máx. 20:1** (ESMA/CNMV, margen 5 %) | margen de bolsa (miles de $) |
| Costes | — | spread (+ comisión en cuentas "raw") + **swap diario** | comisión + tick |
| Protecciones UE | — | cierre por margen al 50 %, saldo negativo protegido | — |

En MT5 con un bróker retail estás operando, casi seguro, un **CFD**. El script lo confirma
con `SYMBOL_TRADE_CALC_MODE` (CFD / CFDLEVERAGE / FOREX) ⏳.

## 3. Números verificados

- ✅ Precio del oro observado en los datos: **3.862 $/oz el 3-oct-2025** (Dukascopy).
- ✅ EURUSD: **1,1155** (cierre 30-oct-2026, Dukascopy).
- ✅ Spread mediano Dukascopy XAUUSD en 2021-T1: 0,38–0,41 $ (a 1.830 $/oz). Un bróker retail
  suele ser igual o peor → el modelo añade 0,15 $ extra + 0,05 $ de slippage por ejecución.
- ✅ El paquete Python `MetaTrader5` (v5.0.6231) solo publica *wheels* `win_amd64`: no corre en macOS.

Con contrato de 100 oz y 0,01 lotes (= 1 oz), con el oro a ~3.900 $:

| Concepto | Valor aproximado |
|---|---|
| Nominal de 0,01 lotes | ≈ 3.900 $ ≈ 3.500 € |
| Margen a 20:1 | ≈ 195 $ ≈ **175 €** |
| P/L por cada 1 $ de movimiento | 1 $ ≈ 0,90 € |
| Riesgo 0,5 % de 20 € | 0,10 € → stop máximo ≈ **0,11 $** sin contar slippage (< spread) |

### Capital mínimo para 0,01 lotes con riesgo del 0,5 %

Pérdida en el stop = (distancia SL + slippage 0,10 $) × 1 oz ÷ 1,1155.

| Stop (en $) | Pérdida 0,01 lotes | Capital para 0,5 % | Capital para 1 % |
|---|---|---|---|
| 1 $ | 0,99 € | 197 € | 99 € |
| 2 $ | 1,88 € | 377 € | 188 € |
| 3 $ | 2,78 € | 556 € | 278 € |
| 5 $ | 4,57 € | 914 € | 457 € |

Además la regla de margen (no usar > 30 % del margen libre) exige ≈ 175 € / 0,30 ≈ **585 €**.
Un stop de 1 $ es poco realista a 3.900 $/oz (el ATR de M5 ya era ~1,4 $ con el oro a 1.830 $).

**Conclusión: el mínimo razonable está en torno a 600–1.000 €** si tu bróker usa
contrato de 100 oz y mínimo 0,01. Si tu bróker ofrece 0,001 lotes o un contrato de 1–10 oz,
estas cifras se dividen por 10 y bajan a ~60–100 € (⏳ lo dirá el script).
A ese ritmo de aportaciones el mínimo tarda muchos meses en alcanzarse, tiempo de sobra para la Fase 6.

## 4. Cuentas cent / micro

Las cuentas "cent" las ofrecen sobre todo entidades **offshore** (fuera de ESMA): sin
límite de apalancamiento retail, sin las mismas garantías y con riesgo de contraparte.
**No se recomiendan.** Solo se considerarían si el bróker está autorizado por la CNMV o
pasaporteado en la UE y el contrato es transparente. Pedir más apalancamiento para
"poder operar" con 20 € está explícitamente descartado: con 1:500, una vela normal de
5 minutos movería el 10–20 % de la cuenta.

## 5. Condiciones para operar con dinero real (todas obligatorias)

1. Bróker regulado (CNMV o entidad UE con pasaporte); cuenta a tu nombre; protección de
   saldo negativo.
2. Capital ≥ **max(capital para que 0,01 lotes con el stop mediano de la estrategia
   arriesgue ≤ 0,5 %, margen ÷ 0,30)**, calculado con `OrderCalcProfit`/`OrderCalcMargin`.
3. Fases 3, 6 y 7 aprobadas según los criterios de `docs/02_plan_fases.md`.
4. Autorización escrita del usuario + `LIVE_PHASE_UNLOCKED` cambiado a mano por el usuario.
5. Dinero que puedas perder entero sin consecuencias. Revisa la fiscalidad (en España las
   ganancias de CFD tributan en la base del ahorro).

## 6. Noticias y macro

No hay un feed gratuito y fiable en tiempo real que podamos integrar sin dependencias. Las
fuentes oficiales gratuitas publican los calendarios con antelación:
FOMC (federalreserve.gov) y CPI/NFP/desempleo (bls.gov/schedule). Plan: `config/events.csv`
mantenido a mano desde esas fuentes + bloqueo ±30 min + compuertas de spread y volatilidad.
Los rendimientos de bonos y el DXY no tienen fuente gratuita en tiempo real adecuada → no se
usan en vivo; se pueden estudiar en investigación con datos diarios (FRED) más adelante.

## 7. Riesgos principales

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Costes ≥ ventaja (spread, slippage) | Alta probabilidad de no tener edge | Filtro de coste/SL, análisis por sesión, benchmark de coste cero |
| Overfitting / p-hacking | Falsa ventaja | Lockbox, walk-forward, rejilla pequeña, benchmarks aleatorios |
| Stops con slippage (noticias, gaps) | Pérdida > presupuesto | Slippage en el dimensionado, blackout de noticias, sin posiciones en fin de semana |
| Datos Dukascopy ≠ bróker | Backtest optimista | Spread extra; recalibrar con export del bróker |
| Mac dormido / desconexión | EA parado | SL/TP en servidor desde la apertura; operar solo en ventanas; reconciliación |
| Bróker cambia condiciones | Margen/spread peores | Script de viabilidad periódico; límites en el EA |
| Error de código en ejecución | Órdenes duplicadas | Idempotencia, magic number, auditoría independiente, demo larga |
