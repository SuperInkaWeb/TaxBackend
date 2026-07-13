"""
Tests de los parsers: detección de formatos PLE, chequeo aritmético que rechaza
archivos corridos, guards de libro cruzado y normalización de tipos.
"""
from app.services.parser.empresa_file import (
    parse_empresa_file, _normalize_tipo_cdp, es_ple_compras,
    _try_parse_as_ple_compras, _try_parse_as_ple_ventas,
)


# ---------- Normalización de tipo de comprobante ----------

def test_normaliza_prefijo_pe():
    assert _normalize_tipo_cdp("PE03") == "03"


def test_normaliza_texto_a_codigo():
    assert _normalize_tipo_cdp("Boleta") == "03"
    assert _normalize_tipo_cdp("Factura") == "01"
    assert _normalize_tipo_cdp("Guía de Remisión") == "09"


def test_codigo_ya_normalizado_se_conserva():
    assert _normalize_tipo_cdp("01") == "01"


# ---------- Construcción de líneas PLE sintéticas ----------

def _linea_ple_compras(serie="E001", numero="892", ruc="20605019031",
                       bi=100.0, igv=18.0, total=118.0, fecha="24/09/2025"):
    c = [""] * 42
    c[0] = "20260500"; c[1] = "31575220"; c[2] = "M31575220"; c[3] = fecha
    c[5] = "01"; c[6] = serie; c[8] = numero; c[10] = "6"; c[11] = ruc
    c[12] = "PROVEEDOR SAC"; c[13] = str(bi); c[14] = str(igv); c[23] = str(total)
    c[24] = "PEN"; c[25] = "1.000"
    return "|".join(c) + "|"


def _linea_ple_ventas(serie="F001", numero="100", bi=100.0, igv=18.0,
                      total=118.0, fecha="04/05/2026"):
    c = [""] * 36
    c[0] = "20260500"; c[1] = "0001"; c[2] = "M0001"; c[3] = fecha
    c[5] = "01"; c[6] = serie; c[7] = numero; c[10] = "6"; c[11] = "20563529378"
    c[12] = "CLIENTE"; c[13] = str(bi); c[15] = str(igv); c[24] = str(total)
    c[25] = "PEN"; c[26] = "1.000"
    return "|".join(c) + "|"


# ---------- Detección y aritmética PLE compras ----------

def test_ple_compras_valido_se_parsea():
    txt = ("\n".join(_linea_ple_compras(numero=str(i)) for i in range(1, 4)) + "\n").encode("latin-1")
    assert es_ple_compras(txt)
    recs = _try_parse_as_ple_compras(txt)
    assert recs is not None and len(recs) == 3
    assert recs[0].ruc_proveedor == "20605019031"
    assert recs[0].key == ("20605019031", "01", "E001", "1")


def test_ple_compras_aritmetica_no_cuadra_se_rechaza():
    """total ≠ base+igv en toda la muestra → None (posible estructura corrida)."""
    txt = ("\n".join(
        _linea_ple_compras(numero=str(i), bi=100.0, igv=18.0, total=999.0)
        for i in range(1, 20)
    ) + "\n").encode("latin-1")
    assert _try_parse_as_ple_compras(txt) is None


def test_ple_ventas_valido_se_parsea():
    txt = ("\n".join(_linea_ple_ventas(numero=str(i)) for i in range(1, 4)) + "\n").encode("latin-1")
    recs = _try_parse_as_ple_ventas(txt)
    assert recs is not None and len(recs) == 3
    assert recs[0].base_imponible == 100.0 and recs[0].igv == 18.0


# ---------- Guards de libro cruzado ----------

def test_ple_ventas_subido_a_compras_se_rechaza():
    txt = ("\n".join(_linea_ple_ventas(numero=str(i)) for i in range(1, 4)) + "\n").encode("latin-1")
    recs, mapping = parse_empresa_file(txt, "x.txt", None, "compras")
    assert recs == []
    assert not mapping.known_format
    assert any("VENTAS" in w for w in mapping.warnings)


def test_ple_compras_subido_a_ventas_se_rechaza():
    txt = ("\n".join(_linea_ple_compras(numero=str(i)) for i in range(1, 4)) + "\n").encode("latin-1")
    recs, mapping = parse_empresa_file(txt, "x.txt", None, "ventas")
    assert recs == []
    assert not mapping.known_format
    assert any("COMPRAS" in w for w in mapping.warnings)


def test_compras_valido_se_acepta_por_parse_empresa_file():
    txt = ("\n".join(_linea_ple_compras(numero=str(i)) for i in range(1, 4)) + "\n").encode("latin-1")
    recs, mapping = parse_empresa_file(txt, "x.txt", None, "compras")
    assert mapping.known_format and len(recs) == 3
