# Agent Request

## From
Antigravity

## To
Codex

## Task ID
prometheus-integration

## Priority
High

## Goal
Integrate Prometheus metrics collection into Ragent API backend.

## Context
We need to gather API performance metrics (FastAPI endpoints HTTP requests latency, count, etc.) and feed them into the local Prometheus monitoring service. Currently, the API backend does not expose metrics, and the Prometheus configuration is missing the job to scrape the backend.

## Requested Work
Please modify the code to:
1. **Update dependencies**: Add `prometheus-fastapi-instrumentator==7.0.0` to [requirements.txt](file:///e:/学习/Project/Ragent/ragent-python/requirements.txt).
2. **Expose /metrics endpoint**: In [app/main.py](file:///e:/学习/Project/Ragent/ragent-python/app/main.py), import `Instrumentator` from `prometheus_fastapi_instrumentator` and register it on the FastAPI `app` instance using a try-except block for resilience (ensure `/metrics` endpoint is not exposed in Swagger docs by using `include_in_schema=False`).
3. **Update scrape configuration**: Add a scrape job for `ragent-api:8000` to the end of `scrape_configs` in [monitoring/prometheus/prometheus.yml](file:///e:/学习/Project/Ragent/ragent-python/monitoring/prometheus/prometheus.yml):
   ```yaml
     - job_name: ragent-api
       metrics_path: /metrics
       static_configs:
         - targets:
             - ragent-api:8000
   ```

## Suggested Files
- [requirements.txt](file:///e:/学习/Project/Ragent/ragent-python/requirements.txt)
- [app/main.py](file:///e:/学习/Project/Ragent/ragent-python/app/main.py)
- [monitoring/prometheus/prometheus.yml](file:///e:/学习/Project/Ragent/ragent-python/monitoring/prometheus/prometheus.yml)

## Files To Avoid
Do not perform broad refactoring.
Do not modify files locked by another agent (check `.agent/locks/`).

## Verification Expected
- Changed files.
- Python compilation/syntax check (e.g., using `py_compile` on modified Python files).
- Dependency installation check.

## Deadline / Urgency
High

## Notes
- Git branch `task/prometheus-integration` has been created and switched to.
- A task lock `prometheus_integration.lock` has been created under `.agent/locks/` and assigned to Codex.
- Once completed, please write the result file to `.agent/results/from-codex/prometheus-integration.md` and release the lock.
