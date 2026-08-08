

def test_cada_dividendo_lleva_su_propio_id():
    """Sin id, todos entraban con id nulo y el indice unico de Mongo los rechazaba a partir
    del segundo: la importacion fallaba entera con un error de clave duplicada."""
    db = _DB()
    _correr(cartera_api.importar_dividendos(db, _DIVS))
    ids = [d.get("id") for d in db.dividendos.docs]
    assert all(ids) and len(set(ids)) == len(ids)
