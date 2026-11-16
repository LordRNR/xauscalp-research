# Auditoría técnica — 2026-11-12

> **Versión pública.** Se omiten los hallazgos y las recomendaciones sobre la configuración de la herramienta de desarrollo con IA (sus reglas de permisos y su *hook*) y sobre el equipo del autor. Se conservan los hallazgos técnicos sobre el código de investigación y de ejecución. Las referencias a commits remiten al historial original, que es privado. Las menciones a `XauScalp_Exec`, `ExecEngine.mqh`, `exec_audit` y `reports/exec_dryrun/` se refieren a un componente de ejecución de órdenes que **no** se publica en este repositorio (*the order-sending component is not published here*).

Entorno real del repositorio (no el de la revisión externa): macOS 26.6 (Apple Silicon),
Python 3.12.10, **pandas 3.1.1**, numpy 2.5.4, pyarrow 26.0.1, PyYAML 6.0.3,
pytest 9.2.0, ruff 0.17.4. Línea base antes de tocar nada: árbol git
limpio (1 commit), **52/52 tests OK** con pandas 3.1.1, 15 avisos de ruff (estilo).

Al cerrar esta sesión: **223 tests OK**, `ruff check` sin errores.

## Hallazgos

| ID | Sev. | Hallazgo | Estado | Prueba de regresión |
|---|---|---|---|---|
| R1 | **CRÍTICA** | `RiskManager` **aprobaba** con spread `NaN`, antigüedad de datos `NaN`, margen libre `NaN` o `kill_switch=None`; con equity `NaN/inf`, FX `NaN`, apalancamiento 0 o step 0 lanzaba excepción en vez de rechazar. `RiskConfig(risk_per_trade_pct=nan)` pasaba la validación (comparaciones con NaN = False). | Corregido: validación *fail-closed* de toda entrada, flags de seguridad solo "seguros" si son exactamente True/False, `ENTRY_PRICE_MISMATCH`, config estricta (sin valores por defecto silenciosos, sin claves desconocidas, sin NaN/inf/bool/str). `HARD_LIMITS` sin cambios. | `tests/test_risk_invalid_inputs.py` (54 casos) |
| T1 | ALTA | Conversión de hora MT5: se aplicaba **un único desfase** (el del momento de exportar) a todo el histórico → 1 h de error en la otra mitad del año si el servidor sigue DST. | Corregido: `ServerTimePolicy` (desconocida por defecto → rechaza), reglas declaradas, **inferencia semanal** contra Dukascopy con umbral de confianza; el exportador ya no sugiere que el offset sea histórico. | `tests/test_server_time.py` (cambios de EE. UU. 9-mar/2-nov y UK 30-mar/26-oct 2025, aperturas de Londres y COMEX, test que reproduce el bug antiguo) |
| D1 | ALTA | Histórico discontinuo (hueco de **1.648 días** 2021-03 → 2025-10 y otros >4 días) tratado como consecutivo: ATR, percentil de régimen y H1 cruzaban huecos; `move15` se calculaba por desplazamiento de filas; folds vacíos se trataban como periodos completos. | Corregido: segmentos (hueco > 96 h), variables por segmento, informe de cobertura, `move15` por tiempo, folds con cobertura < 90 % = `INSUFFICIENT_DATA`, estudio **NO VALIDABLE** si < 4 folds útiles. | `tests/test_data_coverage_gaps.py` |
| W1 | ALTA | Walk-forward: el resultado global concatenaba operaciones de Londres y NY **simuladas por separado** (podían coexistir dos posiciones) y los benchmarks usaban otro universo. | Corregido: **una simulación conjunta cronológica** con una sola posición; benchmarks sobre exactamente la misma lista de señales. | `test_joint_simulation_never_overlaps_positions` |
| H1 | MEDIA | Holdout: `load_research_data` **decodificaba** ficheros del periodo reservado y luego los recortaba; `eurusd_rate()` **leyó EURUSD de oct-2026** (periodo reservado). | Corregido: recorte antes de leer, `load_m1(max_date=...)` obligatorio + `HoldoutAccessError`, test estático sobre todas las llamadas; tabla de capital eliminada del estudio 2. | `tests/test_holdout_and_downloader.py` |
| E1 | MEDIA | Motor: una posición abierta podía "atravesar" un hueco de datos de años y cerrarse al otro lado; el cierre por tiempo podía saltar el hueco. | Corregido: `DATA_GAP`/`END` → `valid=False`, excluidas (y contadas) en métricas; huecos de fin de semana siguen llenando a la reapertura. | `tests/test_engine_extremes.py` |
| E2 | MEDIA | `directions` (benchmark) se alineaba con el orden **ordenado** interno, no con el del llamante. Latente (el script ordenaba antes). | Corregido + error si la longitud no coincide. | `test_directions_align_with_caller_order_not_sorted_order` |
| DL1 | MEDIA | Descargador: reintentos por fichero sin pausa global; ante 429 seguía lanzando peticiones; podía detenerse con un fichero sin validar. | Corregido: throttle global, `Retry-After`, pausa exponencial compartida, *circuit breaker*, presupuesto de peticiones, validación LZMA antes de escribir, cuarentena, parada limpia. | `tests/test_holdout_and_downloader.py` |
| O1 | BAJA | ORB: el código invalidaba el día ante cualquier hueco > 5 min en la ventana; la especificación dice "en la barra de decisión". | Alineado con la especificación. | `tests/test_orb.py` |
| S1 | BAJA (decisión pendiente) | `max_spread_usd = 0,60 $` es absoluto: con el oro a ~4.000 $ el spread típico (Dukascopy + 0,15) es ~0,78 $ y bloquea casi todas las señales de oct-2025. | **No modificado** (no se relajan límites). Propuesta: expresarlo relativo al ATR o en puntos básicos, decidirlo con el spread real del bróker. | Diagnóstico en `reports/03_orb_diagnostics.md` |
| P1 | INFO | `MetaTrader5` (PyPI) solo publica *wheels* `win_amd64`. | Arquitectura sin dependencia de ese paquete en macOS. | — |

