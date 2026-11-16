# MT5: compilación, exportaciones, zona horaria, tester y paridad

> **Nota sobre este repositorio / Note on this repository.** Este documento menciona el componente de ejecución de órdenes (`XauScalp_Exec.mq5`, `ExecEngine.mqh`, `xauscalp.exec_audit` y `reports/exec_dryrun/`), que **no se publica aquí**. Las menciones se conservan como registro histórico del proyecto; los procedimientos y comandos que dependen de él no se pueden ejecutar con este repositorio. *This document refers to the order-sending component, which is not published here. The references are kept as a historical record; procedures that depend on it cannot be run from this repository.*

Ningún paso de esta guía envía órdenes. El EA `XauScalp_ReadOnly` no contiene código de
trading (lo verifican los tests y la herramienta de copia se niega a instalarlo si lo
tuviera). **No actives "Algo Trading"**: nada de esto lo necesita.

## Estado a 2026-11-14

| Paso | Estado | Resultado |
|---|---|---|
| Compilar 3 scripts + EA | ✅ hecho | 0 errores, 0 avisos (`reports/mt5_build/SUMMARY.md`) |
| Informe de viabilidad | ✅ ejecutado | MetaQuotes-Demo (estudio 5) |
| Export M1 desde 2021 | ✅ hecho | 2.063.818 velas; 110 minutos sin vela el 23-oct-2025 (ver paso 4) |
| Zona horaria del servidor | ✅ **CONSISTENT** | `base_dst:120:Europe/London` (UTC+2 invierno, +3 verano, cambio con la UE) |
| Export de ticks oct-2025 | ✅ hecho | 2.622.575 ticks; completo para ese mes (estudio 6) |
| Ejecución del EA en el tester | ✅ 5 ejecuciones | historial en `reports/parity/README.md` |
| Paridad Python/MQL5 | ✅ **EQUIVALENT, 90 sesiones** (`parity5`) | evidencia en `reports/parity/`; no es rentabilidad |

Compilar solo prueba la sintaxis: el comportamiento real se comprueba en el tester.

## 0. Lo que se hace desde el Mac (sin abrir MetaEditor)
```bash
uv run python -m xauscalp.mt5_build all     # copia mt5/ a MT5 y compila con MetaEditor
uv run python -m xauscalp.mt5_build fetch   # trae los CSV de Common/Files y del tester a data/mt5/
```
- `all` copia solo los ficheros de este proyecto (nunca borra nada tuyo) y compila con la
  línea de comandos de MetaEditor dentro del Wine que trae MetaTrader 5.app.
- **No edites el código en MetaEditor**: se edita en el repositorio y se vuelve a copiar.

## 1. Ajuste previo (hecho)
Herramientas → Opciones → Gráficos → "Máx. barras en ventana" → Unlimited.

## 2. Export M1 (hecho)
`XAU_ExportHistory` con `InpFrom = 2021.01.01` → `XAUUSD_M1_20210101_20261113.csv`.
El fichero incluye fechas del periodo reservado (≥ 2025-11-01). Los lectores de Python
**dejan de leer** al llegar al límite de investigación (356.516 filas ni se leen): el candado
se respeta también con los CSV del bróker.

## 3. Zona horaria (hecho)
`research/04_verify_server_tz.py` → veredicto **CONSISTENT**, regla europea, base 120 min.
Verificado de forma independiente: 28 semanas confiables; las 6 que separan la regla de la
UE de la de EE. UU. (mar-2021, mar-2024 y la semana del 25-oct-2025) dan +2 h donde la regla
de EE. UU. predeciría +3 h. Para el EA: `InpTzPolicy = TZ_BASE_PLUS_EU_DST`,
`InpTzBaseMinutes = 120` (ya van en el preset).

## 4. Export de ticks (hecho) y qué dice
Resumen del estudio 6 (`reports/06_tick_quality.md`):
- Los 23 días laborables de octubre tienen ticks; los 8 días sin ticks son sábados y domingos
  (en hora del servidor).
- Los ticks reproducen las velas del servidor: OHLC idéntico y el nº de ticks que cambian el
  bid coincide con `tick_volume` en el 100 % de las 31.562 velas.
- 4 silencios de 7–17 min también faltan en las velas del servidor (cortes de cotización
  del servidor); uno cae dentro de la ventana ORB de Nueva York del 10-oct.
