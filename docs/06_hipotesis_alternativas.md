# Estrategias alternativas para XAUUSD — hipótesis y criterios PREREGISTRADOS

**Fecha de registro: 2026-11-15, antes de ejecutar ningún experimento de esta familia.** Este documento y
`src/xauscalp/strategies/alt.py` se suben al repositorio en el mismo commit y **no se modifican después de ver
resultados**: si algo cambia, se escribe una nueva versión fechada y el resultado anterior se conserva.
Contexto: la ORB no mostró ventaja neta (estudio 7, ADR 33) y no se sigue optimizando sin hipótesis nueva.

## Datos, protocolo y costes (iguales para todas las familias)
- **Datos**: M1 del bróker (MetaQuotes-Demo, 2021-01 → 2025-10, cobertura 98 %), tramo de investigación; el periodo
  reservado (≥ 2025-11-01) **no se lee**. Ask = Bid + spread de la vela (suelo optimista). Nivel de evidencia 1.
- **Walk-forward**: entrenamiento 12 meses / prueba 3 meses (15 folds válidos), selección por expectativa neta en
  entrenamiento dentro de cada familia, mínimo 30 operaciones, **se abstiene** si la mejor expectativa de entrenamiento
  es ≤ 0. Resultado final = **una** simulación conjunta cronológica con una posición, benchmarks sobre las mismas señales.
- **Costes** (fijados, no ajustados): A = demo tal cual (spread extra 0, deslizamiento 0,05, comisión 0);
  **B = base (extra 0,15 $, deslizamiento 0,10 $, comisión 7 $/lote ida y vuelta)**; C = estrés (0,30 / 0,30 / 7).
  El veredicto se decide con **B**, con C como prueba de robustez.
- Sin filtro de noticias en estas familias (horizontes largos: un filtro de ±2 h no es comparable). Se anota como límite.
- **Salidas simplificadas** (limitación declarada): SL fijo en múltiplos de ATR, TP opcional y salida por tiempo; no hay
  trailing stop (el motor de nivel 1 no lo modela).
- Parámetros en unidades de ATR o de barras, nunca en dólares. Sesgo de decisión: se decide al **cierre** de la barra y se
  ejecuta en la apertura de la siguiente M1 (igual que el resto del motor).

## Hipótesis (mecanismo económico, señal, rejilla)
Cada familia tiene una rejilla pequeña **cerrada**. Total: **22 configuraciones** (6 + 6 + 4 + 6).

**H1 — Tendencia (ruptura de Donchian en H1).** *Mecanismo*: el oro muestra persistencia a horizontes de días
(flujos de refugio, tipos reales, bancos centrales). *Señal*: cierre H1 por encima del máximo de las N barras previas →
largo; por debajo del mínimo → corto. *Rejilla*: N ∈ {24, 48, 96} barras H1 × SL ∈ {2, 3} ATR(H1,14). Sin TP;
salida por tiempo a 120 h. *Signo esperado*: positivo en largo plazo, con muchas pérdidas pequeñas.

**H2 — Momentum de series temporales.** *Mecanismo*: el signo del retorno pasado predice el siguiente a escala de
días/semanas (Moskowitz–Ooi–Pedersen en materias primas). *Señal*: una vez al día, al cierre de la barra H1 de las
07:00–08:00 UTC, dirección = signo del retorno de las últimas L horas. *Rejilla*: L ∈ {24, 72, 168} h × mantener
H ∈ {24, 48} h; SL 3 ATR(H1). Sin TP. *Signo esperado*: débilmente positivo.

**H3 — Retroceso en tendencia (pullback).** *Mecanismo*: dentro de una tendencia establecida los retrocesos se compran.
*Señal*: tendencia = EMA50 > EMA200 y cierre > EMA200 en H1 (corto: simétrico); entrada cuando el RSI(14) de H1 vuelve a
cruzar 40 al alza tras estar por debajo (corto: cruza 60 a la baja). *Rejilla*: SL ∈ {1,5; 2,5} ATR(H1) × TP ∈ {1,5; 2,5} R;
salida por tiempo a 48 h. *Signo esperado*: positivo moderado.

**H4 — Reversión a la media en rango.** *Mecanismo*: en régimen sin tendencia el precio vuelve a su media tras excesos
de liquidez. *Señal* (M15): z-score del cierre frente a la media/desviación de las últimas 96 barras (24 h); solo si el
ratio de eficiencia de Kaufman de 96 barras < 0,30 (rango). Contra la desviación cuando |z| ≥ Z. *Rejilla*:
Z ∈ {2,0; 2,5; 3,0} × SL ∈ {2; 3} ATR(M15,14). TP = distancia a la media en la señal; salida por tiempo a 12 h.
*Signo esperado*: positivo, con riesgo de cola (sin trailing, el SL no protege de rachas).

## Criterios de aceptación (TODOS, sobre la ejecución primaria B)
Una familia **solo** se declara «con evidencia de ventaja neta» si cumple a la vez:
1. **Validable**: ≥ 4 folds con cobertura ≥ 90 % (se esperan 15).
2. **≥ 150 operaciones** OOS válidas.
3. **IC95 (bloques semanales) de la expectativa neta en R con límite inferior > 0.**
4. **p frente a dirección aleatoria < 0,0125** (= 0,05 / 4 familias, Bonferroni).
5. **Expectativa > 0 también con costes C (estrés).**
6. **Consistencia temporal**: resultado neto positivo en ≥ 60 % de los folds OOS con operaciones y en ≥ 3 de los 5
   años naturales (2021–2025).
7. **La dirección importa**: la expectativa con la dirección invertida es < 0 (si invertir también gana, no hay señal).
8. **Reproducible**: dos ejecuciones dan el mismo hash de operaciones (semilla fija, código en el commit del registro).
Si ninguna familia lo cumple, el resultado es **«SIN EVIDENCIA»**, válido y publicable. **Ningún resultado de esta
investigación autoriza ejecución**: una familia que pase solo sería *candidata* a **una** confirmación en el periodo
reservado, que únicamente el usuario puede desbloquear (`XAU_UNLOCK_HOLDOUT`, un solo uso), y después a DEMO.

## Qué NO se hace
No se añaden familias, parámetros ni filtros tras ver resultados; no se elige «la mejor de las 22» (se informa de las 22,
sabiendo que el máximo está sesgado al alza); no se usan porcentajes de acierto como criterio; no se toca el periodo reservado.
Viabilidad de capital (riesgo 0,5 % con 0,01 lotes) se informa **aparte**: con SL de 2–3 ATR(H1) el riesgo mínimo supera el
capital de referencia de 1.000 €, de modo que aun con ventaja estadística la ejecución exigiría más capital o menos apalancamiento.
