# TFM PoC v2 — propuesta corregida (no validada en Docker)

Esta es una **versión experimental nueva**. No reemplaza la implementación original ni reproduce por definición los porcentajes publicados (66,30 % y 89,99 %). Los CSV históricos se conservan exclusivamente en `legacy_original/` dentro del paquete descargable.

## Cambios implementados

- Edge: `/operational-status` expone latencia reciente y retardo sintético; `/admin/netem` solo acepta `delay_ms` y rechaza jitter/pérdida que no implementa.
- AIOps: consulta disponibilidad y rendimiento, aplica histéresis (3 lecturas), verifica el estado del Gateway antes de registrar una transición, y evita aislar el último nodo.
- MLOps: `/retrain` separa observaciones alternas para entrenamiento y evaluación; la nueva métrica de evaluación se distingue de la de entrenamiento. Esta partición simple es **solo una mejora preliminar**: para rigor científico debe sustituirse por un conjunto de prueba fijo e independiente, especialmente si hay dependencia temporal.
- Generador: semillas configurables, escenarios E0/E1/E2 separados y salida aislada. El cliente es secuencial: **no garantiza** 15 RPS bajo latencias elevadas.
- Compose: proyecto independiente, sin privilegio NET_ADMIN innecesario, resultados separados y contraseña Grafana configurable.

## Ejecución (requiere Docker Compose v2)

```bash
cp .env.example .env
# Cambiar GRAFANA_ADMIN_PASSWORD en .env
./scripts/run_E0.sh
python3 scripts/validate_results.py results_v2/E0.csv
./scripts/run_E1.sh
python3 scripts/validate_results.py results_v2/E1.csv
./scripts/run_E2.sh
python3 scripts/validate_results.py results_v2/E2.csv
```

Cada escenario elimina los volúmenes **de v2** al comenzar para reiniciar el estado de MLflow/Prometheus/Grafana; esto elimina los datos previos de esos servicios. El script **no sobrescribe** un CSV E0/E1/E2 existente; archívalo antes de repetir. Los puertos 8080, 5000, 9090 y 3000 deben estar libres.

- E0: tráfico nominal, sin controladores ni fallos.
- E1: drift a los 35 s y MLOps habilitado; no inyecta degradación Edge.
- E2: retardo sintético de 180 ms en Edge1 desde 35 s durante 25 s; AIOps habilitado; MLOps deshabilitado.

**Limitaciones:** la señal de retardo configurado se usa explícitamente para detectar la degradación simulada; esto valida la orquestación de una PoC, **no** constituye detección de anomalías basada en IA. La precisión se calcula con etiquetas disponibles en el mismo momento de la inferencia. El mecanismo de retardo no es `tc/netem` de red real. La ventana de latencias y la partición alterna son demostrativas. Es necesario ejecutar pruebas de integración y verificar las transiciones E2 en los logs.

## Evidencias

- `results_v2/E0.csv`, `E1.csv`, `E2.csv`: resultados nuevos.
- `results_v2/logs_E*/`: configuración resuelta y logs del servicio (si la ejecución finaliza normalmente).
- `python3 scripts/validate_results.py ...`: resumen estadístico simple.

## Validación

Se han comprobado sintaxis Python y estructura estática. **No se ha podido ejecutar Docker en este entorno.** La aceptación definitiva requiere ejecutar los tres scripts, inspeccionar logs AIOps/MLOps y contrastar los resultados.