- **Agujero en el export M1**: 23-oct-2025 17:09–18:58 UTC (110 min) hay ticks pero no hay
  velas. Queda fuera de las ventanas ORB, así que no afecta a la paridad. Si algún día importa,
  la fuente de ticks (`MT5BrokerTicksSource`) lo rellena.
- Solo es **un mes** del feed de MetaQuotes-Demo. Sirve para calibrar costes, no para validar.

## 5. Strategy Tester: paridad
**5.1 Preset** (ya generado; repítelo solo si cambia `config/default.yaml`):
```bash
uv run python -m xauscalp.mt5_build preset --tz base_dst:120:Europe/London --log-tag parity3
```
Escribe `XauScalp_ReadOnly_parity.set` en `MQL5/Presets` y en `MQL5/Profiles/Tester`
(el diálogo *Cargar* abre una u otra) e imprime todos los valores.

**5.2 En MT5**: Ver → **Probador de estrategias** (Ctrl+R), pestaña *Configuración*:

| Campo | Valor | Por qué |
|---|---|---|
| Experto | `XauScalp_ReadOnly` | |
| Símbolo / periodo | XAUUSD, M1 | El EA decide al cierre de cada vela M1 |
| Fechas | Personalizado: **2025.09.01 – 2025.11.01** | El tester **excluye** el día final: «hasta 11.01» evalúa hasta el 31-oct. El EA se detiene solo en la primera barra ≥ 2025-11-01 UTC (candado); **nunca** fechas posteriores |
| Retrasos | Sin retrasos | No hay órdenes |
| Modelado | **"1 minute OHLC"** | El tester genera los ticks a partir de las mismas velas que lee Python: cualquier diferencia es un fallo de lógica |
| Optimización | Deshabilitada | |
| Parámetros de entrada | Clic derecho → *Cargar* → `XauScalp_ReadOnly_parity.set` | |

Comprueba en *Parámetros de entrada* que `InpTzPolicy = 4`, `InpTzBaseMinutes = 120` e
`InpLogTag = parity3`. Pulsa **Iniciar**. En *Diario* debe verse
`XauScalp_ReadOnly started ... READ-ONLY: no orders will be sent.`
`NEWS_CALENDAR_MISSING` es normal: sin calendario el EA rechaza por diseño y no afecta a
las señales.

**5.3 Comparar** (la ventana es **explícita** y debe ser la del tester; así un EA que se
detuviera a mitad no pasa por una ventana recortada):
```bash
uv run python -m xauscalp.mt5_build fetch
uv run python -m xauscalp.parity --ea data/mt5/xauscalp/decisions_parity3.csv \
    --broker-m1 data/mt5/XAUUSD_M1_20210101_20261113.csv \
    --tz base_dst:120:Europe/London --from 2025-09-01 --to 2025-10-31
```
Python espera **90 día-sesiones** (`--to 2025-10-31`: es la fecha del último día evaluado, no la del tester) (88 SIGNAL, 2 NO_BREAKOUT; lista en
`reports/parity/python_expected_2025-09-01_2025-10-31.csv`). Solo hay equivalencia con **0 diferencias duras,
0 filas que falten en un lado y ≥ 20 día-sesiones**. Las diferencias por spread se listan
aparte, nunca se esconden (con los spreads de esta demo, 0,17 $, no deberían aparecer).

**Cada ejecución del tester necesita otro `--log-tag`** (`parity2`, …): el EA añade filas
al registro y la herramienta rechaza registros con días repetidos. Si `fetch` no encuentra el
fichero, lo busca también en `Tester/Agent-*/MQL5/Files/xauscalp/` (→ `data/mt5/agents/`).

**5.4 Segunda pasada (más cerca del nivel de evidencia 2)**: repite con el modelado
**"Every tick based on real ticks"**, fechas **2025.10.01 – 2025.10.31**, otro `--log-tag`
(`parity2`) y `--from 2025-10-01 --to 2025-10-31`. Si el diario dice que no hay ticks reales
para esas fechas, **no** es nivel 2. Aquí EA y Python usan spreads distintos (primer tick de
la vela siguiente frente a spread de la vela): es la prueba de que esa diferencia no cambia
ninguna decisión.

