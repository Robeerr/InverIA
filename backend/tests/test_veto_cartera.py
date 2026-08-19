"""La Cartera no persiste niveles de compra de una acción vetada. Ni desde la pantalla,
ni desde una petición directa.

QUÉ CIERRA ESTE FICHERO

`ChartistPanel.addToCartera` ya se para si el veredicto viene vetado, pero es código de
CLIENTE. Un `curl` contra `POST /api/signals` no pasa por ahí, y tampoco una respuesta
servida desde la caché del navegador. Mostrar se protege en la pantalla; escribir se
protege en el servidor, y esto último es lo que se prueba aquí.

DÓNDE SE PARA LA MANO DEL USUARIO Y DÓNDE NO

El veto protege del automatismo, no de ti. Que la IA no pueda autorizar una compra no
significa que la aplicación pueda prohibírtela: querer los niveles preparados de una
acción todavía bajista, para cuando gire, es un caso legítimo. Por eso `forzar: true`
existe, y por eso hay tests de que el Chartista NO lo envía — un escape que un automatismo
puede activar solo no es un escape, es un agujero.

INCORPORAR NO ES MANTENER  (cambio de alcance, decidido por el usuario)

La puerta estaba también en el PATCH, y cortaba editar el nivel 3 de META —una acción que
YA está en la Cartera, con posición abierta— porque su tendencia era bajista. Eso no es lo
que el veto persigue: la decisión de entrar en META ya se había tomado, y mantener el plan
de una posición viva no autoriza ninguna compra. Encima el nivel quedaba imposible de
corregir justo cuando más falta hace corregirlo.

La línea pasa a ser "ya la tienes" frente a "la estás incorporando":

  · POST /signals  → VETADO. Dar de alta una acción nueva CON niveles es incorporarla.
  · PATCH          → libre. Es una fila que ya existe.

Lo que autoriza comprar de verdad sigue vetado igual: el alta, las alertas de COMPRA al
cruzar un soporte, y el plan de entrada del análisis y del Chartista.

CUATRO FRONTERAS QUE NO SE CRUZAN

  · `deseado` y `venta1..3` son objetivos de VENTA. El veto es sobre comprar.
  · El Excel y la foto son contabilidad propia del usuario, no una recomendación.
  · Registrar el precio real de una compra YA EJECUTADA es un hecho, no un plan.
  · Editar una fila que ya existe es mantener, no incorporar.
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import veto_compra  # noqa: E402

_BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
_FRONT = os.path.join(_BACKEND, "..", "frontend", "src")


def _codigo(ruta: str) -> str:
    with open(ruta, encoding="utf-8") as f:
        src = f.read()
    src = re.sub(r'""".*?"""', "", src, flags=re.S)
    src = re.sub(r"/\*[\s\S]*?\*/", "", src)
    src = re.sub(r"^\s*//.*$", "", src, flags=re.M)
    return re.sub(r"#.*", "", src)


SRV = _codigo(os.path.join(_BACKEND, "server.py"))


def _cuerpo(nombre: str, src: str = None) -> str:
    src = SRV if src is None else src
    ini = src.index(f"def {nombre}(")
    resto = src[ini:]
    m = re.search(r"\n(?:def |async def |@api_router|@app\.)", resto[1:])
    return resto[: m.start() + 1] if m else resto


# ── 1-5 · La función pura: qué cuenta como nivel de compra ──────────────────

def test_detecta_los_niveles_con_valor():
    assert veto_compra.niveles_de_compra_en({"nivel1": 180.0}) == ["nivel1"]
    assert veto_compra.niveles_de_compra_en(
        {"nivel1": 180.0, "nivel3": 150.0}) == ["nivel1", "nivel3"]


def test_none_es_borrado_y_no_intento_de_compra():
    """`nivel1: null` en un PATCH BORRA el nivel. Bloquearlo dejaría al usuario sin poder
    retirar un plan de compra sobre una acción que acaba de girarse en contra — justo lo
    contrario de lo que el veto persigue."""
    assert veto_compra.niveles_de_compra_en({"nivel1": None}) == []
    assert veto_compra.niveles_de_compra_en(
        {"nivel1": None, "nivel2": None, "nivel3": None}) == []


def test_el_cero_no_es_un_precio_de_compra():
    assert veto_compra.niveles_de_compra_en({"nivel1": 0}) == []
    assert veto_compra.niveles_de_compra_en({"nivel1": 0.0, "nivel2": -5}) == []


def test_los_objetivos_de_venta_nunca_cuentan():
    payload = {"deseado": 250.0, "venta1": 260.0, "venta2": 280.0, "venta3": 300.0}
    assert veto_compra.niveles_de_compra_en(payload) == []


def test_campos_nivel_no_contiene_ningun_campo_de_venta():
    assert veto_compra.CAMPOS_NIVEL == ("nivel1", "nivel2", "nivel3", "nivel4", "nivel5")
    for venta in ("deseado", "venta1", "venta2", "venta3"):
        assert venta not in veto_compra.CAMPOS_NIVEL, venta


def test_la_funcion_aguanta_basura():
    for basura in (None, [], "nivel1", 7):
        assert veto_compra.niveles_de_compra_en(basura) == []
    assert veto_compra.niveles_de_compra_en({"nivel1": "no-es-un-numero"}) == []


# ── Dobles: nada de Mongo, nada de red ──────────────────────────────────────

class _Coleccion:
    """Registra TODA escritura. La aserción central de este fichero es que la lista de
    escrituras quede vacía cuando el veto actúa."""

    def __init__(self, documento=None):
        self.documento = documento
        self.escrituras = []

    async def find_one(self, filtro, proyeccion=None):
        return self.documento

    async def insert_one(self, doc):
        self.escrituras.append(("insert_one", doc))

    async def update_one(self, filtro, cambio):
        self.escrituras.append(("update_one", filtro, cambio))

        class _R:
            matched_count = 1
        return _R()


class _DB:
    def __init__(self, documento=None):
        self.signal_entries = _Coleccion(documento)


@pytest.fixture
def entorno(monkeypatch):
    """Sustituye la base de datos, la lectura de tendencia y la cotización inicial.

    Se invocan las funciones de endpoint DIRECTAMENTE: montar FastAPI aquí probaría sobre
    todo el montaje, y lo que hay que proteger es el orden de las puertas.
    """
    import server

    estado = {"tendencia": "ALCISTA", "consultas": []}

    def _tendencia_de(sym):
        estado["consultas"].append(sym)
        return estado["tendencia"]

    monkeypatch.setattr(server.market_data, "tendencia_de", _tendencia_de)
    monkeypatch.setattr(server.market_data, "get_quote_fast", lambda s: None)
    monkeypatch.setattr(server.market_data, "get_quote", lambda s: None)

    async def _create_entry(db, data):
        await db.signal_entries.insert_one(data)
        return {**data, "id": "nuevo"}

    async def _update_entry(db, entry_id, data):
        # Devuelve None si no hay fila, como el de verdad (`matched_count == 0`). Antes el
        # doble devolvía siempre un dict y el 404 salía de la comprobación que hacía la
        # puerta de tendencia; al quitar la puerta del PATCH, el 404 pasó a depender de
        # esto y el doble dejó de parecerse al original.
        if db.signal_entries.documento is None:
            return None
        await db.signal_entries.update_one({"id": entry_id}, {"$set": data})
        return {"id": entry_id, **data}

    monkeypatch.setattr(server.signal_table, "create_entry", _create_entry)
    monkeypatch.setattr(server.signal_table, "update_entry", _update_entry)
    return server, estado


def _alta(server, **campos):
    return server.SignalEntryCreate(symbol="TEST", **campos)


async def _crear(server, db, item, monkeypatch):
    monkeypatch.setattr(server, "db", db)
    return await server.create_signal(item, _user="test")


async def _editar(server, db, entry_id, item, monkeypatch):
    monkeypatch.setattr(server, "db", db)
    return await server.update_signal(entry_id, item, _user="test")


# ── 6-8 · POST vetado ───────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_post_vetado_devuelve_409(entorno, monkeypatch):
    server, estado = entorno
    estado["tendencia"] = "BAJISTA"
    db = _DB()
    with pytest.raises(server.HTTPException) as exc:
        await _crear(server, db, _alta(server, nivel1=180.0), monkeypatch)
    assert exc.value.status_code == 409


@pytest.mark.anyio
async def test_post_vetado_no_escribe_absolutamente_nada(entorno, monkeypatch):
    """El requisito literal: «El rechazo debe producir 409 y cero escrituras»."""
    server, estado = entorno
    estado["tendencia"] = "BAJISTA"
    db = _DB()
    with pytest.raises(server.HTTPException):
        await _crear(server, db, _alta(server, nivel1=180.0, nivel2=160.0), monkeypatch)
    assert db.signal_entries.escrituras == []


@pytest.mark.anyio
async def test_el_motivo_del_409_es_el_de_estado_accion(entorno, monkeypatch):
    """No se redacta una explicación nueva en `server.py`: la dueña es `estado_accion`."""
    import estado_accion
    server, estado = entorno
    estado["tendencia"] = "BAJISTA"
    with pytest.raises(server.HTTPException) as exc:
        await _crear(server, _DB(), _alta(server, nivel1=180.0), monkeypatch)
    assert estado_accion.evaluar("BAJISTA")["motivo"] == exc.value.detail["mensaje"]


@pytest.mark.anyio
async def test_el_409_de_veto_se_identifica_por_un_campo_y_no_por_su_texto(entorno, monkeypatch):
    """Hay DOS 409 en este endpoint y significan lo contrario. Distinguirlos por prosa ya
    falló una vez: `ChartistPanel` trataba cualquier 409 como duplicado y pintaba el check
    verde de «En Cartera» sobre un rechazo."""
    server, estado = entorno
    estado["tendencia"] = "BAJISTA"
    with pytest.raises(server.HTTPException) as exc:
        await _crear(server, _DB(), _alta(server, nivel1=180.0), monkeypatch)
    assert exc.value.detail["error"] == "vetado_por_tendencia"
    assert exc.value.detail["symbol"] == "TEST"


@pytest.mark.anyio
async def test_el_409_de_duplicado_conserva_su_contrato(entorno, monkeypatch):
    """Sigue siendo una cadena. El cambio de forma es solo del veto — romper el duplicado
    habría roto la rama que el frontend lleva usando desde siempre."""
    server, estado = entorno
    estado["tendencia"] = "ALCISTA"
    db = _DB({"id": "ya-existe"})
    with pytest.raises(server.HTTPException) as exc:
        await _crear(server, db, _alta(server, nivel1=180.0), monkeypatch)
    assert exc.value.status_code == 409
    assert isinstance(exc.value.detail, str)
    assert "ya está en tu Cartera" in exc.value.detail
    assert db.signal_entries.escrituras == []


@pytest.mark.anyio
async def test_los_dos_409_son_separables_sin_leer_el_mensaje(entorno, monkeypatch):
    """El invariante que usa el cliente: uno trae `detail.error`, el otro no."""
    server, estado = entorno

    estado["tendencia"] = "BAJISTA"
    with pytest.raises(server.HTTPException) as veto:
        await _crear(server, _DB(), _alta(server, nivel1=180.0), monkeypatch)

    estado["tendencia"] = "ALCISTA"
    with pytest.raises(server.HTTPException) as dup:
        await _crear(server, _DB({"id": "x"}), _alta(server, nivel1=180.0), monkeypatch)

    assert isinstance(veto.value.detail, dict) and veto.value.detail.get("error")
    assert not isinstance(dup.value.detail, dict)


# ── 9-13 · POST permitido ───────────────────────────────────────────────────

@pytest.mark.anyio
async def test_post_alcista_con_niveles_se_da_de_alta(entorno, monkeypatch):
    server, estado = entorno
    estado["tendencia"] = "ALCISTA"
    db = _DB()
    await _crear(server, db, _alta(server, nivel1=180.0), monkeypatch)
    assert [e[0] for e in db.signal_entries.escrituras] == ["insert_one"]


@pytest.mark.anyio
async def test_en_seguimiento_no_veta(entorno, monkeypatch):
    """Solo NO_COMPRAR bloquea. INDEFINIDA y SIN_DATOS son EN_SEGUIMIENTO: se vigilan."""
    server, estado = entorno
    for tend in ("INDEFINIDA", "SIN_DATOS"):
        estado["tendencia"] = tend
        db = _DB()
        await _crear(server, db, _alta(server, nivel1=180.0), monkeypatch)
        assert db.signal_entries.escrituras, tend


@pytest.mark.anyio
async def test_alta_sin_niveles_pasa_y_no_consulta_la_tendencia(entorno, monkeypatch):
    server, estado = entorno
    estado["tendencia"] = "BAJISTA"
    db = _DB()
    await _crear(server, db, _alta(server, notes="solo para vigilar"), monkeypatch)
    assert db.signal_entries.escrituras
    assert estado["consultas"] == []


@pytest.mark.anyio
async def test_los_objetivos_de_venta_no_se_vetan(entorno, monkeypatch):
    server, estado = entorno
    estado["tendencia"] = "BAJISTA"
    db = _DB()
    await _crear(server, db, _alta(server, deseado=250.0, venta1=260.0, venta2=280.0,
                                   venta3=300.0), monkeypatch)
    assert db.signal_entries.escrituras
    assert estado["consultas"] == []


@pytest.mark.anyio
async def test_forzar_permite_el_alta_vetada(entorno, monkeypatch):
    server, estado = entorno
    estado["tendencia"] = "BAJISTA"
    db = _DB()
    await _crear(server, db, _alta(server, nivel1=180.0, forzar=True), monkeypatch)
    assert [e[0] for e in db.signal_entries.escrituras] == ["insert_one"]
    assert estado["consultas"] == []


# ── 14-19 · PATCH: editar una fila que YA existe no pasa por la puerta ──────
#
# Estos tests decían lo contrario hasta que el usuario cambió el alcance: la puerta
# cortaba corregir el nivel de una posición abierta, que es mantenimiento y no una
# compra. Se reescriben para fijar la línea nueva; no se borran, porque la
# responsabilidad —"qué puede y qué no puede escribir un PATCH"— sigue viva.

@pytest.mark.anyio
async def test_editar_un_nivel_de_algo_que_ya_tienes_no_consulta_la_tendencia(entorno, monkeypatch):
    """El caso real: META en NO_COMPRAR, ya en la Cartera, y el nivel 3 hay que ajustarlo."""
    server, estado = entorno
    estado["tendencia"] = "BAJISTA"
    db = _DB({"symbol": "META"})
    await _editar(server, db, "id-1", server.SignalEntryUpdate(nivel2=90.0), monkeypatch)
    assert estado["consultas"] == [], "editar no autoriza comprar: no se pregunta"
    assert [e[0] for e in db.signal_entries.escrituras] == ["update_one"]


@pytest.mark.anyio
async def test_el_alta_sigue_vetada(entorno, monkeypatch):
    """La otra mitad de la línea. Si esto cayera, el cambio de alcance se habría comido
    el veto entero en vez de acotarlo."""
    server, estado = entorno
    estado["tendencia"] = "BAJISTA"
    db = _DB()
    with pytest.raises(server.HTTPException) as exc:
        await _crear(server, db, _alta(server, nivel1=180.0), monkeypatch)
    assert exc.value.status_code == 409
    assert exc.value.detail["error"] == "vetado_por_tendencia"
    assert db.signal_entries.escrituras == []


@pytest.mark.anyio
async def test_entrada_inexistente_sigue_dando_404(entorno, monkeypatch):
    server, estado = entorno
    estado["tendencia"] = "BAJISTA"
    db = _DB(None)
    with pytest.raises(server.HTTPException) as exc:
        await _editar(server, db, "no-existe",
                      server.SignalEntryUpdate(nivel1=10.0), monkeypatch)
    assert exc.value.status_code == 404
    assert estado["consultas"] == []


@pytest.mark.anyio
async def test_editar_un_campo_que_no_es_nivel_tampoco_consulta_la_tendencia(entorno, monkeypatch):
    server, estado = entorno
    estado["tendencia"] = "BAJISTA"
    db = _DB({"symbol": "GUARDADO"})
    await _editar(server, db, "id-1",
                  server.SignalEntryUpdate(notes="una nota"), monkeypatch)
    assert estado["consultas"] == []
    assert [e[0] for e in db.signal_entries.escrituras] == ["update_one"]


@pytest.mark.anyio
async def test_borrar_un_nivel_sigue_permitido(entorno, monkeypatch):
    server, estado = entorno
    estado["tendencia"] = "BAJISTA"
    db = _DB({"symbol": "GUARDADO"})
    await _editar(server, db, "id-1",
                  server.SignalEntryUpdate(nivel1=None), monkeypatch)
    assert estado["consultas"] == []
    assert [e[0] for e in db.signal_entries.escrituras] == ["update_one"]


@pytest.mark.anyio
async def test_el_patch_no_consulta_la_tendencia_en_ningun_caso(entorno, monkeypatch):
    """Ni con niveles, ni sin ellos, ni con la acción más bajista del mundo. Una consulta
    de tendencia en el PATCH sería la puerta volviendo por la puerta de atrás."""
    server, estado = entorno
    estado["tendencia"] = "BAJISTA"
    for campos in ({"nivel1": 10.0}, {"nivel1": 10.0, "nivel5": 5.0},
                   {"deseado": 300.0}, {"acciones": 3}):
        db = _DB({"symbol": "GUARDADO"})
        await _editar(server, db, "id-1",
                      server.SignalEntryUpdate(**campos), monkeypatch)
    assert estado["consultas"] == []


# ── 20-27 · Arquitectura ────────────────────────────────────────────────────

def test_no_comprar_no_se_interpreta_fuera_de_veto_compra():
    """La regla sigue centralizada. `server.py` pregunta, no compara."""
    assert '"NO_COMPRAR"' not in SRV


def test_la_puerta_usa_la_autoridad_existente():
    puerta = _cuerpo("_puerta_de_tendencia")
    assert "market_data.tendencia_de" in puerta
    assert "estado_accion.evaluar" in puerta
    assert "veto_compra.hay_veto" in puerta


def test_en_el_alta_el_duplicado_se_comprueba_antes_del_veto():
    cuerpo = _cuerpo("create_signal")
    assert cuerpo.index("ya está en tu Cartera") < cuerpo.index("_puerta_de_tendencia")


def test_la_puerta_va_antes_de_cualquier_escritura():
    alta = _cuerpo("create_signal")
    assert alta.index("_puerta_de_tendencia") < alta.index("signal_table.create_entry")
    # En `update_signal` ya no hay puerta que ordenar: editar una fila que ya existe es
    # mantenimiento. Lo que se exige es que no vuelva a colarse.
    edicion = _cuerpo("update_signal")
    assert "_puerta_de_tendencia" not in edicion


def test_signal_table_no_conoce_el_veto():
    """La autoridad no baja a la capa de datos: si bajara, el import masivo y el registro
    de compras ejecutadas quedarían vetados de rebote.

    NO se prohíbe la palabra «tendencia»: `signal_table` importa el módulo desde 5b-1 y lo
    usa en `_contexto_alerta` para no disparar alertas de COMPRA contra tendencia. Ese es
    otro consumidor legítimo de la misma autoridad. Lo que no puede tener es el veto de
    ESCRITURA, que pertenece a los endpoints.
    """
    codigo = _codigo(os.path.join(_BACKEND, "signal_table.py"))
    for ajeno in ("veto_compra", "NO_COMPRAR", "_puerta_de_tendencia"):
        assert ajeno not in codigo, ajeno
    for escritor in ("create_entry", "update_entry", "bulk_upsert"):
        cuerpo = _cuerpo(escritor, codigo)
        assert "hay_tendencia_valida" not in cuerpo, escritor


def test_el_import_masivo_y_la_foto_no_se_vetan():
    """El Excel y la foto son contabilidad propia del usuario, no una recomendación."""
    for nombre in ("bulk_import_signals", "import_signals_from_image"):
        cuerpo = _cuerpo(nombre)
        assert "_puerta_de_tendencia" not in cuerpo, nombre
        assert "tendencia_de" not in cuerpo, nombre


def test_el_registro_de_compras_ejecutadas_no_se_veta():
    """`_actualizar_precio_nivel` pone el nivel al precio REAL de una compra ya hecha.
    Vetar el registro de un hecho consumado sería falsear el histórico."""
    codigo = _codigo(os.path.join(_BACKEND, "cartera_api.py"))
    for ajeno in ("veto_compra", "_puerta_de_tendencia", "NO_COMPRAR"):
        assert ajeno not in codigo, ajeno


def test_forzar_no_se_persiste():
    """No está en las listas blancas de `signal_table`, así que la capa de datos lo
    descarta sola y no acaba dentro del documento de la Cartera."""
    codigo = _codigo(os.path.join(_BACKEND, "signal_table.py"))
    bloque = codigo[codigo.index("ALLOWED_CREATE"):codigo.index("def ")]
    assert "forzar" not in bloque


# ── El escape es del usuario, no del automatismo ───────────────────────────

def test_ningun_cliente_envia_forzar_al_crear_o_editar_en_cartera():
    """El escape no puede activarlo un automatismo; hoy no lo envía nadie.

    Se comprueba sobre la capa de API y sobre el PATCH suelto de `SignalsView`, no sobre
    la palabra en todo el frontend: `api.borrarCompra` ya usaba un parámetro `forzar`
    ANTES de este cambio, para otro endpoint —sortear la negativa a borrar una compra que
    dejaría ventas sin coste—. Prohibir la palabra habría leído ese otro escape.
    """
    api = _codigo(os.path.join(_FRONT, "lib", "api.js"))
    for linea in api.splitlines():
        if "/signals" in linea:
            assert "forzar" not in linea, linea.strip()
    vista = _codigo(os.path.join(_FRONT, "pages", "SignalsView.jsx"))
    assert "forzar" not in vista
