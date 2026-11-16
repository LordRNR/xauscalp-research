# Plan por fases con criterios verificables

Ninguna fase empieza sin cerrar la anterior. "Cerrar" = criterios cumplidos + informe en
`reports/`. Que un fichero exista **no** significa que funcione.

## Matriz de estado (2026-11-14)

Leyenda: ✅ hecho y comprobado · ⏳ pendiente · — no aplica · ❌ no superado

| Componente | Implementado | Tests Python | Compilado MQL5 | Strategy Tester | DEMO | Validado estadísticamente |
|---|---|---|---|---|---|---|
| Gestor de riesgo Python (fail-closed) | ✅ | ✅ | — | — | — | — |
| Configuración estricta + límites máximos | ✅ | ✅ | — | — | — | — |
| Guardas LIVE (código; la configuración de la herramienta de desarrollo no se publica) | ✅ | ✅ | — | — | — | — |
| Datos Dukascopy + cobertura + segmentos | ✅ | ✅ | — | — | — | — |
| Zona horaria servidor (políticas + inferencia + veredicto de regla) | ✅ | ✅ | — | — | — | ✅ **CONSISTENT**: UE, base 120 (28 semanas confiables) |
| Fuentes MT5 (M1 y ticks) | ✅ (lectores con parada en el límite) | ✅ | — | — | — | — |
| Calidad de ticks (estudio 6) | ✅ | ✅ | — | — | ✅ oct-2025 completo | ❌ un mes: no valida nada |
| Motor de backtest (nivel 1, velas M1) | ✅ | ✅ | — | — | — | — |
| Walk-forward conjunto + benchmarks | ✅ | ✅ | — | — | — | ❌ **NO VALIDABLE** (cobertura 6,9 %) |
| ORB + diagnóstico por día-sesión | ✅ | ✅ | — | — | — | ❌ sin evidencia |
| Script viabilidad / export M1 / export ticks | ✅ | ✅ (estático) | ✅ 0 err / 0 avisos | — | ✅ los tres ejecutados | — |
| Perfil del bróker + estudio 5 | ✅ | ✅ | — | — | ✅ MetaQuotes-Demo | — |
| Herramienta copia/compila/preset/fetch (`mt5_build`) | ✅ | ✅ | ✅ (CLI MetaEditor) | — | — | — |
| EA solo lectura (etapa A) | ✅ | ✅ (estático + espejo de config) | ✅ 0 err / 0 avisos | ✅ 5 ejecuciones | ⏳ | — |
| Paridad Python/MQL5 (etapa B) | ✅ herramienta (ventana explícita, `spread_bar` duro) | ✅ | — | ✅ **EQUIVALENT, 90 sesiones** (`reports/parity/`) | — | — (equivalencia de cálculo, no rentabilidad) |
| Motor de ejecución DEMO (etapa C) | ✅ escrito, **desactivado por defecto** | ✅ estático + especificación + simulación con mocks | ✅ 0 err / 0 avisos (`--with-exec`) | ✅ dry run `exdry2` **SUPERADO** (sin órdenes) | ⏳ | ❌ no aprobado para órdenes (tercera auditoría pendiente de cierre) |
| Calendario de noticias oficial (FOMC/CPI/NFP) | ✅ generador + validación | ✅ | — | — | ⏳ instalado en Common/Files; el usuario debe contrastarlo | ⚠️ solo 3 familias de eventos |
| ORB sobre histórico del bróker (estudio 7) | ✅ | ✅ | — | — | — | ❌ **SIN EVIDENCIA DE VENTAJA NETA** (nivel 1, demo) |
| Alternativas preregistradas (estudio 8: tendencia, momentum, pullback, reversión) | ✅ | ✅ | — | — | — | ❌ **SIN EVIDENCIA** (la tendencia, la más cercana, es sesgo largo 2024-25) |
| Prop firm (FTMO 2-Step): reglas, comprobador, simulación (estudio 9) | ✅ | ✅ | — | — | ⏳ Free Trial (medir contrato/spread/comisión) | ❌ sin ventaja demostrada: no pagar (`docs/07_propfirm_viabilidad.md`) |
| Otros instrumentos (estudio 10: diseño preregistrado y código probado con datos sintéticos; `docs/10_exportacion_multiactivo_y_ftmo.md`) | ✅ código · ⏳ datos | ✅ | ✅ `XAU_SymbolSpecs` 0 err | — | ⏳ el usuario exporta 6 símbolos | ⏳ no ejecutado |
| Logging estructurado del EA | ✅ | — | ✅ | ⏳ | ⏳ | — |
| Dashboard | ⏳ (tras eventos reales) | — | — | — | — | — |
| ML | ⏳ bloqueado (sin baseline validado) | — | — | — | — | — |

