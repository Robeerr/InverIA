# Tests

Batería de tests que protege la lógica de cálculo del backend. Son el
"botón rojo/verde": ejecútalos cada vez que toques el motor de niveles o el
score de potencial, y sabrás en segundos si rompiste algo antes de desplegar.

## Cómo ejecutarlos

```bash
cd backend
pip install -r requirements-dev.txt   # solo la primera vez
pytest                                 # ✅ 23 tests rápidos (sin red)
pytest -v                              # igual, con el detalle de cada test
```

- **Verde** (`23 passed`) → la lógica sigue correcta, puedes desplegar.
- **Rojo** (`X failed`) → rompiste algo; el test te dice qué. Arréglalo antes de subir.

## Qué cubren

- **`test_levels_engine.py`** — el motor de niveles (`compute_buy_levels`):
  invariantes que SIEMPRE deben cumplirse (ningún nivel de compra por encima
  del precio, orden cercano→profundo, fuerza 0-100, determinismo, confluencia).
  Estos tests habrían cazado el bug del gráfico que mostraba $475 en vez de $375.

- **`test_scoring.py`** — el score de potencial (`_potential_score`): que las
  buenas oportunidades puntúen alto y los value traps (tipo CRM/SLB) queden
  penalizados por el guardián de tendencia, pase lo que pase con los pesos.

## Tests de integración (aparte)

`backend_test.py` son pruebas end-to-end que llaman a un servidor en vivo
(necesitan red y la API arrancada). No se ejecutan con `pytest` a secas:

```bash
pytest tests/backend_test.py
```