## Integridad del holdout (≥ 2025-11-01)

- **En caché**: 14 días de XAUUSD de oct-2026 y 5 días de EURUSD de oct-2026.
- **Decodificado**: XAUUSD del holdout **nunca** (el estudio 2 solo se ejecutó con la
  configuración de humo que terminaba en 2021-03-31; con la configuración completa no se
  llegó a ejecutar antes de esta corrección). EURUSD de oct-2026 **sí** se leyó: a mano para
  la tabla de capital de `docs/00_viabilidad.md` y por `eurusd_rate()` en la ejecución de humo
  (sin operaciones, la tabla no llegó a calcularse).
- **Usado para seleccionar o modificar estrategias**: **no**. Ningún parámetro, regla ni
  decisión se basó en datos ≥ 2025-11-01.
- Conclusión: **no hay evidencia de contaminación** del holdout de XAUUSD. El tipo EURUSD
  usado en la planificación de capital procede del periodo reservado; se trata como dato de
  planificación actual (no de investigación) y en adelante la viabilidad usará
  `OrderCalcProfit` del bróker.

## Niveles de evidencia (no son intercambiables)

1. **Backtest con velas M1** (este repositorio): orden intrabarra desconocido, SL primero
   si hay ambigüedad. Etiquetado en cada resultado (`evidence_level = 1-M1_BAR_APPROXIMATION`).
