from collections import Counter
from dataclasses import dataclass, field
from typing import Optional, Union
from app.services.parser.empresa_file import EmpresaRecord
from app.services.parser.sunat_propuesta import SunatRecord

IGV_DIFF_THRESHOLD = 0.10

TIPOS_CONCILIABLES = {"01", "03", "07", "08"}
TIPOS_CONCILIABLES_COMPRAS = {"01", "07", "08", "30", "50", "54"}

TIPO_LABELS = {
    "01": "Factura",
    "03": "Boleta",
    "05": "Boleto de transporte aéreo",
    "07": "Nota de Crédito",
    "08": "Nota de Débito",
    "09": "Guía de Remisión",
    "04": "Liquidación de Compra",
    "14": "Recibo de servicios públicos",
    "50": "DUA - Importación",
}


@dataclass
class DifferenceDetail:
    campo: str
    valor_empresa: Union[str, float]
    valor_sunat: Union[str, float]
    diferencia: Optional[float]


@dataclass
class ScenarioARecord:
    """En CSV pero no en SUNAT (búsqueda en todo el mes)."""
    tipo_cdp: str
    serie: str
    numero: str
    fecha_emision: str
    base_imponible: float
    igv: float
    importe_total: float
    es_alerta_roja: bool
    status_description: str = ""
    ruc_proveedor: str = ""
    razon_social: str = ""


@dataclass
class ScenarioBRecord:
    """En SUNAT (misma fecha que CSV) pero no en CSV."""
    tipo_cdp: str
    serie: str
    numero: str
    fecha_emision: str
    base_imponible_sunat: float
    igv_sunat: float
    importe_total_sunat: float
    es_alerta_roja: bool
    ruc_proveedor: str = ""
    razon_social: str = ""


@dataclass
class ScenarioCRecord:
    """En ambos, con diferencias en fecha o montos (1 a 6 campos)."""
    tipo_cdp: str
    serie: str
    numero: str
    fecha_emision_empresa: str
    fecha_emision_sunat: str
    base_imponible_empresa: float
    base_imponible_sunat: float
    igv_empresa: float
    igv_sunat: float
    importe_total_empresa: float
    importe_total_sunat: float
    mto_exonerado_empresa: float
    mto_exonerado_sunat: float
    mto_inafecto_empresa: float
    mto_inafecto_sunat: float
    diferencias: list[DifferenceDetail]
    es_alerta_roja: bool
    ruc_proveedor: str = ""
    razon_social: str = ""
    bi_dgng_empresa: float = 0.0
    bi_dgng_sunat: float = 0.0
    igv_dgng_empresa: float = 0.0
    igv_dgng_sunat: float = 0.0
    bi_dng_empresa: float = 0.0
    bi_dng_sunat: float = 0.0
    igv_dng_empresa: float = 0.0
    igv_dng_sunat: float = 0.0
    valor_adq_ng_empresa: float = 0.0
    valor_adq_ng_sunat: float = 0.0
    moneda_empresa: str = ""
    moneda_sunat: str = ""
    tipo_cambio_empresa: float = 0.0
    tipo_cambio_sunat: float = 0.0

    @property
    def campos_diferentes(self) -> set[str]:
        return {d.campo for d in self.diferencias}


@dataclass(slots=True)
class ScenarioDRecord:
    """En ambos, sin diferencias relevantes (los 6 campos coinciden con tolerancia de S/ 0.01)."""
    tipo_cdp: str
    serie: str
    numero: str
    fecha_emision_empresa: str
    fecha_emision_sunat: str
    base_imponible_empresa: float
    base_imponible_sunat: float
    igv_empresa: float
    igv_sunat: float
    importe_total_empresa: float
    importe_total_sunat: float
    mto_exonerado_empresa: float
    mto_exonerado_sunat: float
    mto_inafecto_empresa: float
    mto_inafecto_sunat: float
    ruc_proveedor: str = ""
    razon_social: str = ""
    moneda_empresa: str = ""
    moneda_sunat: str = ""
    tipo_cambio_empresa: float = 0.0
    tipo_cambio_sunat: float = 0.0


