"""
Tests de la auto-sugerencia: detección del comprobante combinado (serie-número)
por contenido, aunque el encabezado no lo delate.
"""
from app.services.parser.mapeo import analizar_archivo


def _csv(headers: str, filas: list[str]) -> bytes:
    return ("\n".join([headers] + filas) + "\n").encode("latin-1")


def test_detecta_serie_numero_combinado_por_contenido():
    """Columna 'Comprobante' con 'F001-123' → sugiere numero + combinado, sin serie aparte."""
    content = _csv(
        "Fecha;TDoc;Comprobante;ValorVenta;Impuesto;TotalDoc",
        [f"04/05/2026;01;F001-{100 + i};100.00;18.00;118.00" for i in range(6)],
    )
    res = analizar_archivo(content, "ventas")
    cfg = res["config"]
    assert cfg["serie_numero_combinado"] is True
    assert "numero" in cfg["columnas"]
    assert cfg["columnas"]["numero"] == 2
    assert "serie" not in cfg["columnas"]


def test_numero_separado_no_marca_combinado():
    """Números puros y serie aparte → NO se marca combinado."""
    content = _csv(
        "Fecha;Tipo;Serie;Numero;Base;IGV;Total",
        [f"04/05/2026;01;F001;{100 + i};100.00;18.00;118.00" for i in range(6)],
    )
    res = analizar_archivo(content, "ventas")
    assert res["config"]["serie_numero_combinado"] is False
