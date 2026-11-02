"""El banco de pruebas de la Inteligencia: los 20 casos de PROMPT_V = 2, congelados.

PARA QUÉ

Para comparar versiones de la investigación —otro prompt, otros topes, otro modelo—
sobre EXACTAMENTE los mismos documentos, sin tocar producción. Una versión nueva se juzga
contra estos 20 casos y contra lo que la versión actual produjo con ellos, no contra los
8-K que vayan entrando, que serían otros cada vez.

QUÉ GUARDA DE CADA CASO

  · el evento y su número de registro;
  · los documentos: el texto COMPLETO del principal y de los EX-99 que lee producción,
    re-descargados con las mismas funciones de producción, y además los anexos que
    producción NO lee (EX-99 por encima del tope, EX-2.1, EX-10…), para que una versión
    con otros topes u otra selección pueda construir su propia entrada;
  · la entrada histórica: el texto que recibió el modelo, reconstruido, y si se ha podido
    comprobar que es el mismo (por longitudes registradas o por huella);
  · la salida histórica: resumen, hechos, implicaciones, incertidumbres, fuente,
    confianza guardada y confianza declarada;
  · la verificación de los hechos contra esa entrada;
  · lo que no se registró en su día, dicho como tal.

LO QUE NO INVENTA

Las investigaciones 1-8 son anteriores a la lectura de anexos y todas las anteriores a la
trazabilidad no guardaron la respuesta original, el modelo real, los tiempos ni los
errores. Esos campos quedan a None y aparecen en `faltantes`. Una confianza guardada de 0
no se da por declarada: sin la respuesta original no se distingue de un campo ausente.

INMUTABLE

Se congela una vez. Congelar otra vez no sobrescribe nada: devuelve lo que ya había.
"""
import asyncio
import hashlib
import logging
import time
import uuid

import intel_eventos as ev
import intel_investigacion as inv
import verificador_hechos

logger = logging.getLogger("banco_inteligencia")

BANCO = "inteligencia-20-v1"
COL_BANCO = "intel_banco"
COL_EJECUCIONES = "intel_banco_ejecuciones"
CASOS_ESPERADOS = 20
PROMPT_V_DEL_BANCO = 2

SOLO_PRINCIPAL = "solo_principal"   # investigaciones anteriores a la lectura de EX-99
CON_ANEXOS = "con_anexos"

NO_REGISTRADO = "no registrado: la investigación es anterior a la trazabilidad"

#: Pausa entre casos al congelar: la SEC pide no pasar de 10 peticiones por segundo.
PAUSA_ENTRE_CASOS_S = 0.3

#: Anexos que producción no lee y el banco guarda igualmente, como mucho, por caso; y
#: cuánto texto de cada uno. Un contrato de fusión puede tener medio millón de caracteres:
#: sin tope, un caso no cabría en un documento de Mongo.
MAX_OTROS_ANEXOS = 6
MAX_TEXTO_OTRO_ANEXO = 200_000


def _huella(texto: str) -> str:
    return hashlib.sha256((texto or "").encode("utf-8")).hexdigest()


# ── Qué casos son ────────────────────────────────────────────────────────────

#: Las TRES investigaciones de la muestra hechas con el prompt v2 antes de que la versión
#: se guardara en cada investigación (commit 130727c, 13-09-2026 14:34 UTC). Se leyeron el
#: 11-09-2026 hacia las 11:25 UTC. Su versión no está en el registro: la ATRIBUYE el
#: mensaje de ese commit («RH, AAOI y ORCL con el que las separa»). Los ids los localizó
#: el usuario en la exportación del 02-11-2026.
#:
#: Es una lista EXPLÍCITA, a propósito. Una regla del tipo «las que no tienen versión»
#: metería también las tres leídas con el prompt v1 (abajo), que no son de la muestra.
ATRIBUIDOS_V2 = {
    "sec:8-K:000110465926106743": "RH",
    "sec:8-K:000168316826007057": "AAOI",
    "sec:8-K:000119312526387905": "ORCL",
}

#: Las tres investigaciones antiguas SIN versión que NO son de la muestra: se leyeron el
#: 10-09-2026 con el prompt v1 (commits f09bcf3 y 8bed99e). Nunca entran en el banco.
EXCLUIDOS_V1 = {
    "sec:8-K:000117891326004477": "SEDG",
    "sec:8-K:000101872426000036": "AMZN",
    "sec:8-K:000163882626000093": "TTAN",
}