**5.5 Qué se encontró en parity1/parity2 (2026-11-14)**
- `decisions_parity1.csv` tenía **cada fila duplicada** (176 filas = 88 × 2): el EA añade al
  registro y la misma etiqueta se usó dos veces. La herramienta lo rechaza (`DuplicateDecisionsError`).
  **Una etiqueta nueva en cada ejecución**; no se borra ni edita ningún registro antiguo.
- **ATR (13 y 20-oct, Londres, lunes)**: la ventana de cálculo del EA se medía en tiempo natural
  y solo contenía ~110 barras M5 esos lunes; el error de semilla de Wilder, (13/14)^110, dio una
  diferencia de 0,10–0,13 % (> tolerancia 0,1 %). Emulada en Python: residuo de 6e-7. Corregido
  (10 días, mínimo 300 barras).
- **Spread (20-oct)**: 0,06 frente a 0,17 son dos magnitudes distintas: `spread_now` = vela 10:21
  (siguiente), `spread_bar` = vela 10:20 (decisión). `spread_bar` coincide con Python en 86/86.
- **31-oct**: el tester no incluye el día final (último registro del EA: 30-oct 23:59:55).

## 6. Demo en vivo, solo lectura (opcional)
Arrastra el EA a un gráfico XAUUSD M1 con `InpTzPolicy = TZ_BASE_PLUS_EU_DST` y
`InpTzBaseMinutes = 120` (con `TZ_LIVE_CLOCK` también funciona en vivo). **Algo Trading
desactivado**. Verás un panel con símbolo, zona horaria, spread, señales y motivos; estado en
`Common/Files/xauscalp/state_ro.json`. **Kill switch**: fichero vacío
`Common/Files/xauscalp/KILL_SWITCH`.

## 7. Etapa C: EA de ejecución DEMO (escrito, compilado, **sin ejecutar y sin aprobar**)

> **Esta sección y las tres siguientes describen el EA de ejecución, que no se publica en este repositorio.** Sus archivos y comandos (`XauScalp_Exec.mq5`, `ExecEngine.mqh`, `mt5_build ... --with-exec`, `xauscalp.exec_audit`, `reports/exec_dryrun/`) no existen aquí y los procedimientos no se pueden ejecutar. Se conservan como registro histórico. *This section and the next three describe the order-sending Expert Advisor, which is not published here; they are kept as a historical record.*
`mt5/Experts/XauScalp_Exec.mq5` + `Include/XauScalp/ExecEngine.mqh` (único código de órdenes del
repositorio; el escáner solo lo admite en esos dos ficheros). **No se copia a MT5 con la
herramienta normal**: hace falta `--with-exec`. Compilar no envía nada.

```bash
uv run python -m xauscalp.mt5_build all --with-exec    # copia + compila (0 err / 0 avisos hoy)
uv run python -m xauscalp.calendar.official write --install   # calendario FOMC/CPI/NFP en Common/Files
```
Capas de seguridad (todas deben cumplirse para que se envíe algo):
1. `InpEnableTrading = false` por defecto → **dry run**: toda la tubería, sin `OrderSend`.
2. Cuenta **DEMO** (o Strategy Tester, donde las órdenes son simuladas). No existe ningún input para cuentas reales.
3. Fichero `Common/Files/xauscalp/EXEC_DEMO_AUTHORIZED` creado **a mano** por ti (solo fuera del tester) con **una línea**
   `login=<tu número de cuenta DEMO>;expires=AAAA-MM-DD` (caduca como máximo a 31 días vista y solo vale para esa cuenta; un fichero vacío
   o de otra cuenta no autoriza nada). El número de cuenta **no** se guarda en el repositorio.
4. Algo Trading activo; sin `KILL_SWITCH`; motor no bloqueado; sin intento en vuelo; ninguna posición.
5. Los límites de riesgo son los mismos (`HARD_LIMITS` sin cambios); el volumen sale solo del guardián.