@dataclass
class ReconciliationOutput:
    scenario_a: list[ScenarioARecord]
    scenario_b: list[ScenarioBRecord]
    scenario_c: list[ScenarioCRecord]
    scenario_d: list[ScenarioDRecord] = field(default_factory=list)
    excluidos_por_tipo: dict[str, int] = field(default_factory=dict)
    csv_duplicados: int = 0
    sunat_duplicados: int = 0

    @property
    def total_excluidos(self) -> int:
        return sum(self.excluidos_por_tipo.values())

    @property
    def igv_diferencia_total(self) -> float:
        total = 0.0
        campos_igv = {"igv", "igv_dgng", "igv_dng"}
        for rec in self.scenario_c:
            for diff in rec.diferencias:
                if diff.campo in campos_igv and diff.diferencia is not None:
                    total += abs(diff.diferencia)
        for rec in self.scenario_b:
            total += abs(rec.igv_sunat)
        return round(total, 2)

    @property
    def tiene_alertas_rojas(self) -> bool:
        return (
            any(r.es_alerta_roja for r in self.scenario_a)
            or any(r.es_alerta_roja for r in self.scenario_b)
            or any(r.es_alerta_roja for r in self.scenario_c)
        )


def reconcile(
    empresa_records: list[EmpresaRecord],
    sunat_records: list[SunatRecord],
    tipo_libro: str = "ventas",
) -> ReconciliationOutput:
    es_compras = tipo_libro == "compras"
    tipos_ok = TIPOS_CONCILIABLES_COMPRAS if es_compras else TIPOS_CONCILIABLES

    conciliables = [r for r in empresa_records if r.key[1] in tipos_ok]
    excluidos = Counter(r.key[1] for r in empresa_records if r.key[1] not in tipos_ok)

    empresa_index = {r.key: r for r in conciliables}
    sunat_index   = {r.key: r for r in sunat_records}

    csv_duplicados   = len(conciliables) - len(empresa_index)
    sunat_duplicados = len(sunat_records) - len(sunat_index)

    # En ventas el CSV es un corte por fechas del mes → B se filtra a esas fechas.
    # En compras el PLE es el registro íntegro del periodo (con fechas de emisión
    # dispersas por meses) → B compara periodo completo, sin filtro.
    csv_dates: set[str] = (
        set() if es_compras else {r.fecha_emision for r in conciliables if r.fecha_emision}
    )

    scenario_a: list[ScenarioARecord] = []
    for key, emp in empresa_index.items():
        if key not in sunat_index:
            igv_total = emp.igv + emp.igv_dgng + emp.igv_dng
            es_roja = abs(igv_total) > IGV_DIFF_THRESHOLD
            scenario_a.append(ScenarioARecord(
                tipo_cdp      = emp.tipo_cdp,
                serie         = emp.serie,
                numero        = emp.numero,
                fecha_emision = emp.fecha_emision,
                base_imponible= emp.base_imponible,
                igv           = igv_total,
                importe_total = emp.importe_total,
                es_alerta_roja= es_roja,
                status_description = emp.status_description,
                ruc_proveedor = emp.ruc_proveedor,
                razon_social  = emp.razon_social,
            ))

    scenario_b: list[ScenarioBRecord] = []
    for key, sun in sunat_index.items():
        if key in empresa_index:
            continue
        if csv_dates and sun.fecha_emision not in csv_dates:
            continue
        igv_total = sun.igv + sun.igv_dgng + sun.igv_dng
        es_roja = abs(igv_total) > IGV_DIFF_THRESHOLD
        scenario_b.append(ScenarioBRecord(
            tipo_cdp            = sun.tipo_cdp,
            serie               = sun.serie,
            numero              = sun.numero,
            fecha_emision       = sun.fecha_emision,
            base_imponible_sunat= sun.base_imponible,
            igv_sunat           = igv_total,
            importe_total_sunat = sun.importe_total,
            es_alerta_roja      = es_roja,
            ruc_proveedor       = sun.ruc_proveedor,
            razon_social        = sun.razon_social,
        ))

    scenario_c: list[ScenarioCRecord] = []
    scenario_d: list[ScenarioDRecord] = []
    campos_igv = {"igv", "igv_dgng", "igv_dng"}

    for key in empresa_index.keys() & sunat_index.keys():
        emp = empresa_index[key]
        sun = sunat_index[key]

        diffs: list[DifferenceDetail] = []

        def _cmp_num(campo: str, v_emp: float, v_sun: float, tol: float = 0.01, nd: int = 2):
            d = round(v_emp - v_sun, nd)
            if abs(d) > tol:
                diffs.append(DifferenceDetail(campo, v_emp, v_sun, d))

        if emp.fecha_emision and sun.fecha_emision and emp.fecha_emision != sun.fecha_emision:
            diffs.append(DifferenceDetail("fecha", emp.fecha_emision, sun.fecha_emision, None))

        _cmp_num("base_imponible", emp.base_imponible, sun.base_imponible)
        _cmp_num("igv", emp.igv, sun.igv)
        _cmp_num("importe_total", emp.importe_total, sun.importe_total)

        if es_compras:
            _cmp_num("bi_dgng", emp.bi_dgng, sun.bi_dgng)
            _cmp_num("igv_dgng", emp.igv_dgng, sun.igv_dgng)
            _cmp_num("bi_dng", emp.bi_dng, sun.bi_dng)
            _cmp_num("igv_dng", emp.igv_dng, sun.igv_dng)
            _cmp_num("valor_adq_ng", emp.valor_adq_ng, sun.valor_adq_ng)
            if emp.moneda and sun.moneda and emp.moneda.strip().upper() != sun.moneda.strip().upper():
                diffs.append(DifferenceDetail("moneda", emp.moneda, sun.moneda, None))
            _cmp_num("tipo_cambio", emp.tipo_cambio, sun.tipo_cambio, tol=0.001, nd=3)
        else:
            _cmp_num("mto_exonerado", emp.mto_exonerado, sun.mto_exonerado)
            _cmp_num("mto_inafecto", emp.mto_inafecto, sun.mto_inafecto)

        if diffs:
            es_roja = any(
                d.campo in campos_igv and d.diferencia is not None and abs(d.diferencia) > IGV_DIFF_THRESHOLD
                for d in diffs
            )
            scenario_c.append(ScenarioCRecord(
                tipo_cdp               = emp.tipo_cdp,
                serie                  = emp.serie,
                numero                 = emp.numero,
                fecha_emision_empresa  = emp.fecha_emision,
                fecha_emision_sunat    = sun.fecha_emision,
                base_imponible_empresa = emp.base_imponible,
                base_imponible_sunat   = sun.base_imponible,
                igv_empresa            = emp.igv,
                igv_sunat              = sun.igv,
                importe_total_empresa  = emp.importe_total,
                importe_total_sunat    = sun.importe_total,
                mto_exonerado_empresa  = emp.mto_exonerado,
                mto_exonerado_sunat    = sun.mto_exonerado,
                mto_inafecto_empresa   = emp.mto_inafecto,
                mto_inafecto_sunat     = sun.mto_inafecto,
                diferencias            = diffs,
                es_alerta_roja         = es_roja,
                ruc_proveedor          = emp.ruc_proveedor,
                razon_social           = emp.razon_social or sun.razon_social,
                bi_dgng_empresa        = emp.bi_dgng,
                bi_dgng_sunat          = sun.bi_dgng,
                igv_dgng_empresa       = emp.igv_dgng,
                igv_dgng_sunat         = sun.igv_dgng,
                bi_dng_empresa         = emp.bi_dng,
                bi_dng_sunat           = sun.bi_dng,
                igv_dng_empresa        = emp.igv_dng,
                igv_dng_sunat          = sun.igv_dng,
                valor_adq_ng_empresa   = emp.valor_adq_ng,
                valor_adq_ng_sunat     = sun.valor_adq_ng,
                moneda_empresa         = emp.moneda,
                moneda_sunat           = sun.moneda,
                tipo_cambio_empresa    = emp.tipo_cambio,
                tipo_cambio_sunat      = sun.tipo_cambio,
            ))
        else:
            scenario_d.append(ScenarioDRecord(
                tipo_cdp               = emp.tipo_cdp,
                serie                  = emp.serie,
                numero                 = emp.numero,
                fecha_emision_empresa  = emp.fecha_emision,
                fecha_emision_sunat    = sun.fecha_emision,
                base_imponible_empresa = emp.base_imponible,
                base_imponible_sunat   = sun.base_imponible,
                igv_empresa            = emp.igv,
                igv_sunat              = sun.igv,
                importe_total_empresa  = emp.importe_total,
                importe_total_sunat    = sun.importe_total,
                mto_exonerado_empresa  = emp.mto_exonerado,
                mto_exonerado_sunat    = sun.mto_exonerado,
                mto_inafecto_empresa   = emp.mto_inafecto,
                mto_inafecto_sunat     = sun.mto_inafecto,
                ruc_proveedor          = emp.ruc_proveedor,
                razon_social           = emp.razon_social or sun.razon_social,
                moneda_empresa         = emp.moneda,
                moneda_sunat           = sun.moneda,
                tipo_cambio_empresa    = emp.tipo_cambio,
                tipo_cambio_sunat      = sun.tipo_cambio,
            ))

    return ReconciliationOutput(
        scenario_a=scenario_a,
        scenario_b=scenario_b,
        scenario_c=scenario_c,
        scenario_d=scenario_d,
        excluidos_por_tipo=dict(excluidos),
        csv_duplicados=csv_duplicados,
        sunat_duplicados=sunat_duplicados,
    )
