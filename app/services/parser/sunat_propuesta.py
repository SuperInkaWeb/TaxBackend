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

    @property
    def key(self) -> tuple:
        t = str(self.tipo_cdp).strip().upper()
        s = str(self.serie).strip().upper()
        n = str(self.numero).strip().lstrip("0") or "0"
        return (t, s, n)


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
    "base_imponible": 14,
    "igv":            15,
    "importe_total":  24,
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
        )
        for t, s, n, f, b, g, m, tc, exo, ina in zip(
            tipo_cdp_s.tolist(), serie_s.tolist(), numero_s.tolist(), fecha_norm.tolist(),
            base_s.tolist(), igv_s.tolist(), importe_s.tolist(), tc_s.tolist(),
            exo_s.tolist(), ina_s.tolist(),
        )
    ]

    return records
