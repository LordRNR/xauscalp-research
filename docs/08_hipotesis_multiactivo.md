# Investigación en otros instrumentos — hipótesis y criterios PREREGISTRADOS (sin datos todavía)

**Fecha de registro: 2026-11-15.** Estado: **diseño listo, NO ejecutado**. Hacen falta datos de otros instrumentos y hoy solo hay
XAUUSD. No se descargan de forma indefinida de ningún proveedor: los exporta el usuario desde MT5 (procedimiento abajo). Este
documento se congela antes de ver ningún resultado; los cambios se hacen en una versión nueva fechada.

## Por qué otros instrumentos
En el oro, ninguna familia (ORB, Donchian, momentum, pullback, reversión) mostró ventaja neta (estudios 7 y 8); la única señal cercana
era exposición larga al mercado alcista de 2024-25. La literatura de *time-series momentum* (Moskowitz–Ooi–Pedersen 2012; Hurst–Ooi–Pedersen
2017) describe un efecto **diversificado entre muchos activos**, débil en uno solo y dominado por las tendencias largas. Con 1.000-10.000 € no
se puede esperar que un único activo lo capture; probar una cesta es la hipótesis nueva y justificada.

## Datos necesarios (los exporta el usuario, periodo de investigación solamente)
Con el script que ya existe `XAU_ExportHistory` (parámetro `InpSymbol`), desde MetaQuotes-Demo, M1, `InpFrom=2021.01.01`, `InpTo=2025.11.01`
(el periodo reservado empieza el 2025-11-01; el export de ejemplo ya contiene fechas posteriores y los lectores se detienen en el límite):
EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, XAGUSD, y un índice (US500 o similar) y petróleo si aparecen en *Market Watch*. Los nombres cambian
según el servidor: comprueba el símbolo exacto. Ficheros ≈ 100 MB cada uno, no se versionan.
Antes de usarlos hay que repetir la verificación de zona horaria (`research/04`) y la de cobertura por símbolo. Los **spreads de MetaQuotes-Demo
no son los de un bróker real**: el modelo de costes se define **relativo al spread mediano** de cada símbolo (abajo).

## Hipótesis (mecanismo, señal, rejilla cerrada)
**M1 — Momentum de series temporales diversificado.** *Mecanismo*: persistencia de retornos a 1-12 meses por flujos y reacción lenta a la información,
más fuerte promediada entre activos poco correlados. *Señal* (barras diarias construidas desde M1, decisión al cierre de las 21:00 UTC, ejecución a la
apertura siguiente): signo del retorno de las últimas L sesiones. *Rejilla*: L ∈ {60, 120, 250}; mantener H ∈ {5, 20} sesiones; SL = 3 ATR(14) diario.
Cada activo con **riesgo igual** (1R) y cartera igual ponderada; 6 configuraciones.
**M2 — Tendencia por ruptura de Donchian diaria sobre la cesta.** N ∈ {50, 100, 200} sesiones, SL ∈ {2, 3} ATR(14) diario, salida por tiempo a 60 sesiones;
6 configuraciones. *Mecanismo*: seguimiento de tendencia clásico (Faber, Turtles).
**M3 — Reversión de divisas en rango (FX solamente).** z-score de 24 h en M15 con filtro de eficiencia < 0,30 (igual a H4 del estudio 8 pero en FX, donde
la literatura de microestructura la apoya a horizontes cortos). 6 configuraciones.
Total **18 configuraciones × cesta**; la **cesta** (no cada activo) es la unidad de evaluación.

## Costes (relativos al spread mediano `s` de cada símbolo, fijados antes)
A = spread del dato; **B (base) = spread del dato + 1,0·s extra + deslizamiento 0,5·s por orden + comisión de 7 USD/lote ida y vuelta**;
C (estrés) = + 2,0·s extra + 1,0·s de deslizamiento. En FX el contrato es de 100.000 unidades (comisión por lote → en unidades de precio con ese tamaño).
Los swaps por mantener posiciones **no están modelados** y en horizontes de días importan: se reportan como límite y se estimarán con el campo `swap` del
bróker real antes de cualquier decisión.

## Protocolo y criterios de aceptación (TODOS, sobre la ejecución B)
Mismo walk-forward (12 m / 3 m, abstención si la expectativa de entrenamiento ≤ 0, una simulación conjunta por **cartera**, una posición por activo,
riesgo total simultáneo ≤ el límite del proyecto), con cobertura mínima del 90 % por fold y símbolo. Una cesta se declara «con evidencia» solo si:
1. ≥ 4 folds válidos y ≥ 200 operaciones OOS en la cartera;
2. IC95 (bloques semanales) de la expectativa neta en R con límite inferior > 0;
3. p frente a **tres** controles < 0,05/3 (Bonferroni): dirección aleatoria, **siempre largo** con las mismas señales y horas, y **tiempos de entrada aleatorios** con la misma mezcla
   de direcciones (el control que faltó en el oro: elimina la deriva de mercado);
4. expectativa > 0 con costes C;
5. positiva en ≥ 60 % de los folds y en ≥ 3 de los 5 años, **y** en ≥ 60 % de los activos con operaciones (no la sostiene uno solo);
6. dirección invertida < 0 y expectativa a coste cero > expectativa con costes;
7. reproducible (mismo hash de operaciones en dos ejecuciones).
Si no se cumple: **«SIN EVIDENCIA»**. Aun cumpliéndolo solo sería candidata a **una** confirmación en el periodo reservado, que únicamente abre el usuario
(`XAU_UNLOCK_HOLDOUT`, un solo uso), y después a una prueba gratuita/DEMO. Nada de esto autoriza ejecución.

## Qué NO se hace
Añadir activos o parámetros después de ver resultados; elegir el mejor activo; medir por porcentaje de acierto; tocar el periodo reservado; ajustar nada para pasar
un challenge (el objetivo es la ventaja estadística, no aprobar una evaluación).
