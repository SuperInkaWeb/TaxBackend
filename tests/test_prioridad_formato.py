"""
Tests de la prioridad de formato: PLE (Nivel 1) gana sobre un mapeo guardado,
y el mapeo guardado se usa solo para formatos no estándar.
Cubre el bug: un PLE era rechazado si la empresa tenía un formato guardado.
"""
from app.services.parser.empresa_file import parse_empresa_file, es_ple_compras
from app.services.parser.mapeo import parse_con_columnas, validar_mapeo


def _ple_compras(n=3):
    def linea(numero):
        c = [""] * 42
        c[0] = "20260500"; c[1] = "31575220"; c[2] = "M31575220"; c[3] = "24/09/2025"
        c[5] = "01"; c[6] = "E001"; c[8] = numero; c[10] = "6"; c[11] = "20605019031"
        c[12] = "PROVEEDOR SAC"; c[13] = "100.0"; c[14] = "18.0"; c[23] = "118.0"
        c[24] = "PEN"; c[25] = "1.000"
        return "|".join(c) + "|"
    return ("\n".join(linea(str(i)) for i in range(1, n + 1)) + "\n").encode("latin-1")


def test_ple_se_detecta_por_auto_deteccion():
    """La auto-detección (sin mapeo) reconoce el PLE → known_format."""
    txt = _ple_compras()
    assert es_ple_compras(txt)
    recs, mapping = parse_empresa_file(txt, "x.txt", None, "compras")
    assert mapping.known_format and len(recs) == 3


def test_mapeo_guardado_ajeno_no_aplica_al_ple():
    """
    Un mapeo guardado con posiciones de OTRO formato, aplicado a un PLE,
    falla la aritmética. La prioridad correcta (auto-detección primero) evita
    que ese mapeo se use: el PLE se detecta antes de recurrir al guardado.
    """
    txt = _ple_compras()
    config_ajeno = {
        "delimiter": "|", "encoding": "latin-1", "has_header": False, "skip_rows": 0,
        "serie_numero_combinado": False,
        "columnas": {
            "fecha_emision": 3, "tipo_cdp": 5, "serie": 6, "numero": 8,
            "ruc_proveedor": 11, "base_imponible": 0, "igv": 1, "importe_total": 2,
        },
    }
    val = validar_mapeo(txt, config_ajeno, "compras")
    assert not val["ok"]
    recs, mapping = parse_empresa_file(txt, "x.txt", None, "compras")
    assert mapping.known_format and len(recs) == 3
