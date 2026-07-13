"""
Tests del mapeo configurable (Nivel 3): validación aritmética que rechaza
mapeos corridos y detección del nivel correcto por formato.
"""
from app.services.parser.mapeo import analizar_archivo, validar_mapeo, parse_con_columnas


def _csv_ventas(n=5):
    """CSV genérico con encabezados propios (no es el formato Tambo conocido)."""
    lineas = ["fecha;tipo;serie;numero;base;igv;total"]
    for i in range(1, n + 1):
        lineas.append(f"04/05/2026;01;F001;{i};100.00;18.00;118.00")
    return ("\n".join(lineas) + "\n").encode("latin-1")


def test_mapeo_correcto_valida_ok():
    content = _csv_ventas()
    config = {
        "delimiter": ";", "encoding": "latin-1", "has_header": True, "skip_rows": 0,
        "serie_numero_combinado": False,
        "columnas": {
            "fecha_emision": 0, "tipo_cdp": 1, "serie": 2, "numero": 3,
            "base_imponible": 4, "igv": 5, "importe_total": 6,
        },
    }
    val = validar_mapeo(content, config, "ventas")
    assert val["ok"]
    assert val["aritmetica_pct"] == 100.0
    recs = parse_con_columnas(content, config, "ventas")
    assert len(recs) == 5 and recs[0].base_imponible == 100.0


def test_mapeo_columnas_corridas_falla_aritmetica():
    """Asignar base/igv a columnas equivocadas → aritmética no cuadra → no ok."""
    content = _csv_ventas()
    config = {
        "delimiter": ";", "encoding": "latin-1", "has_header": True, "skip_rows": 0,
        "serie_numero_combinado": False,
        "columnas": {
            "fecha_emision": 0, "tipo_cdp": 1, "serie": 2, "numero": 3,
            "base_imponible": 3, "igv": 2, "importe_total": 6,
        },
    }
    val = validar_mapeo(content, config, "ventas")
    assert not val["ok"]


def test_mapeo_falta_obligatorio_lo_reporta():
    content = _csv_ventas()
    config = {
        "delimiter": ";", "encoding": "latin-1", "has_header": True, "skip_rows": 0,
        "serie_numero_combinado": False,
        "columnas": {"fecha_emision": 0, "tipo_cdp": 1, "serie": 2},
    }
    val = validar_mapeo(content, config, "ventas")
    assert not val["ok"]
    assert "numero" in val["faltantes"]


def test_analizar_detecta_nivel_desconocido_para_csv_generico():
    """Un CSV con encabezados propios no es plataforma conocida → editable."""
    res = analizar_archivo(_csv_ventas(), "ventas")
    assert res["nivel"] in ("sugerido", "desconocido")
    assert res["solo_lectura"] is False


def test_plataforma_es_solo_lectura():
    """
    El CSV del POS conocido es formato de fábrica: solo lectura, para que la
    conciliación use su lector dedicado (que lee el estado del comprobante).
    """
    filas = ["type description;number;issued date;amount net;amount tax;amount total;status description"]
    filas += [f"Boleta;B001-{100 + i};04/05/2026;100.00;18.00;118.00;Aceptado" for i in range(5)]
    content = ("\n".join(filas) + "\n").encode("latin-1")
    res = analizar_archivo(content, "ventas")
    assert res["nivel"] == "plataforma"
    assert res["solo_lectura"] is True
