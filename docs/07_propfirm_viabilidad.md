# XAUScalp y las prop firms (FTMO 2-Step): diagnóstico técnico y económico

> **Nota sobre este repositorio / Note on this repository.** Este documento menciona el componente de ejecución de órdenes (`XauScalp_Exec.mq5`, `ExecEngine.mqh`, `xauscalp.exec_audit` y `reports/exec_dryrun/`), que **no se publica aquí**. Las menciones se conservan como registro histórico del proyecto; los procedimientos y comandos que dependen de él no se pueden ejecutar con este repositorio. *This document refers to the order-sending component, which is not published here. The references are kept as a historical record; procedures that depend on it cannot be run from this repository.*

**Fecha: 2026-11-15.** Reglas leídas de las páginas de FTMO ese día (herramienta de lectura que resume el texto: contrastar antes de decidir).
Detalle con fuente de cada dato en `config/propfirm_ftmo_2step.yaml`. **No se ha comprado nada, no se ha enviado ninguna orden y no se ha tocado
ningún límite (`HARD_LIMITS`) ni autorización.**

## Conclusión corta
**Hoy no hay ninguna estrategia con ventaja estadística demostrada** (ORB: estudio 7; tendencia, momentum, pullback y reversión: estudio 8; el único caso
cercano, la tendencia Donchian, es exposición larga al mercado alcista de 2024-25 y no supera los criterios preregistrados). **No recomiendo pagar ninguna
evaluación.** Una prop firm no crea ventaja: solo cambia quién pone el capital. Lo que sí vale la pena es la **Free Trial** (gratuita) para medir condiciones
reales de ejecución, y seguir buscando ventaja en una cesta de activos (diseño preregistrado en `docs/08_hipotesis_multiactivo.md`).

## 1. Condiciones oficiales de FTMO 2-Step (según sus páginas, leídas 2026-11-15)
| Concepto | Dato | Observación |
|---|---|---|
| Fases | Challenge → Verification → FTMO Account | misma cuenta simulada en las dos primeras |
| Objetivo | **10 %** (Challenge), **5 %** (Verification); sin objetivo en la cuenta financiada | el balance debe superarlo **con todas las posiciones cerradas** |
| Pérdida diaria máxima | **5 %** del capital inicial: límite = balance a las 00:00 **CE(S)T** − 5 % | se recalcula cada día; **cuenta el equity (pérdidas flotantes, swaps, comisiones)** |
| Pérdida máxima | **10 % estática**: capital inicial − 10 % | no se arrastra con los beneficios |
| Días mínimos | **4** por fase (día con ≥ 1 posición *abierta*) | no hay mínimo en la cuenta financiada |
| Límite de tiempo | «Unlimited» | |
| Tamaños | 10.000 / 25.000 / 50.000 / 100.000 / 200.000 | cuenta simulada |
| Cuota | 10k: 89 € · 25k: 250 € · 50k: 345 € · 100k: 439 € (oferta; 540 € en otras páginas) · 200k: 1.080 € | **precios obtenidos de una búsqueda que resume su web: confirmar en la caja** |
| Reembolso | **100 % de la cuota** al solicitar el **primer retiro** de recompensa (solo 2-Step) | |
| Recompensa | **80 %** (hasta **90 %** con Scaling Plan o Premium) | retiro desde el día 14 tras la primera operación; mínimo 20 USD; hay que cerrar todo antes |
| EAs | **Permitidos** («algorithmic trading or EAs»); la operativa debe ser **replicable en cuentas reales** | máx. 200 órdenes simultáneas y 2.000 peticiones/día; EAs de terceros: riesgo de «asignación máxima de capital» |
| Noticias | Restricción de **±2 min** alrededor de eventos seleccionados (órdenes, SL, TP y pendientes) | **no se aplica en Challenge ni Verification**; sí en la cuenta financiada. Para XAUUSD afectan eventos del USD (tipos, empleo/salarios, PIB, minutas FOMC, CPI) |
| Prácticas prohibidas | *Gap trading* (abrir alrededor de noticias o a < 2 h de un cierre de ≥ 2 h), hedging/profit smoothing, sobreapalancamiento y apuestas unidireccionales, > 2.000 peticiones/día, explotar precios erróneos o retrasados | consecuencias: perder recompensas, descalificación o cierre |
| Apalancamiento | «hasta 1:100» (cuenta estándar); 1:30 (Swing) | **sin dato por activo (oro)** |
| Hora del servidor | GMT+2 con horario de verano | coincide con la regla verificada en este proyecto (`base_dst:120:Europe/London` es UTC+2/+3) |
| **Free Trial** | «abridged version» de la evaluación, **«No time limit»**, «Up to $200,000», «As many Free Trials as you need»; **no** cuenta como paso de calificación ni da derecho a recompensa | **contradice lo que se te dijo (14 días): verificarlo en la página de registro** |