**Prueba 1 (segura, dry run en el tester)** — `exdry1` ya se ejecutó y fue **parcial** (`reports/exec_dryrun/`); repetir como `exdry2`:
igual que la 5.2 pero con experto `XauScalp_Exec`, `InpEnableTrading=false`, `InpTzPolicy=4`, `InpTzBaseMinutes=120`, `InpLogTag=exdry2`,
**«1 minute OHLC»**, 2025.09.01–2025.11.01. Después: `mt5_build fetch` y `uv run python -m xauscalp.exec_audit decisions_exdry2.csv exec_exdry2.csv state_exdry2.json` (debe dar SUPERADO). Debe registrar las mismas señales que `XauScalp_ReadOnly`
(`decisions_exdry1.csv`) y `exec_exdry1.csv` con `DECISION ... DRY_RUN`. Con el calendario cargado,
las sesiones dentro de una ventana de noticias aparecerán como `NEWS_BLACKOUT`.
**Prueba 2 (solo tras la auditoría 2 y mi OK por escrito)**: `InpEnableTrading=true` **solo en el
tester** («Every tick based on real ticks» en octubre 2025): las órdenes son simuladas.
**DEMO real**: no antes de superar la prueba 2 y de cerrar la lista «must-fix» de `docs/auditoria_2026-11-12.md`.

### Prueba del tester con órdenes SIMULADAS — **PENDIENTE: no se ejecuta sin tu aprobación escrita**
Esta es la única prueba que habilita la **ruta de envío** (`InpEnableTrading=true`); en el tester las órdenes son simuladas, pero el código de envío se ejercita de verdad.
No la he lanzado ni la lanzaré yo (el tester lo abres tú). Cuando quieras aprobarla, dime expresamente «apruebo la prueba del tester con órdenes simuladas» y esto es lo que hay que hacer:
1. Compilado actual: `uv run python -m xauscalp.mt5_build all --with-exec` (0 errores, 0 avisos). El token **no** hace falta en el tester y **no debe existir**.
2. Probador de estrategias: experto `XauScalp_Exec`, XAUUSD, M1, **«Every tick based on real ticks»** (octubre de 2025; con «1 minute OHLC» también vale como primera pasada), fechas 2025.10.01 – 2025.11.01, sin optimización.
3. Entradas: `InpEnableTrading=true`, `InpTzPolicy=4`, `InpTzBaseMinutes=120`, `InpLogTag=exord1` (nueva en cada ejecución); `InpTesterStopUtc` sin tocar. El EA limpia su estado del tester al arrancar.
4. Al terminar: `uv run python -m xauscalp.mt5_build fetch` y `uv run python -m xauscalp.exec_audit data/mt5/xauscalp/decisions_exord1.csv data/mt5/xauscalp/exec_exord1.csv data/mt5/xauscalp/state_exord1.json --orders` — debe dar «PRUEBA DE ÓRDENES SIMULADAS: SUPERADO».
5. En la pestaña *Resultados* del tester: 0 posiciones abiertas al final, cada operación con SL y TP, cierres por SL/TP/tiempo coherentes con `exec_*.csv`.
6. Es evidencia de nivel 2 **del flujo de ejecución** únicamente (no de desconexiones ni de rentabilidad).

### Reset manual del motor (tras un `LOCKED`)
Solo con la posición ya resuelta a mano en el terminal. Borra, en `Common/Files/xauscalp/`, los ficheros `exec_lock_*` y `exec_inflight_*`
y, en MT5 (F3 → *Variables globales*), las que empiezan por `xauscalp.ex.` (lock, errors, inflight, must_close). **No** borres (en cuenta real, `L`) las
`xauscalp.exdone.*` ni los `exec_done_L.*`: son las sesiones ya operadas (borrarlas permitiría repetirlas). El estado va por cuenta y por
modo (`T` tester / `L` real), de modo que el tester no contamina la DEMO ni al revés. En el tester el EA borra por sí mismo su estado `T` al arrancar, de modo que cada ejecución empieza limpia.

### Procedimiento DEMO manual exigido por la auditoría 3 (antes de cualquier orden)
Fase 1 (≥ 5 días con Londres y NY, `InpEnableTrading=false`): comprobar `STARTED`, `DRYRUN_ORDERCHECK` con retcode y modo de llenado
reales, 0 operaciones en el terminal, y `exec_audit`. Simulacros: cortar la red (deben salir `STALE_*`, 0 errores), cierre limpio y
*force quit* del terminal (ver qué variables globales sobreviven), y cambio de cuenta DEMO. Fase 2 (solo con tu firma, 0,01 lotes,
sesiones atendidas): ver `docs/auditoria_2026-11-12.md`.

## Qué me tienes que pasar
1. La salida completa de `xauscalp.parity` (5.3), y la de 5.4 si la haces.
2. Cualquier error o aviso del *Diario* del tester.