## Fases

| Fase | Criterio de salida | Estado |
|---|---|---|
| 0 Viabilidad | Script compilado y ejecutado en la demo; capital mínimo con `OrderCalcProfit/Margin` | ✅ en MetaQuotes-Demo (repetir con el bróker elegido) |
| 1 Investigación | ≥ 2,5 años de M1 bid/ask con cobertura ≥ 90 % en el tramo de investigación; zona horaria del bróker verificada | 🟡 cobertura Dukascopy 6,9 %; zona horaria ✅; M1 del bróker 2021→hoy disponible (otra fuente, ver nota) |
| 2 Prototipo | Reglas exactas, tests verdes | ✅ |
| 3 Backtesting | Criterios de promoción (abajo) con estudio VALIDABLE | ⏳ datos |
| 4 ML | Mejora OOS neta frente al baseline, calibrada | bloqueada |
| 5 Integración MT5 | A: EA lectura compilado · B: paridad equivalente · C: ejecución DEMO (desactivada por defecto) · D: Strategy Tester con ticks reales · auditoría sin CRITICAL | 🟡 A compilado; B pendiente del tester |
| 6 DEMO | Criterios DEMO (abajo) | — |
| 7 Auditoría | Sin CRITICAL/HIGH abiertos | — |
| 8 LIVE | Decisión **solo del usuario** | — |

## Criterios de promoción (Fase 3 → 5) — sin cambios
1. Expectativa OOS > 0 tras costes, límite inferior del IC 95 % (bootstrap semanal) > 0.
2. Supera la dirección aleatoria con p < 0,05 (Bonferroni si se comparan varias).
3. Positiva en ≥ 60 % de los folds donde operó y no depende de un único año.
4. Sigue positiva con costes ×1,5.
5. ≥ 200 operaciones OOS.
6. Monte Carlo: P(drawdown ≥ 16R) < 5 %.
7. **Nuevo**: estudio declarado VALIDABLE (≥ 4 folds con cobertura ≥ 90 %). Esto endurece,
   no relaja, los criterios.

## Criterios DEMO (Fase 6) — sin cambios
≥ 8 semanas y ≥ 100 operaciones; 0 duplicados; 100 % con SL desde la apertura; 0 violaciones
de límites; spread/slippage reales ≤ 1,5× lo modelado; expectativa demo dentro del IC 95 %
del backtest; paridad señal a señal; disponibilidad ≥ 99 % en las ventanas.
Rechazo inmediato: duplicado, orden sin SL, límite violado o expectativa < 0 con p < 0,05.

## Nota sobre el M1 del bróker como histórico de investigación
El export M1 de MetaQuotes-Demo cubre 2021→2026 (2,06 M de velas), mucho más que Dukascopy en
caché. Pero su Ask es **derivado** (bid + spread de la vela, que es el mínimo del minuto),
es el feed de una demo sin ejecución real y los precios difieren de Dukascopy en +0,25 $ de
mediana. Usarlo para investigar exige decidirlo explícitamente (ADR pendiente); no se ha
hecho ningún estudio de rentabilidad con él.

## Siguiente objetivo técnico
Ejecutar el EA en el Strategy Tester (preset ya generado, 2025-09-01 → 2025-10-31, "1 minute
OHLC") y superar la paridad con Python. Solo después se escribe la etapa C (ejecución DEMO,
desactivada por defecto). Pasos exactos: `docs/05_mt5_instalacion_y_pruebas.md`.
