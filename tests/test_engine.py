"""
Tests del motor de conciliación — la lógica que calcula A/B/C/D y crédito fiscal.
Protege la aritmética de los escenarios contra regresiones silenciosas.
"""
from app.services.reconciliation.engine import reconcile
from tests.factories import emp, sun


# ---------- Clasificación base ----------

def test_espejo_todo_coincide_va_a_d():
    """Archivo idéntico a SUNAT → todo en D, nada en A/B/C."""
    registros = [emp(numero=str(i)) for i in range(1, 6)]
    espejo = [sun(numero=str(i)) for i in range(1, 6)]
    out = reconcile(registros, espejo, "ventas")
    assert len(out.scenario_d) == 5
    assert out.scenario_a == [] and out.scenario_b == [] and out.scenario_c == []


def test_solo_en_empresa_va_a_a():
    out = reconcile([emp(numero="1")], [], "ventas")
    assert len(out.scenario_a) == 1
    assert out.scenario_a[0].numero == "1"


def test_solo_en_sunat_va_a_b():
    out = reconcile([], [sun(numero="9")], "ventas")
    assert len(out.scenario_b) == 1
    assert out.scenario_b[0].numero == "9"


def test_diferencia_de_igv_va_a_c_con_alerta_roja():
    out = reconcile([emp(igv=18.0)], [sun(igv=25.0)], "ventas")
    assert len(out.scenario_c) == 1
    rec = out.scenario_c[0]
    assert "igv" in rec.campos_diferentes
    assert rec.es_alerta_roja  # diff > umbral 0.10


def test_diferencia_menor_a_un_centavo_es_d():
    """Tolerancia: 100.00 vs 100.004 coincide → D, no C."""
    out = reconcile([emp(base=100.00)], [sun(base=100.004)], "ventas")
    assert len(out.scenario_d) == 1
    assert out.scenario_c == []


# ---------- Aritmética que cierra (la identidad A+C+D) ----------

def test_identidad_a_mas_c_mas_d_igual_conciliables():
    empresa = [emp(numero="1"), emp(numero="2", igv=99.0), emp(numero="3")]
    sunat = [sun(numero="2"), sun(numero="3"), sun(numero="8")]
    out = reconcile(empresa, sunat, "ventas")
    # #1 solo empresa (A), #2 difiere (C), #3 coincide (D), #8 solo sunat (B)
    assert len(out.scenario_a) == 1
    assert len(out.scenario_c) == 1
    assert len(out.scenario_d) == 1
    assert len(out.scenario_b) == 1
    unicos = len(out.scenario_a) + len(out.scenario_c) + len(out.scenario_d)
    assert unicos == 3  # los 3 conciliables del archivo


# ---------- Filtros de tipo ----------

def test_guias_de_remision_excluidas_en_ventas():
    out = reconcile([emp(tipo="09", numero="1"), emp(tipo="03", numero="2")], [], "ventas")
    assert out.excluidos_por_tipo.get("09") == 1
    assert len(out.scenario_a) == 1  # solo la boleta


def test_duplicados_se_cuentan_una_vez():
    empresa = [emp(numero="1"), emp(numero="1")]  # misma llave
    out = reconcile(empresa, [], "ventas")
    assert out.csv_duplicados == 1
    assert len(out.scenario_a) == 1


# ---------- Filtro de fechas del Escenario B (ventas) ----------

def test_b_filtra_por_cobertura_declarada():
    empresa = [emp(numero="1", fecha="2026-05-04")]
    sunat = [
        sun(numero="1", fecha="2026-05-04"),   # coincide → D
        sun(numero="7", fecha="2026-05-10"),   # SUNAT, día declarado → B
        sun(numero="8", fecha="2026-05-15"),   # SUNAT, día NO declarado → fuera
    ]
    out = reconcile(empresa, sunat, "ventas", {"2026-05-04", "2026-05-10"})
    assert len(out.scenario_b) == 1
    assert out.scenario_b[0].fecha_emision == "2026-05-10"


def test_b_cobertura_vacia_es_mes_completo():
    empresa = [emp(numero="1", fecha="2026-05-04")]
    sunat = [sun(numero="1", fecha="2026-05-04"), sun(numero="8", fecha="2026-05-20")]
    out = reconcile(empresa, sunat, "ventas", set())
    assert len(out.scenario_b) == 1  # el del día 20 aparece


# ---------- Compras: llave con RUC, 12 campos, B sin filtro ----------

def test_compras_llave_incluye_ruc_proveedor():
    """Misma serie-número de proveedores distintos NO colisionan en compras."""
    empresa = [
        emp(tipo="01", serie="F001", numero="1", ruc="20111111111"),
        emp(tipo="01", serie="F001", numero="1", ruc="20222222222"),
    ]
    sunat = [
        sun(tipo="01", serie="F001", numero="1", ruc="20111111111"),
        sun(tipo="01", serie="F001", numero="1", ruc="20222222222"),
    ]
    out = reconcile(empresa, sunat, "compras")
    assert len(out.scenario_d) == 2  # ambos coinciden por su RUC
    assert out.csv_duplicados == 0


def test_compras_compara_destino_mixto_dgng():
    empresa = [emp(tipo="01", serie="F001", numero="1", ruc="20111111111", bi_dgng=50.0)]
    sunat = [sun(tipo="01", serie="F001", numero="1", ruc="20111111111", bi_dgng=99.0)]
    out = reconcile(empresa, sunat, "compras")
    assert len(out.scenario_c) == 1
    assert "bi_dgng" in out.scenario_c[0].campos_diferentes


def test_compras_b_no_filtra_por_fecha():
    """En compras, una factura emitida en otra fecha DEBE aparecer en B."""
    empresa = [emp(tipo="01", serie="F001", numero="1", ruc="20111111111", fecha="2026-05-04")]
    sunat = [
        sun(tipo="01", serie="F001", numero="1", ruc="20111111111", fecha="2026-05-04"),
        sun(tipo="01", serie="F009", numero="5", ruc="20333333333", fecha="2025-03-10"),
    ]
    out = reconcile(empresa, sunat, "compras")
    assert len(out.scenario_b) == 1  # la de marzo aparece pese a la fecha lejana


def test_compras_moneda_distinta_va_a_c():
    empresa = [emp(tipo="01", serie="F001", numero="1", ruc="20111111111", moneda="PEN")]
    sunat = [sun(tipo="01", serie="F001", numero="1", ruc="20111111111", moneda="USD")]
    out = reconcile(empresa, sunat, "compras")
    assert "moneda" in out.scenario_c[0].campos_diferentes


def test_compras_tipos_conciliables_incluyen_dua():
    """Compras acepta tipo 50 (DUA); ventas no."""
    out = reconcile([emp(tipo="50", numero="1", ruc="20111111111")], [], "compras")
    assert len(out.scenario_a) == 1
    assert "50" not in out.excluidos_por_tipo