2. **Backtest con ticks reales** del bróker (Strategy Tester "Every tick based on real
   ticks"): pendiente, requiere el EA de ejecución y MT5.
3. **Forward DEMO**: pendiente.

## Lo que NO se ha podido verificar

- Ningún fichero MQL5 está **compilado** (no hay MetaEditor en el Mac). Hay tests
  estáticos (sin llamadas de trading, límites idénticos, estados idénticos) pero no
  sustituyen a la compilación ni al Strategy Tester.
- Condiciones reales de la cuenta (contrato, lote mínimo, margen, spread, comisión).
- Zona horaria del servidor MetaQuotes-Demo.

## Auditoría independiente (agente `risk-auditor`, solo lectura) y seguimiento

Revisó los cambios desde la revisión anterior (historial original, privado); 206 tests en verde en su ejecución. Verificó como correctos:
`HARD_LIMITS` sin cambios y alineados con MQL5, módulo de bloqueo de LIVE sin cambios
desde la revisión anterior, carga estricta de YAML, gestor *fail-closed*, EA sin código de envío y con
rechazo de cuentas no demo, guarda de holdout en `load_m1`/`pipeline`.

| ID | Sev. | Hallazgo del auditor | Estado |
|---|---|---|---|
| H1 | **ALTA** | El tamaño se calculaba con la entrada de la propuesta, no con la cotización viva: con una entrada desfasada un 0,1 % se aprobaban 1,38 lotes con pérdida real ≈ 1.035 sobre 100.000 (**1,03 %, por encima del techo del 1 %**). | **Corregido** en Python y MQL5: peor precio entre entrada y cotización; SL más allá del precio que lo dispara (`SL_WRONG_SIDE_OF_MARKET`). `tests/test_audit_followup.py` |
| M2 | MEDIA | Sin techo/suelo para spread máx., antigüedad de datos, errores consecutivos; slippage 0 aceptado. | Corregido: `SANITY_BOUNDS` (Python y MQL5, test de igualdad). |
| M3 | MEDIA | Stops/freeze level no comprobados correctamente. | Corregido en el EA (desde el precio que dispara el stop). Python no modela niveles del bróker (investigación). |
| M4 | MEDIA | Datos obsoletos medidos con `TimeCurrent()` (se congela con el feed). | Corregido: `TimeTradeServer()`. |
| M5 | MEDIA | Anclas día/semana se reiniciaban al arrancar el EA. | Corregido: reconstrucción desde el historial de operaciones. |
| M6 | MEDIA | La paridad cargaba datos del periodo reservado sin candado; `holdout_start` modificable. | Corregido: respeta el candado por defecto; fecha fijada por test. |
| M7 | MEDIA | Sin calendario de noticias el EA no bloqueaba. | Corregido: `NEWS_CALENDAR_MISSING` (rechazo). |
| L1–L7 | BAJA | Desbordamiento en sizing; pico obsoleto; recuentos que fallaban abiertos; bloque suelto; `#import` no prohibido; fuentes sin recorte previo; construcciones MQL5 dudosas. | Corregidos. L7 sigue **UNVERIFIED** hasta compilar. |

## Seguimiento 2026-11-14 (compilación real y condiciones de la cuenta)

| ID | Sev. | Hallazgo | Estado |
|---|---|---|---|
| P2 | MEDIA | El filtro de coste ORB del EA usaba `InpSlippage` (slippage de **riesgo**, 0,10) y Python `costs.slippage_usd` (0,05). Con datos idénticos el EA habría rechazado más señales por coste, y la paridad lo habría clasificado como SPREAD_SENSITIVE en lugar de diferencia dura. | Corregido: nueva entrada `InpCostSlippage` (0,05); test de espejo que compara **todos** los valores por defecto del EA con `config/default.yaml`; preset del tester generado desde la configuración. |
| P3 | BAJA | El registro de decisiones del EA **añade** filas entre ejecuciones: repetir el tester con la misma etiqueta duplicaba días y la paridad los cruzaba mal. | Corregido: `read_ea_log` rechaza (*fail-closed*) días-sesión repetidos y pide otra `InpLogTag`. |
| T2 | BAJA | El estudio 4 podía listar varias reglas horarias «compatibles» a la vez (con datos solo de verano, «fijo», «EE. UU.» y «UE» encajan). | Corregido: `fit_server_rule` emite un único veredicto (CONSISTENT / AMBIGUOUS / INCONSISTENT / INSUFFICIENT) y exige semanas capaces de refutar las alternativas. |
| C2 | INFO | `Include/XauScalp` no estaba instalado en MT5 (el EA no habría compilado con F7). | La herramienta `mt5_build` copia todo y compila: **0 errores, 0 avisos** en los 4 programas. El único aviso inicial era el formato de `#property version` (solo relevante para el Market). |

El informe de viabilidad real (MetaQuotes-Demo) pasa todas las comprobaciones de
coherencia, por ejemplo que el margen de 0,01 lotes cuadre con el precio, el apalancamiento
y el tipo EURUSD. No hay ningún supuesto en el que el bróker sea **peor** que la
configuración. Comisión y deslizamiento siguen sin medirse (`reports/05_broker_conditions.md`).

## Seguimiento 2026-11-14 (exportaciones reales de MT5)

| ID | Sev. | Hallazgo | Estado |
|---|---|---|---|
| H1b | MEDIA | Los lectores de CSV del bróker (`read_mt5_rates_raw`, `read_mt5_ticks_raw`, `load_mt5_rates_csv`) **leían el fichero entero y recortaban después**. El export M1 real incluye 356.516 filas del periodo reservado (nov-2025 → nov-2026). Se descartaban antes de calcular nada y el estudio 4 solo usó datos anteriores al límite, así que no hay contaminación; pero es exactamente el patrón del hallazgo H1. | Corregido: los lectores **dejan de leer** al llegar a `server_cut(max_date)` (el fichero está ordenado y se verifica; si no lo está, error), `max_date` obligatorio con test estático. Verificado con el fichero real: 1.707.302 de 2.063.818 filas leídas. |
| P4 | BAJA | La paridad cargaba todo el histórico del bróker (2021→2025) y lo comparaba con el registro del EA (2 meses): «NO EQUIVALENTE» falso. Con una ventana implícita (la del propio registro) un EA detenido a mitad habría pasado. | Corregido: `--from/--to` obligatorios (= fechas del tester); test de EA parcial. |
| D2 | INFO | Export M1 con un agujero de 110 min (23-oct-2025 17:09–18:58 UTC) donde sí hay ticks. Fuera de las ventanas ORB. | Documentado (estudio 6). Los ticks lo pueden rellenar. |
| D3 | INFO | 4 cortes de cotización del servidor de 7–17 min en octubre (también ausentes de sus velas); uno dentro de la ventana ORB de Nueva York del 10-oct. | Documentado. No se rellenan: son del servidor. |
| T3 | INFO | Zona horaria verificada de forma independiente: 28 semanas confiables; las 6 que separan UE de EE. UU. (mar-2021, mar-2024, semana del 25-oct-2025) dan +2 h donde EE. UU. predeciría +3 h. | `base_dst:120:Europe/London`. |

Sin cambios en `HARD_LIMITS`, `SANITY_BOUNDS`, `modes.py` ni en la configuración de riesgo.
Los criterios de completitud de ticks se refinaron tras ver la primera ejecución (la versión
inicial confundía pausas programadas con pérdidas); el informe 6 lo declara.

## Auditorías independientes de 2026-11-14 (risk-auditor, solo lectura)

**Auditoría 1 — EA de solo lectura y controles de riesgo (previa a la etapa C).** Sin críticos.
| ID | Sev. | Hallazgo | Estado |
|---|---|---|---|
| H1 | ALTA | Guardián no atómico con el envío; un timeout puede duplicar la entrada | Diseñado en la etapa C (marcador *in-flight*, ver auditoría 2) |
| H2 | ALTA | `ENTRY_PRICE_MISMATCH` vacuo en el EA; sin control de edad/contigüidad de la señal | Etapa C: `Fresh()` (contigüidad, ≤ 65 s, deriva ≤ 0,25×SL). El EA de solo lectura no opera |
| H3 | ALTA | El contador de errores consecutivos se borra con cada `CopyRates` correcto | Etapa C: contador persistente, solo un *fill* confirmado lo borra |
| M1 | MEDIA | Escáner de llamadas de trading frágil y duplicado | Corregido: `mql5_scan.py` único, lista blanca explícita, strings no son comentarios |
| M2 | MEDIA | Calendario parcial pasa por «ok» | Corregido en `News.mqh` (EA de ejecución); calendario oficial generado. El EA de solo lectura no se modificó (paridad probada) |
| M3–M7 | MEDIA | Anclas de equity, slippage de entrada, tick size/stops del TP/límite de volumen, reloj del tester, kill switch antes de enviar | M4/M5/M7 en el motor; M3 y M6 documentados (anclas con retiradas; tester ≠ evidencia de ejecución) |

**Auditoría 2 — motor de ejecución DEMO.** Sin críticos; 1 ALTA y 6 MEDIA, todas corregidas y recompiladas (0/0):
| ID | Hallazgo | Corrección |
|---|---|---|
| H-1 | El cierre por riesgo post-*fill* fallaba abierto (un solo intento) | `DemandClose`: marca persistente, reintento en cada `Reconcile`, bloqueo si sigue abierta tras 60 s |
| M-1 | Reconciliación sin historial: un *fill* rápido dejaba el motor bloqueado; ADOPT sin chequeo de riesgo | Se consulta el historial (deal de entrada); ADOPT recalcula el riesgo |
| M-2 | Reiniciar el EA permitía reentrar en la misma sesión | Marca persistente por (sesión, día) antes del envío |
| M-3 | Parser de noticias: comas entre comillas, un solo evento lejano, operación que cruza una noticia | Líneas con comillas o ≠ 3 campos = descartadas; cobertura contigua; bloqueo desde (30 + 90) min antes |
| M-4 | Marcador *in-flight* solo en GlobalVariable | Duplicado en fichero (`FileClose` vuelca) |
| M-5/M-6 | Tolerancia post-*fill* 1,25×; test de retcodes solo comprobaba presencia | Tolerancia 1,10×; el test compara los conjuntos exactos analizando el `switch` |
Menores (L-1…L-9): `InpMagic` validado (> 0 y distinto del EA de solo lectura); el log de auditoría es obligatorio para
enviar; el resto documentado en `docs/05_mt5_instalacion_y_pruebas.md` §7 (reset manual de `errors`/`lock`, autorización sin token,
sin *time exit* si se reinicia con `InpEnableTrading=false`).

**Veredicto de la auditoría 2 sobre el estado previo a las correcciones:** tester con órdenes simuladas = GO con condiciones;
**cualquier orden DEMO = NO-GO** hasta cerrar la lista (hecho en código), pasar el tester, varios días de *dry run* en DEMO, nueva
auditoría tras los cambios y firma humana. **Esa nueva auditoría sobre el código corregido NO se ha hecho todavía.**
*(Hecha después: ver la auditoría 3, más abajo.)*

## Auditoría 3 (2026-11-15) — motor de ejecución tras las correcciones
Sin críticos. **Veredicto del auditor: tester con órdenes simuladas = GO con condiciones; órdenes DEMO = NO-GO hoy.**
| ID | Sev. | Hallazgo | Estado |
|---|---|---|---|
| S1 | ALTA | La autorización DEMO (fichero vacío) y el cambio de `InpEnableTrading` se podían eludir por shell (por varias vías de shell) | Corregido: el EA exige un **token** (`login=…;expires=…`, ≤ 31 días, solo esa cuenta). Las medidas sobre la configuración de la herramienta de desarrollo no se publican. **Residual**: la autorización final es siempre un acto humano |
| M1/M3 | MEDIA | Marca de sesión, bloqueo y errores solo en variables globales sin volcado | Corregido: marca de sesión = variable global (volcada y verificada) + **fichero** + **deal en el historial**; bloqueo = variable + **fichero**; `GlobalVariablesFlush`; si la marca no se puede guardar, no se envía |
| M2 | MEDIA | Estado compartido entre tester y DEMO y entre cuentas | Corregido: prefijo por cuenta y modo (`T`/`L`), también en el guardián de riesgo |
| M4 | MEDIA | El reset manual borraba también las sesiones ya operadas | Corregido: espacio de nombres propio `xauscalp.exdone.*` y procedimiento documentado |
| N1 | MEDIA | Calendario con huecos pasaba por «ok» | Corregido: huecos entre eventos ≤ 45 días en la ventana [−1 d, +14 d] |
| E3 | BAJA | Una coma en el log rompía el análisis | Corregido (se sustituye por `;`) |
| D7/D8 | — | El simulador no cubría el reset humano ni la pérdida de variables sin intento en curso | Cubierto: 300 secuencias aleatorias con pérdida de variables en cualquier momento mantienen los invariantes |

Pendiente (no hecho): E1 (prechecks de conexión/AutoTrading sin bloqueo), D1–D6 y D9–D11 del simulador (OrderCheck, cierre parcial o
ambiguo, fórmula de riesgo), G1 (reproducir la semana 1 sin semilla), M6 (sin *time exit* con el interruptor apagado; documentado).
*(La auditoría 4, más abajo, revisó estos cambios.)*

## Auditoría 4 (2026-11-15) — motor de ejecución tras la auditoría 3
**Sin críticos ni altos nuevos. Veredicto del auditor: tester con órdenes simuladas = GO condicionado; cualquier orden DEMO = NO-GO.**
| ID | Sev. | Hallazgo | Estado |
|---|---|---|---|
| N-1 | MEDIA | El estado del tester (`exec_done_T.*`, `exec_lock_T.*`, `exec_inflight_T.*`) persistía entre ejecuciones y las envenenaba | Corregido: el EA lo borra al arrancar **solo en el tester** (nunca estado real ni el fichero de autorización) |
| N-4 | BAJA | El analizador de la autorización dependía de `StringToTime` | Corregido: fecha como enteros con rangos estrictos; **falta un autotest ejecutado en MT5 con casos negativos** (fecha basura, otro login) |
| N-5 | BAJA | `exec_audit --orders` era más débil de lo que parecía | Reforzado: arranque con `trading=ENABLED` en el tester, volumen enviado = aprobado, ≤ 3 operaciones/día |
| N-6 | BAJA | El guardián no distinguía tester de real en el prefijo | Corregido (`T.`/`L.`) |
| N-7/N-8/N-9 | BAJA | Mensaje de bloqueo incompleto; fallo al persistir el contador sin escalada; `#include` sin distinguir mayúsculas | Corregidos (aviso completo; si no se puede guardar, se bloquea; búsqueda sin distinguir mayúsculas y prueba de que el nombre del fichero de autorización solo aparece en los dos ficheros de ejecución) |
**Lista exacta antes de cualquier orden DEMO** (del auditor): autotest del analizador en MT5, tester con órdenes simuladas aprobado por `exec_audit --orders`, dry run ≥ 5 días en la cuenta real (OrderCheck, modo de llenado, comentario del deal, supervivencia de variables tras *force quit* y cambio de cuenta), verificación manual del calendario y tu firma.

