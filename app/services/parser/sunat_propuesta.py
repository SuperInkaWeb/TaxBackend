import io
from dataclasses import dataclass

import pandas as pd


@dataclass(slots=True)
class SunatRecord:
    tipo_cdp: str
    serie: str
    numero: str
    fecha_emision: str
    base_imponible: float
    igv: float
    importe_total: float
    tipo_cambio: float
    mto_exonerado: float = 0.0
    mto_inafecto: float = 0.0
    ruc_proveedor: str = ""
    razon_social: str = ""
    bi_dgng: float = 0.0
    igv_dgng: float = 0.0
    bi_dng: float = 0.0
    igv_dng: float = 0.0
    valor_adq_ng: float = 0.0
    moneda: str = ""

    @property
    def key(self) -> tuple:
        r = str(self.ruc_proveedor).strip()
        t = str(self.tipo_cdp).strip().upper()
        s = str(self.serie).strip().upper()
        n = str(self.numero).strip().lstrip("0") or "0"
        return (r, t, s, n)


VENTAS_COL_IDX: dict[str, int] = {
    "fecha_emision":           4,
    "tipo_cdp":                6,
    "serie":                   7,
    "numero":                  8,
    "base_imponible":          14,
    "descuento_base_imponible":15,
    "igv":                     16,
    "descuento_igv":           17,
    "mto_exonerado":           18,
    "mto_inafecto":            19,
    "importe_total":           25,
    "tipo_cambio":             27,
}

COMPRAS_COL_IDX: dict[str, int] = {
    "fecha_emision":  4,
    "tipo_cdp":       6,
    "serie":          7,
    "numero":         9,
    "ruc_proveedor":  12,
    "razon_social":   13,
    "base_imponible": 14,
    "igv":            15,
    "bi_dgng":        16,
    "igv_dgng":       17,
    "bi_dng":         18,
    "igv_dng":        19,
    "valor_adq_ng":   20,
    "importe_total":  24,
    "moneda":         25,
    "tipo_cambio":    26,
}


def _col(df: pd.DataFrame, idx: int) -> pd.Series:
    """Devuelve la columna idx como Series de strings limpios."""
    if idx >= len(df.columns):
        return pd.Series("", index=df.index, dtype=str)
    return df.iloc[:, idx].fillna("").astype(str).str.strip()


def _to_float(series: pd.Series) -> pd.Series:
    """Convierte una Series de strings a float, coma → punto, errores → 0."""
    return pd.to_numeric(series.str.replace(",", ".", regex=False), errors="coerce").fillna(0.0)


def parse_sunat_propuesta(txt_bytes: bytes, tipo_libro: str) -> list[SunatRecord]:
    """
    Parsea el TXT pipe-delimited de la propuesta SUNAT.
    tipo_libro: 'compras' | 'ventas'

    Usa operaciones vectorizadas (sin iterrows) para manejar archivos de millones de filas.
    """
    text: str | None = None
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = txt_bytes.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = txt_bytes.decode("latin-1", errors="replace")

    col_idx = COMPRAS_COL_IDX if tipo_libro == "compras" else VENTAS_COL_IDX

    df = pd.read_csv(
        io.StringIO(text),
        sep="|",
        header=0,
        dtype=str,
        skip_blank_lines=True,
        on_bad_lines="skip",
    )

    if df.empty:
        return []

    tipo_cdp_s = _col(df, col_idx["tipo_cdp"])
    serie_s    = _col(df, col_idx["serie"])
    numero_s   = _col(df, col_idx["numero"])

    mask = ~(tipo_cdp_s.eq("") & serie_s.eq("") & numero_s.eq(""))
    df         = df[mask].reset_index(drop=True)
    tipo_cdp_s = tipo_cdp_s[mask].reset_index(drop=True)
    serie_s    = serie_s[mask].reset_index(drop=True)
    numero_s   = numero_s[mask].reset_index(drop=True)

    fecha_s   = _col(df, col_idx["fecha_emision"])
    base_s    = _to_float(_col(df, col_idx["base_imponible"]))
    igv_s     = _to_float(_col(df, col_idx["igv"]))
    importe_s = _to_float(_col(df, col_idx["importe_total"]))
    tc_s      = _to_float(_col(df, col_idx["tipo_cambio"])).replace(0.0, 1.0)

    if "descuento_base_imponible" in col_idx:
        base_s = base_s + _to_float(_col(df, col_idx["descuento_base_imponible"]))
    if "descuento_igv" in col_idx:
        igv_s = igv_s + _to_float(_col(df, col_idx["descuento_igv"]))

    if "mto_exonerado" in col_idx:
        exo_s = _to_float(_col(df, col_idx["mto_exonerado"]))
        ina_s = _to_float(_col(df, col_idx["mto_inafecto"]))
    else:
        exo_s = pd.Series(0.0, index=df.index)
        ina_s = pd.Series(0.0, index=df.index)

    def _opt_str(campo: str) -> pd.Series:
        return _col(df, col_idx[campo]) if campo in col_idx else pd.Series("", index=df.index)

    def _opt_num(campo: str) -> pd.Series:
        return _to_float(_col(df, col_idx[campo])) if campo in col_idx else pd.Series(0.0, index=df.index)

    ruc_s     = _opt_str("ruc_proveedor")
    razon_s   = _opt_str("razon_social")
    moneda_s  = _opt_str("moneda")
    dgng_b_s  = _opt_num("bi_dgng")
    dgng_i_s  = _opt_num("igv_dgng")
    dng_b_s   = _opt_num("bi_dng")
    dng_i_s   = _opt_num("igv_dng")
    ang_s     = _opt_num("valor_adq_ng")

    parts = fecha_s.str.extract(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
    is_slash = parts[0].notna()
    fecha_norm = (parts[2] + "-" + parts[1].str.zfill(2) + "-" + parts[0].str.zfill(2)).where(is_slash, fecha_s)

    records = [
        SunatRecord(
            tipo_cdp       = t,
            serie          = s,
            numero         = n,
            fecha_emision  = f,
            base_imponible = b,
            igv            = g,
            importe_total  = m,
            tipo_cambio    = tc,
            mto_exonerado  = exo,
            mto_inafecto   = ina,
            ruc_proveedor  = ruc,
            razon_social   = razon,
            bi_dgng        = dgb,
            igv_dgng       = dgi,
            bi_dng         = dnb,
            igv_dng        = dni,
            valor_adq_ng   = ang,
            moneda         = mon,
        )
        for t, s, n, f, b, g, m, tc, exo, ina, ruc, razon, dgb, dgi, dnb, dni, ang, mon in zip(
            tipo_cdp_s.tolist(), serie_s.tolist(), numero_s.tolist(), fecha_norm.tolist(),
            base_s.tolist(), igv_s.tolist(), importe_s.tolist(), tc_s.tolist(),
            exo_s.tolist(), ina_s.tolist(),
            ruc_s.tolist(), razon_s.tolist(),
            dgng_b_s.tolist(), dgng_i_s.tolist(), dng_b_s.tolist(), dng_i_s.tolist(),
            ang_s.tolist(), moneda_s.tolist(),
        )
    ]

    return records
