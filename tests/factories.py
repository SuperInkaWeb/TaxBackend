"""Constructores de registros para los tests del motor de conciliación."""
from app.services.parser.empresa_file import EmpresaRecord
from app.services.parser.sunat_propuesta import SunatRecord


def emp(serie="B001", numero="1", tipo="03", fecha="2026-05-04",
        base=100.0, igv=18.0, total=118.0, exo=0.0, ina=0.0,
        ruc="", estado="", bi_dgng=0.0, igv_dgng=0.0, bi_dng=0.0,
        igv_dng=0.0, ang=0.0, moneda="PEN", tc=1.0) -> EmpresaRecord:
    return EmpresaRecord(
        tipo_cdp=tipo, serie=serie, numero=numero, importe_total=total,
        fecha_emision=fecha, base_imponible=base, igv=igv,
        mto_exonerado=exo, mto_inafecto=ina, status_description=estado,
        ruc_proveedor=ruc, bi_dgng=bi_dgng, igv_dgng=igv_dgng,
        bi_dng=bi_dng, igv_dng=igv_dng, valor_adq_ng=ang, moneda=moneda, tipo_cambio=tc,
    )


def sun(serie="B001", numero="1", tipo="03", fecha="2026-05-04",
        base=100.0, igv=18.0, total=118.0, exo=0.0, ina=0.0,
        ruc="", bi_dgng=0.0, igv_dgng=0.0, bi_dng=0.0, igv_dng=0.0,
        ang=0.0, moneda="PEN", tc=1.0) -> SunatRecord:
    return SunatRecord(
        tipo_cdp=tipo, serie=serie, numero=numero, fecha_emision=fecha,
        base_imponible=base, igv=igv, importe_total=total, tipo_cambio=tc,
        mto_exonerado=exo, mto_inafecto=ina, ruc_proveedor=ruc,
        bi_dgng=bi_dgng, igv_dgng=igv_dgng, bi_dng=bi_dng, igv_dng=igv_dng,
        valor_adq_ng=ang, moneda=moneda,
    )