PROCEDENCIA_REGISTRADA = {
    "version": PROMPT_V_DEL_BANCO,
    "verificacion": "registrada en la investigación",
    "evidencia": "investigacion.prompt_v",
}
PROCEDENCIA_ATRIBUIDA = {
    "version": PROMPT_V_DEL_BANCO,
    "verificacion": "atribuida, no verificada individualmente",
    "evidencia": ("commit 130727c: «RH, AAOI y ORCL con el [prompt] que las separa»; "
                  "el campo prompt_v no se guardó en la investigación"),
}


def procedencia_de(evento: dict):
    """De dónde sale que el caso es v2. None si no es de la muestra."""
    i = (evento or {}).get("investigacion") or {}
    if i.get("prompt_v") == PROMPT_V_DEL_BANCO:
        return dict(PROCEDENCIA_REGISTRADA)
    if evento.get("id") in ATRIBUIDOS_V2 and "prompt_v" not in i:
        return dict(PROCEDENCIA_ATRIBUIDA)
    return None


async def candidatos(db) -> list:
    """Los casos de la muestra, en el orden en que se investigaron.

    Los que tienen guardado PROMPT_V = 2, más los tres de `ATRIBUIDOS_V2` si existen,
    están investigados y siguen SIN versión guardada. Solo se lee: ningún registro se toca.
    """
    registrados = await db.intel_eventos.find(
        {"investigacion.prompt_v": PROMPT_V_DEL_BANCO}, {"_id": 0}
    ).to_list(1000)
    atribuidos = await db.intel_eventos.find(
        {"id": {"$in": list(ATRIBUIDOS_V2)}}, {"_id": 0}
    ).to_list(len(ATRIBUIDOS_V2))
    vistos, docs = set(), []
    for d in registrados + atribuidos:
        if d.get("id") in vistos or d.get("id") in EXCLUIDOS_V1:
            continue
        if d.get("investigacion") and procedencia_de(d):
            vistos.add(d.get("id"))
            docs.append(d)
    return sorted(docs, key=lambda d: str(d.get("investigado_en") or ""))


def era_de(evento: dict) -> str:
    """Las investigaciones con `documentos_enviados` se hicieron leyendo anexos."""
    return CON_ANEXOS if evento.get("documentos_enviados") else SOLO_PRINCIPAL


# ── Reconstrucción con las funciones de producción ───────────────────────────

async def reconstruir(evento: dict) -> dict:
    """Re-descarga los documentos del caso y reconstruye la entrada que recibió el modelo.

    Usa `descargar_documento`, `texto_del_documento`, `anexos_ex99` y `ensamblar_envio`
    tal cual: la reconstrucción no tiene un camino propio que pudiera diferir.
    """
    errores = []
    url = evento.get("url")
    bajada = await inv.descargar_documento(url)
    if not bajada.get("ok"):
        return {"ok": False, "errores": [f"principal: {bajada.get('error')}"]}
    principal = inv.texto_del_documento(bajada.get("html"), maximo=inv.MAX_BYTES)

    ex99 = await inv.anexos_ex99(evento)
    anexos = ex99.get("anexos") or []
    for f in ex99.get("fallos") or []:
        errores.append(f"{f.get('tipo')}: {f.get('error')}")

    otros = await _otros_anexos(evento, ex99, errores)

    era = era_de(evento)
    if era == CON_ANEXOS:
        # Los anexos que se ENVIARON, en su orden, según lo que quedó registrado.
        enviados = [d.get("url") for d in (evento.get("documentos_enviados") or [])[1:]]
        por_url = {a.get("url"): a for a in anexos}
        faltan = [u for u in enviados if u not in por_url]
        if faltan:
            errores.append(f"no se pudieron re-descargar anexos enviados: {faltan}")
        anexos_historicos = [por_url[u] for u in enviados if u in por_url]
    else:
        anexos_historicos = []
    envio = inv.ensamblar_envio(principal, evento, anexos_historicos)
    peticion = inv.construir_peticion(evento, envio["texto"])
    historicos = {a.get("url") for a in anexos_historicos}
    return {
        "ok": not any(e.startswith("no se pudieron") for e in errores),
        "errores": errores,
        "documentos": {
            "principal": {"url": url, "http": bajada.get("http"),
                          "caracteres": len(principal), "texto": principal},
            "anexos": [{"tipo": a.get("tipo"), "documento": a.get("documento"),
                        "url": a.get("url"), "caracteres": len(a.get("texto") or ""),
                        "enviado_historicamente": a.get("url") in historicos,
                        "texto": a.get("texto")} for a in anexos],
            "otros": otros,
            "ex99": {k: v for k, v in ex99.items() if k != "anexos"},
        },
        "envio": envio,
        "peticion": peticion,
    }


