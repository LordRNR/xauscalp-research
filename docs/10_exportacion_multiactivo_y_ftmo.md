# Exportación de datos: otros instrumentos (MetaQuotes-Demo) y recopilación en la Free Trial de FTMO

> **Nota sobre este repositorio / Note on this repository.** Este documento menciona el componente de ejecución de órdenes (`XauScalp_Exec.mq5`, `ExecEngine.mqh`, `xauscalp.exec_audit` y `reports/exec_dryrun/`), que **no se publica aquí**. Las menciones se conservan como registro histórico del proyecto; los procedimientos y comandos que dependen de él no se pueden ejecutar con este repositorio. *This document refers to the order-sending component, which is not published here. The references are kept as a historical record; procedures that depend on it cannot be run from this repository.*

**Nada de esto envía órdenes.** Solo se usan scripts de lectura (`XAU_SymbolSpecs`, `XAU_ExportHistory`, `XAU_ExportTicks`, `XAU_FeasibilityReport` — este último solo
llama a `OrderCheck`, que valida sin enviar). No actives `InpEnableTrading`, no adjuntes `XauScalp_Exec` y no crees ningún fichero de autorización.

## A. Datos para la investigación multiactivo (MetaQuotes-Demo, periodo de investigación solamente)
Objetivo: `EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, XAGUSD` (además del `XAUUSD` que ya tienes). Diseño y criterios: `docs/08_hipotesis_multiactivo.md` (preregistrado).

1. **Comprueba los nombres**: en MT5, *Ver → Símbolos* (Ctrl+U) y busca cada uno; anota el nombre exacto (algunos servidores añaden sufijos). Si falta alguno, dímelo: el estudio exige ≥ 4 símbolos.
2. **Especificaciones de contrato (una sola ejecución para todos)**: *Navegador → Scripts → XAU_SymbolSpecs* (doble clic).
   `InpSymbols` = `EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,XAUUSD,XAGUSD` (con tus nombres exactos), `InpTag` = `mqdemo` → Aceptar. Resultado: `Common/Files/xauscalp/symbol_specs_mqdemo.csv`.
3. **Histórico M1 de cada símbolo** (repite 6 veces): script `XAU_ExportHistory` con
   - `InpSymbol` = el símbolo; `InpFrom` = `2021.01.01`; **`InpTo` = `2025.11.01`** (así el fichero **no contiene nada** del periodo reservado: el export del oro sí lo contiene y los lectores tienen que recortarlo).
   - Antes de lanzar cada uno, abre un gráfico M1 de ese símbolo y desplázate hasta 2021 para que MT5 descargue el historial (con «Máx. barras en ventana» = Unlimited, ya configurado). Si el servidor no tiene historial desde 2021, el fichero empezará más tarde: anota la fecha de inicio que imprime el script.
4. En el Mac: `uv run python -m xauscalp.mt5_build fetch` (copia a `data/mt5/`; los ficheros no se versionan).
5. **Previsualiza la viabilidad de contrato** (sin estrategia): `uv run python -m xauscalp.symbol_specs data/mt5/xauscalp/symbol_specs_mqdemo.csv --capital 1000 --risk-pct 0.5 --sl XAUUSD=12,EURUSD=0.0030,GBPUSD=0.0035,USDJPY=0.45,AUDUSD=0.0025,USDCAD=0.0035,XAGUSD=0.60`
   (las distancias son solo orientativas; el estudio usa 3×ATR diario medido de los datos).
6. **Verifica la zona horaria** con un símbolo nuevo: `uv run python research/04_verify_server_tz.py data/mt5/EURUSD_M1_*.csv` (debe dar la misma regla `base_dst:120:Europe/London`).
7. Cuando estén los ficheros, **dímelo** y ejecuto `research/10_multiasset.py` (ya escrito, probado con datos sintéticos, se niega a correr con menos de 4 símbolos).

Qué NO cubre: los swaps por mantener posiciones (en horizontes de días importan) se estimarán con los de un bróker real; los spreads de MetaQuotes-Demo no son los de un bróker regulado.

## B. Recopilación en la Free Trial de FTMO (solo datos de mercado y características del contrato)
Has confirmado que cada Free Trial dura **14 días y puede repetirse** (la página de FTMO que leí decía «No time limit»: vale lo que tú hayas visto al registrarte).
Es una cuenta de **prueba con fondos simulados**: no compres nada, no introduzcas medios de pago.

1. Regístrate en la Free Trial; **las credenciales de la cuenta no se comparten conmigo ni se guardan en el repositorio**.
2. En MT5: *Archivo → Abrir una cuenta*, busca el servidor de FTMO e inicia sesión. Apunta (sin el número de cuenta): nombre del servidor, divisa de la cuenta, apalancamiento, tipo de cuenta (hedging/netting).
3. **Antes de nada, guarda la copia de MetaQuotes**: `cp data/mt5/xau_feasibility.csv data/mt5/xau_feasibility_mqdemo.csv` (el siguiente `fetch` sobrescribiría el original).
4. Ejecuta `XAU_FeasibilityReport` (valida con `OrderCheck`, no envía) y `XAU_SymbolSpecs` con `InpTag` = `ftmo` y los símbolos que FTMO use (oro, plata, pares de FX…): contrato, lote mínimo, tick value, spread actual, swaps y margen **de su servidor**.
5. **Spreads reales**: ejecuta `XAU_ExportTicks` de XAUUSD para **1–2 semanas recientes** (cambia `InpFrom`/`InpTo`; los valores por defecto son los de octubre de 2025) y analiza **solo spreads** con
   `uv run python research/11_cost_calibration.py data/mt5/XAUUSD_ticks_<desde>_<hasta>.csv --label ftmo` (esa herramienta no calcula rentabilidad: por eso puede leer fechas recientes sin tocar el candado del periodo reservado).
6. **A mano** (no está en la API de MQL5): comisión por lote del oro en FTMO (especificación del símbolo en la plataforma o primer extracto), swaps, apalancamiento por activo y la lista de **«eventos restringidos»** del calendario económico de su plataforma. Anótalo en `config/propfirm_ftmo_2step.yaml`, sección `unverified` (quita lo confirmado y apunta la fuente y la fecha).
7. Cierra con: el nombre real del tamaño de contrato, el lote mínimo y el spread mediano en horas de Londres/Nueva York frente a los 0,17 $ de MetaQuotes-Demo. Esos números sustituyen los supuestos del modelo de costes **solo cuando los confirme una cuenta real**; una Free Trial es evidencia, no prueba.
8. **Opcional, sin órdenes**: dry run de solo lectura con `XauScalp_ReadOnly` (no incluye código de órdenes) durante los 14 días, para ver señales, motivos de rechazo y spreads de tu servidor.

**Lo que NO se hace en ninguna Free Trial hasta nueva decisión tuya**: operar, activar `InpEnableTrading`, adjuntar `XauScalp_Exec`, crear `EXEC_DEMO_AUTHORIZED` o comprar un challenge.
