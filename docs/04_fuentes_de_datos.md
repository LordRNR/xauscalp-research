# Fuentes de datos para XAUUSD

Todas las fuentes entran por `src/xauscalp/data/sources.py` y entregan el mismo formato
canónico (M1 Bid/Ask, índice UTC) más sus **metadatos de calidad**, que deben citarse junto
a cualquier resultado.

| Fuente | Coste | Granularidad | Bid/Ask | Zona horaria | Cobertura | Limitaciones |
|---|---|---|---|---|---|---|
| **Dukascopy** (implementada) | Gratis | M1 (también ticks por hora) | Bid **y** Ask reales | UTC | Años | Limita peticiones (HTTP 429, cortes). No son los precios de tu bróker: spread más estrecho → se añade spread extra. Uso personal; no redistribuir. |
| **MT5 M1 del bróker** (`XAU_ExportHistory.mq5`, implementada) | Gratis | M1 | Bid OHLC + campo `spread` por barra → **Ask derivado** (optimista: a menudo es el spread mínimo de la barra) | Hora del **servidor**: exige política verificada | Depende del servidor | Profundidad limitada por el bróker y por "Max bars" del terminal. |
| **MT5 ticks del bróker** (`XAU_ExportTicks.mq5` + `CopyTicksRange`, implementada) | Gratis | Tick → M1 exacto | Bid y Ask reales de cada cotización | Hora del servidor (ms) | Normalmente meses, a veces más (depende del servidor) | Ficheros grandes; el script informa de los días sin ticks. |
| **Strategy Tester "Every tick based on real ticks"** | Gratis | Tick | Reales del bróker | Servidor | La del historial de ticks del bróker | Si no hay ticks reales, MT5 los **genera** a partir de M1: eso **no** es nivel 2 de evidencia. |
| HistData.com (no implementada) | Gratis | M1 | Solo Bid (según un *wrapper* de terceros; **no verificado** en la web oficial) | EST sin horario de verano (misma fuente) | Años | Sin Ask → no sirve para costes reales. |
| Forex Tester (no implementada) | Gratis (descarga) | M1 | Bid | GMT sin DST (según su web) | Años | Sin Ask. |
| Yahoo `GC=F` | Gratis | 1 min solo para días recientes | Futuros, no CFD | — | Muy corta | Instrumento distinto. Descartada. |
| Proveedores de pago | € | Ticks | Sí | — | Años | No imprescindibles. |

Hechos verificados en la documentación oficial de MQL5:
- `TimeGMT()` se calcula con el reloj local del PC y **en el Strategy Tester es igual a
  `TimeTradeServer()`** → en el tester no existe una forma de deducir UTC; hay que declarar
  la regla del servidor, verificada antes con `research/04_verify_server_tz.py`.
- `CopyTicksRange(symbol, ticks[], flags, from_msc, to_msc)` usa milisegundos desde 1970,
  ambos extremos inclusive; `COPY_TICKS_INFO` devuelve los ticks con cambios de Bid/Ask.

## Recomendación

1. **Investigación de largo plazo**: Dukascopy (es la única fuente gratuita con Bid y Ask
   reales y años de historia). Descargar de noche con el CLI (se detiene solo si la
   fuente limita).
2. **Costes reales y zona horaria**: export M1 y ticks del bróker; comparar spreads con
   Dukascopy y calibrar `costs.extra_spread_usd`.
3. **Nivel 2 de evidencia**: Strategy Tester con ticks reales en los meses con historial
   de ticks del servidor.

Nunca se sustituyen ticks por velas sin decirlo: cada resultado lleva `meta.granularity`,
`meta.ask_source` y el nivel de evidencia.