async def _otros_anexos(evento: dict, ex99: dict, errores: list) -> list:
    """Los anexos del registro que producción NO lee: los EX-99 por encima del tope y los
    de otros tipos (EX-2.1, EX-10…). Se guardan para poder probar otra selección.

    Mismas garantías que producción: solo nombres seguros dentro de la carpeta del
    registro, y nunca XBRL (EX-101) ni la portada interactiva (EX-104).
    """
    accession = str((evento.get("crudo") or {}).get("accession") or "")
    carpeta = inv.carpeta_del_registro(evento.get("url"), accession)
    if not carpeta:
        return []
    otros = []
    for item in ex99.get("inventario") or []:
        if len(otros) >= MAX_OTROS_ANEXOS:
            break
        tipo = (item.get("tipo") or "").upper()
        nombre = item.get("documento") or ""
        if item.get("decision") not in ("omitido_por_tope", "no_leido"):
            continue
        if not tipo.startswith("EX-") or tipo.startswith(("EX-101", "EX-104")):
            continue
        if not inv._NOMBRE_SEGURO.match(nombre):
            continue
        bajada = await inv.descargar_documento(carpeta + nombre)
        if not bajada.get("ok"):
            errores.append(f"{tipo} (no lo lee producción): {bajada.get('error')}")
            continue
        texto = inv.texto_del_documento(bajada.get("html"), maximo=inv.MAX_BYTES)
        otros.append({"tipo": tipo, "documento": nombre, "url": carpeta + nombre,
                      "caracteres": len(texto), "texto": texto[:MAX_TEXTO_OTRO_ANEXO],
                      "texto_recortado": len(texto) > MAX_TEXTO_OTRO_ANEXO,
                      "leido_por_produccion": False, "enviado_historicamente": False,
                      "motivo_no_leido": item.get("motivo")})
    return otros


def comprobar_reconstruccion(evento: dict, envio: dict) -> dict:
    """¿Lo reconstruido es lo que se envió? Con lo que haya registrado, sin suponer nada."""
    traza = evento.get("traza") or {}
    huella = ((traza.get("envio") or {}).get("sha256_texto_enviado"))
    if huella:
        coincide = huella == _huella(envio["texto"])
        return {"metodo": "huella", "coincide": coincide,
                "diferencias": [] if coincide else ["la huella del texto no coincide"]}
    registrados = evento.get("documentos_enviados")
    if not registrados:
        return {"metodo": "ninguno", "coincide": None, "diferencias": [],
                "nota": ("anterior a la lectura de anexos y a la trazabilidad: no quedó "
                         "ninguna longitud registrada con la que contrastar")}
    diferencias = []
    reconstruidos = envio["documentos"]
    if len(registrados) != len(reconstruidos):
        diferencias.append(f"documentos: registrados {len(registrados)}, "
                           f"reconstruidos {len(reconstruidos)}")
    for reg, rec in zip(registrados, reconstruidos):
        for campo in ("url", "caracteres_extraidos", "caracteres_enviados"):
            if reg.get(campo) != rec.get(campo):
                diferencias.append(f"{reg.get('tipo')} {campo}: registrado {reg.get(campo)}, "
                                   f"reconstruido {rec.get(campo)}")
    return {"metodo": "longitudes", "coincide": not diferencias, "diferencias": diferencias}


def salida_historica(evento: dict) -> dict:
    """La lectura guardada, tal cual, y la confianza que se puede dar por declarada."""
    i = evento.get("investigacion") or {}
    traza = evento.get("traza") or {}
    respuesta = traza.get("respuesta") or {}
    guardada = i.get("confianza")
    if respuesta:
        declarada, nota = respuesta.get("confianza_declarada"), None
    elif isinstance(guardada, (int, float)) and guardada > 0:
        # `validar` solo inventa un 0: cualquier otro valor lo escribió el modelo.
        declarada, nota = guardada, None
    else:
        declarada = None
        nota = ("se guardó 0, y sin la respuesta original no se distingue un 0 declarado "
                "de un campo ausente")
    return {
        "hay_informacion": i.get("hay_informacion"),
        "resumen": i.get("resumen"),
        "hechos": i.get("hechos") or [],
        "implicaciones": i.get("implicaciones") or [],
        "incertidumbres": i.get("incertidumbres") or [],
        "fuente": i.get("fuente"),
        "confianza_guardada": guardada,
        "confianza_declarada": declarada,
        "nota_confianza": nota,
    }