**No consta en ninguna página leída** (hay que medirlo en su servidor MT5, con la Free Trial): tamaño de contrato de XAUUSD, lote mínimo y paso, spreads, comisiones por lote,
swaps, apalancamiento del oro, lista completa de «eventos restringidos». El modelo de costes del proyecto no se cambia hasta tenerlos.

## 2. Compatibilidad con este proyecto (sin cambiar nada)
- Nuestros límites son **más estrictos** que los de FTMO, por construcción: pérdida diaria 2 % (FTMO 5 %), semanal 5 %, caída desde máximo 8 % (siempre más cercano que el 10 % estático
  de FTMO, porque el máximo nunca baja del capital inicial), riesgo 0,5 % por operación (techo duro 1 %), 1 posición, SL obligatorio, sin martingala ni grid ni hedging.
- La hora de reinicio diario del servidor (GMT+2 con DST) coincide con las 00:00 CE(S)T de FTMO.
- Noticias: el bloqueo del EA (30 min después y 30 + 90 antes) cubre ±2 min para FOMC, CPI y NFP, pero **no** para el resto de eventos USD (PIB, minutas…): habría que ampliar el calendario
  antes de operar una cuenta financiada. En Challenge/Verification no aplica; el *gap trading* sí está prohibido (abrir cerca de grandes noticias) y nuestro bloqueo lo evita para esos tres tipos.
- Una prop firm **no reduce el riesgo del sistema**: solo el de tu capital. Las reglas se comprueban con el módulo `src/xauscalp/propfirm/` (abajo).

## 3. Módulo `xauscalp.propfirm` (separado y configurable)
- `config/propfirm_ftmo_2step.yaml`: reglas con procedencia y lista de lo no verificado; el cargador falla cerrado ante valores ausentes o absurdos.
- `rules.py`: `PropChecker` (máquina de estados con equity flotante, reinicio diario en la zona de la firma, pérdida máxima estática, objetivo con posiciones cerradas y días mínimos,
  valores no finitos = suspensión), ventanas de noticias de ±2 min (incluye SL/TP), dimensionado de lotes con redondeo hacia abajo.
- `replay.py`: reproduce una lista de operaciones con el recorrido M1 (extremo adverso de cada minuto) y detecta rupturas **sin que se cierre ninguna pérdida**.
- `montecarlo.py`: simulación reproducible del Challenge + Verification + 13 semanas financiadas con **bootstrap por semanas en dos niveles** (la incertidumbre sobre la ventaja
  entra en el resultado) y un **control nulo** (mismas semanas, expectativa neta 0). 11 tests.

