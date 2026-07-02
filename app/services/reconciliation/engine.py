from collections import Counter
from dataclasses import dataclass, field
from typing import Optional, Union
from app.services.parser.empresa_file import EmpresaRecord
from app.services.parser.sunat_propuesta import SunatRecord

IGV_DIFF_THRESHOLD = 0.10

TIPOS_CONCILIABLES = {"01", "03", "07", "08"}

TIPO_LABELS = {
    "01": "Factura",
    "03": "Boleta",
    "07": "Nota de Crédito",
    "08": "Nota de Débito",
    "09": "Guía de Remisión",
    "04": "Liquidación de Compra",
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


@dataclass
class ScenarioCRecord:
    """En ambos, con diferencias en fecha o montos (1 a 4 campos)."""
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
    diferencias: list[DifferenceDetail]
    es_alerta_roja: bool

    @property
    def campos_diferentes(self) -> set[str]:
        return {d.campo for d in self.diferencias}


@dataclass
class ReconciliationOutput:
    scenario_a: list[ScenarioARecord]
    scenario_b: list[ScenarioBRecord]
    scenario_c: list[ScenarioCRecord]
    excluidos_por_tipo: dict[str, int] = field(default_factory=dict)
    csv_duplicados: int = 0
    sunat_duplicados: int = 0

    @property
    def total_excluidos(self) -> int:
        return sum(self.excluidos_por_tipo.values())

    @property
    def igv_diferencia_total(self) -> float:
        total = 0.0
        for rec in self.scenario_c:
            for diff in rec.diferencias:
                if diff.campo == "igv" and diff.diferencia is not None:
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
) -> ReconciliationOutput:
    conciliables = [r for r in empresa_records if r.key[0] in TIPOS_CONCILIABLES]
    excluidos = Counter(r.key[0] for r in empresa_records if r.key[0] not in TIPOS_CONCILIABLES)

    empresa_index = {r.key: r for r in conciliables}
    sunat_index   = {r.key: r for r in sunat_records}

    csv_duplicados   = len(conciliables) - len(empresa_index)
    sunat_duplicados = len(sunat_records) - len(sunat_index)

    csv_dates: set[str] = {r.fecha_emision for r in conciliables if r.fecha_emision}

    scenario_a: list[ScenarioARecord] = []
    for key, emp in empresa_index.items():
        if key not in sunat_index:
            es_roja = abs(emp.igv) > IGV_DIFF_THRESHOLD
            scenario_a.append(ScenarioARecord(
                tipo_cdp      = emp.tipo_cdp,
                serie         = emp.serie,
                numero        = emp.numero,
                fecha_emision = emp.fecha_emision,
                base_imponible= emp.base_imponible,
                igv           = emp.igv,
                importe_total = emp.importe_total,
                es_alerta_roja= es_roja,
            ))

    scenario_b: list[ScenarioBRecord] = []
    for key, sun in sunat_index.items():
        if key in empresa_index:
            continue
        if csv_dates and sun.fecha_emision not in csv_dates:
            continue
        es_roja = abs(sun.igv) > IGV_DIFF_THRESHOLD
        scenario_b.append(ScenarioBRecord(
            tipo_cdp            = sun.tipo_cdp,
            serie               = sun.serie,
            numero              = sun.numero,
            fecha_emision       = sun.fecha_emision,
            base_imponible_sunat= sun.base_imponible,
            igv_sunat           = sun.igv,
            importe_total_sunat = sun.importe_total,
            es_alerta_roja      = es_roja,
        ))

    scenario_c: list[ScenarioCRecord] = []
    for key in empresa_index.keys() & sunat_index.keys():
        emp = empresa_index[key]
        sun = sunat_index[key]

        diffs: list[DifferenceDetail] = []

        if emp.fecha_emision and sun.fecha_emision and emp.fecha_emision != sun.fecha_emision:
            diffs.append(DifferenceDetail(
                campo         = "fecha",
                valor_empresa = emp.fecha_emision,
                valor_sunat   = sun.fecha_emision,
                diferencia    = None,
            ))

        net_diff = round(emp.base_imponible - sun.base_imponible, 2)
        if abs(net_diff) > 0.01:
            diffs.append(DifferenceDetail(
                campo         = "base_imponible",
                valor_empresa = emp.base_imponible,
                valor_sunat   = sun.base_imponible,
                diferencia    = net_diff,
            ))

        tax_diff = round(emp.igv - sun.igv, 2)
        if abs(tax_diff) > 0.01:
            diffs.append(DifferenceDetail(
                campo         = "igv",
                valor_empresa = emp.igv,
                valor_sunat   = sun.igv,
                diferencia    = tax_diff,
            ))

        total_diff = round(emp.importe_total - sun.importe_total, 2)
        if abs(total_diff) > 0.01:
            diffs.append(DifferenceDetail(
                campo         = "importe_total",
                valor_empresa = emp.importe_total,
                valor_sunat   = sun.importe_total,
                diferencia    = total_diff,
            ))

        if diffs:
            es_roja = any(
                d.campo == "igv" and d.diferencia is not None and abs(d.diferencia) > IGV_DIFF_THRESHOLD
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
                diferencias            = diffs,
                es_alerta_roja         = es_roja,
            ))

    return ReconciliationOutput(
        scenario_a=scenario_a,
        scenario_b=scenario_b,
        scenario_c=scenario_c,
        excluidos_por_tipo=dict(excluidos),
        csv_duplicados=csv_duplicados,
        sunat_duplicados=sunat_duplicados,
    )