def _cobertura(documentos: dict, envio: dict) -> dict:
    enviados = sum(d.get("caracteres_enviados") or 0 for d in envio["documentos"])
    leidos = sum(d.get("caracteres_extraidos") or 0 for d in envio["documentos"])
    # Todo lo que tiene el registro en texto: el principal, los EX-99 que se leen y los
    # anexos que producción no lee. Es la medida de cuánto se le escapa a la lectura.
    del_registro = (documentos["principal"]["caracteres"]
                    + sum(a["caracteres"] for a in documentos["anexos"])
                    + sum(o["caracteres"] for o in documentos.get("otros") or []))
    return {"caracteres_enviados": enviados,
            "caracteres_de_lo_leido": leidos,
            "caracteres_del_registro": del_registro,
            "cobertura_de_lo_leido": round(enviados / leidos, 4) if leidos else None,
            "cobertura_del_registro": round(enviados / del_registro, 4) if del_registro else None,
            "documentos_recortados": sum(1 for d in envio["documentos"] if d.get("recortado"))}


def construir_caso(evento: dict, orden: int, rec: dict) -> dict:
    crudo = evento.get("crudo") or {}
    traza = evento.get("traza") or {}
    salida = salida_historica(evento)
    envio, peticion = rec["envio"], rec["peticion"]
    faltantes = [c for c, v in (("respuesta_original", (traza.get("respuesta") or {}).get("original")),
                                ("modelo_real", (traza.get("llamada") or {}).get("modelo_real")),
                                ("tiempos", traza.get("tiempos_ms")),
                                ("errores", traza or None)) if not v]
    if era_de(evento) == SOLO_PRINCIPAL:
        faltantes.append("documentos_enviados")
    return {
        "tipo": "caso",
        "banco": BANCO,
        "orden": orden,
        "evento_id": evento.get("id"),
        "symbol": evento.get("symbol"),
        "titulo": evento.get("titulo"),
        "formulario": crudo.get("formulario") or crudo.get("suceso"),
        "accession": crudo.get("accession"),
        "cik": crudo.get("cik"),
        "url": evento.get("url"),
        "fecha_registro": crudo.get("fecha_registro"),
        "recibido_en": evento.get("recibido_en"),
        "investigado_en": evento.get("investigado_en"),
        "era": era_de(evento),
        # Lo que dice el registro, tal cual (None en los tres atribuidos), y aparte de
        # dónde sale la versión. El registro original no se toca.
        "prompt_v": (evento.get("investigacion") or {}).get("prompt_v"),
        "procedencia_version": procedencia_de(evento),
        "modelo": {"clave": (evento.get("investigacion") or {}).get("modelo"),
                   "real": (traza.get("llamada") or {}).get("modelo_real"),
                   "nota": None if traza else NO_REGISTRADO},
        "documentos": rec["documentos"],
        "documentos_enviados_registrados": evento.get("documentos_enviados"),
        "entrada_historica": {
            "texto": envio["texto"],
            "caracteres": len(envio["texto"]),
            "sha256": _huella(envio["texto"]),
            "documentos": envio["documentos"],
            "usuario_sha256": _huella(peticion["usuario"]),
            "sistema_sha256": _huella(peticion["sistema"]),
            "reconstruccion": comprobar_reconstruccion(evento, envio),
        },
        "cobertura": _cobertura(rec["documentos"], envio),
        "respuesta_original": (traza.get("respuesta") or {}).get("original"),
        "salida": salida,
        "estado_respuesta": ({k: v for k, v in (traza.get("respuesta") or {}).items()
                              if k not in ("original", "original_descartada")} or None),
        "verificacion_hechos": {
            "sobre": "entrada reconstruida",
            **verificador_hechos.verificar(salida["hechos"], peticion["usuario"]),
        },
        "tiempos_ms": traza.get("tiempos_ms"),
        "error": traza.get("error") if traza else None,
        "errores_de_reconstruccion": rec["errores"],
        "faltantes": faltantes,
    }


