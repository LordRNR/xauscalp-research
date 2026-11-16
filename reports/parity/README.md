# Paridad Python ↔ MQL5 (ORB, solo lectura) — resultado formal

**Fecha del resultado:** 2026-11-14 · **Nivel de evidencia:** 1 (velas M1 del bróker; el Strategy Tester
genera los ticks desde las mismas velas, modelado «1 minute OHLC»).

## Resultado
`uv run python -m xauscalp.parity --ea decisions_parity5_… --broker-m1 XAUUSD_M1_20210101_20261113.csv
--tz base_dst:120:Europe/London --from 2025-09-01 --to 2025-10-31` → **EQUIVALENT on 90 day-sessions**:
88 SIGNAL + 2 NO_BREAKOUT, 0 diferencias duras, 0 sensibles al spread, 0 filas sin correspondencia.
`spread_now` del EA = spread de la vela siguiente según Python en 88/88 (información, no criterio).
Reverificado de forma independiente por el asistente sobre el CSV de este directorio (misma salida).

## Qué significa y qué NO
- **Significa**: el EA `XauScalp_ReadOnly` y `orb_scan()` calculan lo mismo (estado, dirección, vela de
  decisión, rango de apertura, ATR M5, distancia de SL, spread de la vela) sobre los mismos datos, en
  sep–oct 2025, con zona horaria `base_dst:120:Europe/London` verificada (estudio 4).
- **No significa**: rentabilidad, ventaja estadística ni validez fuera de esas 90 sesiones. El disparador
  ORB salta casi todas las sesiones (88/90), así que la paridad de señales no es selectiva. No hay
  P&L en esta prueba y no se tocó el periodo reservado (≥ 2025-11-01).
- Tampoco prueba la ejecución de órdenes: el EA no contiene código de trading.

## Historial de ejecuciones (todas con el mismo preset salvo donde se indica)
| Etiqueta | Resultado | Causa / nota |
|---|---|---|
| parity1 | no interpretable | registro con filas duplicadas (misma etiqueta usada dos veces) |
| parity2 | 2 diferencias duras (ATR) + 2 sesiones sin EA | ventana de ATR de 502×300 s en tiempo natural (~110 barras los lunes); tester acaba el 30-oct |
| parity3 | 0 diferencias duras; faltan las 2 del 31-oct | ATR corregido (10 días, ≥ 300 barras); fecha final del tester excluida |
| parity4 | parcial (diagnóstico del 31-oct) | no usada como evidencia |
| **parity5** | **EQUIVALENT, 90 sesiones** | tester «Hasta 2025.11.01» |

## Ficheros (evidencia conservada)
- `decisions_parity5_2025-09-01_2025-10-31.csv` — registro de decisiones del EA (sin cuenta ni credenciales;
  `mode=TESTER`; el volumen es 0 y `risk_approved=0` porque el EA no opera y el calendario aún no se usaba).
- `python_expected_2025-09-01_2025-10-31.csv` — lo que Python espera para las mismas sesiones.
- `state_parity5.json` — estado final del EA (`read_only: true`, 0 órdenes).
- SHA-256: ver `SHA256SUMS`. Entrada: export M1 del bróker `XAUUSD_M1_20210101_20261113.csv`
  (SHA-256 `8a1e75fd2ab69486a3dd8b8d8e1dd408dec77760b02903f8ff2264310a61c80b`, no versionado por tamaño).
- Versiones: commit del código en `git log` (ver `docs/decisiones.md` ADR 29–32).

## Reproducir
Pasos en `docs/05_mt5_instalacion_y_pruebas.md` §5. Cada ejecución del tester necesita otra `InpLogTag`.