## 4. Resultados de la simulación (estudio 9, cuenta de 10.000 €, cuota 89 €; `reports/09_propfirm_feasibility.md`)
**Evaluación principal con el riesgo operativo del proyecto (0,5 % por operación; techo duro 1,0 %)**, horizonte de 104 semanas por fase (FTMO no tiene límite de tiempo).
Probabilidad de superar Challenge + Verification, mediana [percentiles 5–95 % de la incertidumbre estadística], frente al control nulo (misma varianza y agrupación, expectativa neta 0):
| Estrategia (OOS, costes B) | Real a 0,5 % | Nulo a 0,5 % | EV por intento (real / nulo) | Real a 0,25 % |
|---|---|---|---|---|
| ORB | 0 % [0–5,5] | 8,5 % [4,0–13,1] | −89 € / −79 € | 0 % |
| Tendencia Donchian | 49,2 % [9,0–87,5] | 9,0 % [4,0–14,5] | +11 € / −77 € | 9,2 % [0–50,6] |
| Pullback | 17,5 % [0,5–65,3] | 9,8 % [6,0–15,5] | −66 € / −76 € | 0,8 % |
| Momentum | 3,5 % [0–35,2] | 15,0 % [10,5–20,0] | −85 € / −67 € | 0 % |
**El 1 % por operación se mantiene solo como sensibilidad separada** (no es la configuración operativa; ver el informe): sube todas las probabilidades, incluido el nulo (≈ 25–30 %).
Lectura honesta:
- Una estrategia **sin ventaja** pasa entre el 9 % y el 15 % de las veces con 0,5 % de riesgo y 104 semanas: aprobar un challenge es compatible con la suerte. Su valor esperado es de −67 a −79 € por intento.
- ORB y momentum quedan **por debajo del nulo** (expectativa neta negativa); el pullback queda dentro de la incertidumbre del nulo.
- **La tendencia Donchian NO queda validada por aprobar el challenge simulado.** Su probabilidad (49 %) tiene un intervalo [9–87 %] que llega al nivel del nulo, su ventaja no es estadísticamente significativa (estudio 8: IC95 inferior −0,02 R) y proviene de operaciones largas en el mercado alcista de 2024-25 (la muestra OOS solo contiene operaciones de 2022, 2024 y 2025). El EV de +11 € depende de que el futuro se parezca a esa muestra.
- Reproducción histórica exacta (fase 1, 0,5 %): Donchian 43/48 inicios pasan, ORB 0/28 (21 suspendidos), momentum 0/48 (20 suspendidos), pullback 10/45 (35 sin resolver).

## 5. Veredicto económico
- **Sin ventaja demostrada: no pagar.** El coste de 89 € (10k) es pequeño, pero el valor esperado de un intento sin ventaja es de −67 a −79 € (riesgo 0,5 %); y los 250-1.080 € de tamaños mayores multiplican la pérdida.
- **Con una ventaja demostrada** (cumplir los criterios preregistrados, no solo pasar la evaluación) la prop firm sí sería útil: elimina el problema de capital (con 10.000 € simulados el 0,01 lote deja de ser un límite).
- Aun así la **parte difícil no es el challenge sino lo posterior**: reglas de noticias en la cuenta financiada, replicabilidad en real, riesgo de que la firma cambie condiciones, y fiscalidad (España: el usuario es responsable).

## 6. Plan de pruebas (en este orden; cada paso es una puerta)
1. **Hoy, gratis y sin órdenes**: abrir la **Free Trial** de FTMO (cuenta demo) en MT5; anotar la fecha y la duración real que muestra. Ejecutar `XAU_FeasibilityReport` (solo `OrderCheck`) y `XAU_ExportHistory`/`XAU_ExportTicks` de un
   periodo corto. Resultado: tamaño de contrato, lote mínimo, spread real, comisión y swap de XAUUSD → rellenar la lista `unverified` del YAML y **calibrar el modelo de costes con un bróker real** (S1).
2. **Dry run en la Free Trial** (`InpEnableTrading=false`, ≥ 5 días): `XauScalp_ReadOnly` + `XauScalp_Exec` con `exec_audit`; sin autorización de órdenes.
3. **Otros instrumentos**: exportar M1 de EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, XAGUSD (+ índice/petróleo si existen) y ejecutar el estudio preregistrado `docs/08_hipotesis_multiactivo.md`. Si **ninguna** cesta cumple los
   criterios: «sin evidencia» y se para (o se cambia de enfoque).
4. **Solo si una estrategia cumple todos los criterios**: una confirmación única en el periodo reservado (la desbloqueas tú); después forward en Free Trial/DEMO durante ≥ 8 semanas con expectativa neta > 0 y 0
   incumplimientos de las reglas con `PropChecker`; **entonces y no antes** se plantea pagar un challenge de 10k (89 €).
5. Antes de cualquier orden, aunque sea en Free Trial: **cuarta/quinta auditoría cerrada**, prueba del tester con órdenes simuladas (`exec_audit --orders`) y tu autorización escrita por ti (token con login y caducidad).

## 7. Riesgos y límites de este análisis
Las reglas pueden cambiar en cualquier momento; las páginas se leyeron con una herramienta que resume; los precios no están confirmados; el feed de MetaQuotes-Demo no es el de FTMO; el estudio 9 supone que el futuro se parece a la
muestra OOS (2022-25, con un mercado alcista del oro) y no modela swaps, la restricción de noticias de la cuenta financiada ni la conversión de divisa. Nada de esto es asesoramiento financiero.