# ── Congelar y leer ──────────────────────────────────────────────────────────

async def manifiesto(db):
    return await db[COL_BANCO].find_one({"tipo": "manifiesto", "banco": BANCO}, {"_id": 0})


async def congelar(db, ids: list = None) -> dict:
    """Construye el banco y lo guarda UNA vez. No toca `intel_eventos`.

    Sin `ids`, toma los casos de la muestra —los que tienen PROMPT_V = 2 guardado y los
    tres de `ATRIBUIDOS_V2`— y exige que estén los tres atribuidos y que sean exactamente
    20: si no, no congela nada y devuelve la lista para revisarla. Con `ids`, usa
    exactamente esos. Si algún documento que se envió no se puede re-descargar, tampoco
    congela: un banco incompleto no serviría para comparar.
    """
    ya = await manifiesto(db)
    if ya:
        return {"ok": False, "motivo": "el banco ya está congelado y no se sobrescribe",
                "manifiesto": ya}
    todos = await candidatos(db)
    resumen = [_resumen_candidato(e) for e in todos]
    if ids:
        if len(ids) != len(set(ids)):
            return {"ok": False, "motivo": "hay ids repetidos", "candidatos": resumen}
        elegidos = [e for e in todos if e.get("id") in set(ids)]
        if len(elegidos) != len(set(ids)):
            return {"ok": False, "motivo": "algún id no es un caso de la muestra (PROMPT_V = 2)",
                    "candidatos": resumen}
    else:
        elegidos = todos
        # Los tres atribuidos, TODOS: sin alguno, el banco no se congela a medias.
        presentes = {e.get("id") for e in todos}
        faltan = [i for i in ATRIBUIDOS_V2 if i not in presentes]
        if faltan:
            return {"ok": False,
                    "motivo": f"faltan investigaciones autorizadas de la muestra: {faltan}",
                    "candidatos": resumen}
        if len(elegidos) != CASOS_ESPERADOS:
            return {"ok": False,
                    "motivo": f"se esperaban {CASOS_ESPERADOS} casos y hay {len(elegidos)}",
                    "candidatos": resumen}
    if len({e.get("id") for e in elegidos}) != len(elegidos):
        return {"ok": False, "motivo": "hay casos repetidos", "candidatos": resumen}

    casos, errores = [], []
    for orden, evento in enumerate(elegidos, start=1):
        rec = await reconstruir(evento)
        if not rec.get("ok"):
            errores.append({"evento_id": evento.get("id"), "errores": rec.get("errores")})
        else:
            casos.append(construir_caso(evento, orden, rec))
        await asyncio.sleep(PAUSA_ENTRE_CASOS_S)
    if errores:
        return {"ok": False, "motivo": "no se pudieron reconstruir todos los casos; no se "
                                       "ha guardado nada", "errores": errores}

    man = {
        "tipo": "manifiesto", "banco": BANCO, "congelado_en": ev._ahora(),
        "casos": len(casos), "ids": [c["evento_id"] for c in casos],
        "prompt_v": PROMPT_V_DEL_BANCO,
        "version_registrada": sum(1 for c in casos if c["procedencia_version"]["verificacion"]
                                  == PROCEDENCIA_REGISTRADA["verificacion"]),
        "version_atribuida": [c["evento_id"] for c in casos
                              if c["procedencia_version"]["verificacion"]
                              == PROCEDENCIA_ATRIBUIDA["verificacion"]],
        "sistema_sha256": _huella(inv.SISTEMA),
        "limites": inv.nueva_traza()["limites"],
        "reconstruccion": {
            "comprobada_por_huella": sum(1 for c in casos if c["entrada_historica"]["reconstruccion"]["metodo"] == "huella"),
            "comprobada_por_longitudes": sum(1 for c in casos if c["entrada_historica"]["reconstruccion"]["metodo"] == "longitudes"),
            "sin_registro_con_que_comparar": sum(1 for c in casos if c["entrada_historica"]["reconstruccion"]["metodo"] == "ninguno"),
            "no_coinciden": [c["evento_id"] for c in casos
                             if c["entrada_historica"]["reconstruccion"]["coincide"] is False],
        },
    }
    for c in casos:
        await db[COL_BANCO].insert_one(dict(c))
    await db[COL_BANCO].insert_one(dict(man))
    return {"ok": True, "manifiesto": man}


