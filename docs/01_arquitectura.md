# Arquitectura

## Comparativa

| Criterio | A. Solo MQL5 | B. Python + paquete MetaTrader5 | C. Híbrida clásica (Python decide, MQL5 ejecuta vía IPC) | **D. Híbrida "compilada"** (Python investiga → MQL5 ejecuta reglas/ONNX dentro de MT5) |
|---|---|---|---|---|
| Latencia | Mínima (en el terminal) | +IPC (ms) | +IPC/sockets | Mínima |
| Fiabilidad de ejecución | Alta | Si Python cae, nadie gestiona | Dos procesos que sincronizar | Alta: un proceso en el terminal |
| Calidad de pruebas | Strategy Tester con ticks reales | Backtester propio | Difícil probar el conjunto | **Ambas**: Python (rápido, estadístico) + Strategy Tester con ticks reales del bróker |
| macOS | Sí (MT5 para macOS) | **No** (wheels solo Windows) | Parcial | **Sí** |
| Facilidad desarrollo | Baja para investigación | Alta | Media | Alta en investigación, media en ejecución |
| CPU/RAM | Muy bajo | Medio | Medio | Muy bajo en vivo |
| Coste | 0 € | 0 € | 0 € | 0 € |
| Autonomía | Alta | Media | Media | Alta |
| Dependencias externas | Ninguna | Windows | Varias | Ninguna en vivo |
| Integración ML | Pobre (salvo ONNX) | Total | Total | Total vía **ONNX** nativo de MQL5 |

**Elegida: D.** Investigación, backtesting, validación estadística y entrenamiento en
Python (Mac). El sistema en vivo es un **EA de MQL5** que contiene las reglas de la
estrategia, el gestor de riesgo (última línea de defensa) y, si la Fase 4 lo justifica, un
modelo exportado a ONNX. Ventajas medibles: misma lógica probada en el Strategy Tester con
los ticks reales de *tu* bróker, cero IPC, funciona en macOS, sin procesos que puedan caerse
por separado. Coste: la lógica de la estrategia existe dos veces (Python y MQL5) → se
mitiga manteniéndola simple y con un **test de paridad** (mismas señales en el mismo periodo).

```
            ┌──────────── Mac (investigación) ────────────┐
 Dukascopy ─┤ data → features → regime → strategy/model    │
 export MT5 ┤ → backtest (bid/ask, costes) → walk-forward   │──► params.json / model.onnx
            │ → reports/                                    │
            └───────────────────────────────────────────────┘
            ┌──────────── MetaTrader 5 (DEMO) ─────────────┐
            │ EA: MarketData → Features → Regime → Signal   │
            │     → RiskManager (veto) → Execution          │──► Common/Files/state.json,
            │     → PositionManager → Logger                │    decisions.csv, trades.csv
            └───────────────────────────────────────────────┘
                      │                         │
              Streamlit dashboard        Telegram (opcional, WebRequest)
```

Módulos (sección 8 del encargo) y dónde viven:

| Módulo | Python (investigación) | MQL5 (vivo, Fase 5) |
|---|---|---|
| 1 Market Data | `data/dukascopy.py`, `data/quality.py`, `mt5_report.py` | ticks/rates + compuertas de datos obsoletos |
| 2 Features | `features/core.py`, `features/sessions.py` | mismo cálculo, test de paridad |
| 3 Régimen | `regime.py` | idem |
| 4 Estrategia/Predicción | `strategies/` (+ `models/` en Fase 4) | reglas / ONNX |
| 5 Risk Manager | `risk/manager.py`, `risk/sizing.py` | `Include/RiskManager.mqh` (veto final) |
| 6 Ejecución | — | `Include/Execution.mqh` |
| 7 Posiciones | — | `Include/PositionManager.mqh` |
| 8 Monitorización | `reports/`, `dashboard/` | logs estructurados en Common/Files |

## Programas

| Uso | Programa | Coste | Estado |
|---|---|---|---|
| **Trading** | MetaTrader 5 para macOS (MetaQuotes) o la versión de tu bróker | Gratis | ❌ no instalado en el Mac |
| **Desarrollo** | VS Code + Claude Code; Python 3.12 + `uv`; Git; MetaEditor (viene con MT5) | Gratis | ✅ salvo MetaEditor |
| **Seguimiento** | App MT5 móvil (iOS/Android) + dashboard Streamlit local; Telegram opcional | Gratis | Fase 6 |
| Datos | Dukascopy (gratis, con límite de peticiones) + export de tu bróker | Gratis | ✅ en curso |

## Dónde se ejecuta

- **Mac** (M5, ~5 W): ideal para investigación; para el EA en demo funciona si no se
  duerme (`caffeinate` o Ajustes → Batería). Coste eléctrico despreciable.
- **PC Ryzen**: SO no verificado. Si es Windows, MT5 corre nativo y es el mejor candidato
  para un demo 24/5, pero consume ~60–100 W en reposo (≈ 5–10 €/mes de luz a 24/5). Para
  una estrategia que solo opera en las aperturas, basta encenderlo en esas ventanas.
- **VPS**: no contratado. El VPS de MetaQuotes cuesta aprox. 10–15 $/mes (verificar),
  desproporcionado frente a un capital reducido.
- **Modo por horarios** (recomendado): el EA solo abre en ventanas definidas y la estrategia
  cierra por tiempo (≤ 90 min) → nunca quedan posiciones abiertas al apagar; SL/TP viven
  en el servidor del bróker desde la apertura por si el equipo se cae.
