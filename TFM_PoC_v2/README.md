# PoC Docker: integración MLOps-AIOps para Edge

Esta prueba de concepto despliega una arquitectura distribuida con dos nodos Edge, un gateway adaptativo, controladores MLOps y AIOps, MLflow, Prometheus y Grafana.

## Servicios

- `edge1`, `edge2`: inferencia y reentrenamiento local; permiten inyectar latencia/pérdida con Linux `tc/netem`.
- `gateway`: balanceo entre nodos y aislamiento/restauración de rutas.
- `mlops-controller`: detecta caída de accuracy, ejecuta reentrenamiento y registra el experimento en MLflow.
- `aiops-controller`: detecta degradación de salud/latencia y retira temporalmente el nodo afectado.
- `traffic-generator`: genera tráfico, introduce drift y congestión controlada.
- `prometheus`, `grafana`: observabilidad.
- `mlflow`: trazabilidad de reentrenamientos.

## Requisitos

- Docker Engine 24+ y Docker Compose v2.
- Linux recomendado. `NET_ADMIN` es necesario para `tc/netem` dentro de los nodos Edge.
- Puertos libres: 3000, 5000, 8080 y 9090.

## Ejecución

```bash
./scripts/run_experiment.sh
```

Interfaces:

- Gateway: http://localhost:8080/health
- Grafana: http://localhost:3000 (`admin` / `admin`)
- MLflow: http://localhost:5000
- Prometheus: http://localhost:9090

El experimento dura 120 segundos:

1. 0-35 s: distribución estable.
2. 35 s: cambia el umbral real de clasificación y aparece drift.
3. 65 s: se inyectan 180 ms de retardo, 30 ms de jitter y 1 % de pérdida en `edge1`.
4. 90 s: se elimina la degradación de red.

Los resultados por solicitud se guardan en `results/requests.csv`.

## Escenario de control sin automatización

Para obtener una línea base, detenga los controladores y ejecute el generador:

```bash
docker compose stop mlops-controller aiops-controller
docker compose --profile experiment run --rm traffic-generator
mv results/requests.csv results/requests_baseline.csv
```

Después, reinicie los controladores y repita:

```bash
docker compose start mlops-controller aiops-controller
docker compose --profile experiment run --rm traffic-generator
mv results/requests.csv results/requests_propuesta.csv
```

## Limitaciones

La PoC no representa el plano radio completo de una red 6G. Docker reproduce la separación de servicios y la coordinación funcional, mientras que `tc/netem` introduce condiciones de red controladas. Los resultados deben presentarse como validación funcional y reproducible de la arquitectura, no como mediciones de una red 6G comercial.

## Diagnóstico cuando los paneles aparecen vacíos

La observabilidad necesita tráfico. Ejecute el experimento completo con:

```bash
./scripts/run_experiment.sh
```

También puede generar tráfico manualmente:

```bash
docker compose run --rm traffic-generator
```

Comprobaciones rápidas:

```bash
# Estado de los contenedores
docker compose ps

# Targets que Prometheus está recopilando
curl http://localhost:9090/api/v1/targets

# Métricas expuestas directamente
curl http://localhost:8080/metrics
curl http://localhost:8080/health

# Logs de los controladores
docker compose logs -f mlops-controller aiops-controller
```

En Prometheus, abra `http://localhost:9090/targets`. Los targets `gateway`, `edge1` y `edge2` deben aparecer con estado **UP**.

Grafana aprovisiona automáticamente el datasource Prometheus y el dashboard **TFM - MLOps y AIOps**, dentro de la carpeta **TFM MLOps-AIOps**.

MLflow crea una ejecución de monitorización al iniciar el controlador MLOps. Las métricas de accuracy y threshold aparecen aunque todavía no se haya activado un reentrenamiento.

Si se había levantado una versión anterior, elimine los volúmenes para evitar configuraciones persistidas antiguas:

```bash
docker compose down -v
docker compose up -d --build
./scripts/run_experiment.sh
```