def _resumen_candidato(e: dict) -> dict:
    procedencia = procedencia_de(e) or {}
    return {"evento_id": e.get("id"), "symbol": e.get("symbol"),
            "investigado_en": e.get("investigado_en"), "era": era_de(e),
            "version": procedencia.get("version"),
            "verificacion_version": procedencia.get("verificacion")}


async def casos(db, con_textos: bool = False) -> list:
    proy = {"_id": 0}
    if not con_textos:
        proy.update({"documentos.principal.texto": 0, "documentos.anexos.texto": 0,
                     "documentos.otros.texto": 0, "entrada_historica.texto": 0})
    docs = await db[COL_BANCO].find({"tipo": "caso", "banco": BANCO}, proy).sort(
        "orden", 1).to_list(1000)
    return docs


# ── Versiones y comparación ──────────────────────────────────────────────────

def version_produccion() -> dict:
    """La investigación tal como está hoy en producción, descrita para el banco."""
    return {"nombre": f"produccion-prompt-v{inv.PROMPT_V}", "prompt_v": inv.PROMPT_V,
            "sistema": inv.SISTEMA, "modelo": inv.MODELO,
            "max_caracteres": inv.MAX_CARACTERES,
            "max_caracteres_anexo": inv.MAX_CARACTERES_ANEXO,
            "max_anexos": inv.MAX_ANEXOS, "max_tokens": inv.MAX_TOKENS_SALIDA,
            "lee_anexos": True}


#: Las versiones que se pueden ejecutar sobre el banco. Una versión candidata se añade
#: aquí, con su prompt y sus topes, sin tocar `intel_investigacion`.
VERSIONES = {"produccion": version_produccion}


def entrada_para(caso: dict, version: dict) -> str:
    """El texto que recibiría el modelo con los topes de `version`. Puro.

    Mismo formato que `ensamblar_envio` (principal y luego cada anexo con su
    delimitador); con los topes de producción da exactamente lo mismo.
    """
    principal = caso["documentos"]["principal"]["texto"] or ""
    partes = [principal[:version["max_caracteres"]]]
    if version.get("lee_anexos"):
        # Los EX-99 que lee producción y los que dejó fuera por el tope: con el tope de
        # producción salen exactamente los mismos, y con uno mayor entran los demás.
        candidatos_ex99 = list(caso["documentos"]["anexos"]) + [
            o for o in caso["documentos"].get("otros") or []
            if inv._TIPO_EX99.match(o.get("tipo") or "")]
        anexos = sorted((a for a in candidatos_ex99 if a.get("texto")),
                        key=lambda a: inv._clave_de_tipo(a.get("tipo")))
        for a in anexos[:version["max_anexos"]]:
            partes.append(f"\n\n=== ANEXO {a.get('tipo')} ===\n"
                          f"{a['texto'][:version['max_caracteres_anexo']]}")
    return "".join(partes)


def _evento_del_caso(caso: dict) -> dict:
    """Lo que `construir_peticion` necesita del evento, sacado del caso congelado."""
    return {"symbol": caso.get("symbol"), "titulo": caso.get("titulo"),
            "crudo": {"formulario": caso.get("formulario"),
                      "fecha_registro": caso.get("fecha_registro")}}


def metricas(salida: dict, verificacion: dict, estado: dict = None) -> dict:
    """Lo que se compara entre versiones, igual para la histórica y para las nuevas."""
    rec = (verificacion or {}).get("recuento") or {}
    return {
        "hechos": len(salida.get("hechos") or []),
        "implicaciones": len(salida.get("implicaciones") or []),
        "incertidumbres": len(salida.get("incertidumbres") or []),
        "hechos_localizados": rec.get(verificador_hechos.LOCALIZADO, 0),
        "hechos_parciales": rec.get(verificador_hechos.PARCIAL, 0),
        "hechos_no_localizados": rec.get(verificador_hechos.NO_LOCALIZADO, 0),
        "confianza_declarada": salida.get("confianza_declarada"),
        "estado_respuesta": (estado or {}).get("estado"),
        "resumen_caracteres": len(salida.get("resumen") or ""),
    }


async def ejecutar_caso(caso: dict, version: dict, run_model=None) -> dict:
    """Una pasada de `version` sobre un caso. Lee y llama al modelo; no escribe nada."""
    import ai_analysis
    run_model = run_model or ai_analysis._run_model
    texto = entrada_para(caso, version)
    peticion = inv.construir_peticion(_evento_del_caso(caso), texto)
    registro = {}
    marca = ai_analysis.REGISTRO_LLAMADA.set(registro)
    t0 = time.perf_counter()
    try:
        bruto = await asyncio.wait_for(
            run_model(version["modelo"], version["sistema"], peticion["usuario"],
                      max_tokens=version["max_tokens"]),
            timeout=inv.TIMEOUT_MODELO)
        error = None
    except asyncio.TimeoutError:
        bruto, error = None, f"el modelo no contestó en {inv.TIMEOUT_MODELO} s"
    except Exception as e:
        bruto, error = None, f"{type(e).__name__}: {str(e)[:200]}"
    finally:
        ai_analysis.REGISTRO_LLAMADA.reset(marca)
    ms = round((time.perf_counter() - t0) * 1000)
    resultado = {"evento_id": caso.get("evento_id"), "orden": caso.get("orden"),
                 "entrada_caracteres": len(texto), "entrada_sha256": _huella(texto),
                 "ms_modelo": ms, "error": error,
                 "modelo_real": registro.get("modelo_real"),
                 "respuesta_original": registro.get("respuesta_bruta")}
    if bruto is None:
        return resultado
    v = inv.validar(bruto)
    estado = inv.estado_de_respuesta(bruto, registro)
    if not v["ok"]:
        resultado.update(error=f"la respuesta no cumple el contrato: {v['motivo']}",
                         estado_respuesta=estado)
        return resultado
    i = v["investigacion"]
    salida = {**{k: i.get(k) for k in ("hay_informacion", "resumen", "hechos",
                                        "implicaciones", "incertidumbres", "fuente")},
              "confianza_guardada": i.get("confianza"),
              "confianza_declarada": estado["confianza_declarada"]}
    verificacion = verificador_hechos.verificar(salida["hechos"], peticion["usuario"])
    resultado.update(salida=salida, estado_respuesta=estado,
                     verificacion_hechos=verificacion,
                     metricas=metricas(salida, verificacion, estado))
    return resultado


def comparar(casos_banco: list, resultados: list) -> dict:
    """La versión ejecutada frente a la histórica, caso a caso y en total."""
    por_id = {r.get("evento_id"): r for r in resultados}
    filas, total = [], {"historica": {}, "version": {}}
    for c in casos_banco:
        base = metricas(c["salida"], c["verificacion_hechos"], c.get("estado_respuesta"))
        r = por_id.get(c["evento_id"]) or {}
        nueva = r.get("metricas")
        filas.append({"evento_id": c["evento_id"], "symbol": c.get("symbol"),
                      "historica": base, "version": nueva, "error": r.get("error")})
        for clave, destino in (("historica", base), ("version", nueva)):
            for k, v in (destino or {}).items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    total[clave][k] = total[clave].get(k, 0) + v
    return {"casos": filas, "totales": total,
            "fallos_de_la_version": sum(1 for f in filas if f["error"])}


async def ejecutar(db, version_nombre: str = "produccion", run_model=None) -> dict:
    """Pasa una versión por los casos congelados y guarda el resultado APARTE.

    No toca `intel_eventos` ni el contador diario de la investigación: el banco gasta
    llamadas al modelo, pero no es producción. Un caso que falla se apunta y se sigue.
    """
    if version_nombre not in VERSIONES:
        return {"ok": False, "motivo": f"versión desconocida: {version_nombre}",
                "versiones": sorted(VERSIONES)}
    if not await manifiesto(db):
        return {"ok": False, "motivo": "el banco no está congelado"}
    version = VERSIONES[version_nombre]()
    lista = await casos(db, con_textos=True)
    inicio = ev._ahora()
    resultados = []
    for caso in lista:
        resultados.append(await ejecutar_caso(caso, version, run_model=run_model))
    descriptor = {k: v for k, v in version.items() if k != "sistema"}
    descriptor["sistema_sha256"] = _huella(version["sistema"])
    doc = {"id": f"ejecucion-{uuid.uuid4().hex[:12]}", "banco": BANCO, "version": descriptor,
           "inicio": inicio, "fin": ev._ahora(),
           "llamadas": len(resultados), "resultados": resultados,
           "comparacion": comparar(lista, resultados)}
    await db[COL_EJECUCIONES].insert_one(dict(doc))
    return {"ok": True, **{k: v for k, v in doc.items() if k != "resultados"}}
