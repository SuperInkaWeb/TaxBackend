import asyncio
import os
import re
import shutil
import subprocess
import tempfile
import httpx
import zipfile
import io
from dataclasses import dataclass, field
from enum import Enum

_7ZIP_PATHS = [
    r"C:\Program Files\7-Zip\7z.exe",
    r"C:\Program Files (x86)\7-Zip\7z.exe",
    "7z",
    "7za",
]

def _find_7zip() -> str | None:
    for path in _7ZIP_PATHS:
        if os.path.isabs(path):
            if os.path.exists(path):
                return path
        else:
            if shutil.which(path):
                return path
    return None

SIRE_BASE = "https://api-sire.sunat.gob.pe/v1/contribuyente/migeigv/libros"
POLL_INTERVAL_SECONDS = 10
POLL_MAX_ATTEMPTS = 360


class TicketStatus(str, Enum):
    en_proceso = "En Proceso"
    terminado  = "Terminado"
    error      = "Error"


@dataclass
class TicketFileInfo:
    """Información del archivo generado por SUNAT al terminar el ticket."""
    nom_archivo:      str
    cod_tipo_archivo: str | None
    cod_proceso:      str | None
    per_tributario:   str
    archivo_reportes: list[dict] = field(default_factory=list)


def _extract_ticket(resp: "httpx.Response", context: str) -> str:
    """
    Extrae el numTicket de la respuesta de exportapropuesta.
    Si SUNAT devuelve 422 con error 42209 (proceso en curso), reutiliza ese ticket.
    """
    data = resp.json() if "application/json" in resp.headers.get("content-type", "") else {}

    if resp.status_code == 200:
        ticket = data.get("numTicket")
        if not ticket:
            raise ValueError(f"SUNAT no devolvió numTicket para {context}: {data}")
        return ticket

    if resp.status_code == 422:
        errors = data.get("errors", [])
        cod = errors[0].get("cod") if errors else None
        if cod == 42209:
            msg = errors[0].get("msg", "")
            match = re.search(r"Ticket:\s*(\d+)", msg)
            if match:
                return match.group(1)
        raise ValueError(f"SUNAT 422 para {context}: {data}")

    resp.raise_for_status()
    raise ValueError(f"Respuesta inesperada {resp.status_code} para {context}")


def _auth_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }


def _extract_file_info(registro: dict, periodo: str) -> TicketFileInfo:
    """
    Extrae nombre de archivo y metadatos del registro de ticket.
    Manual 5.16/5.31: el archivo está en archivoReporte[] o en detalleTicket.
    Soporta ZIP particionado: archivoReporte[] puede tener múltiples entradas.
    """
    nom_archivo      = None
    cod_tipo_archivo = None
    archivo_reportes = registro.get("archivoReporte") or []

    if archivo_reportes:
        first            = archivo_reportes[0]
        nom_archivo      = first.get("nomArchivoReporte")
        cod_tipo_archivo = (
            first.get("codTipoArchivoReporte")
            or first.get("codTipoAchivoReporte")
        )

    if not nom_archivo:
        detalle = registro.get("detalleTicket") or {}
        nom_archivo = detalle.get("nomArchivoReporte")

    if not nom_archivo:
        nom_archivo = registro.get("nomArchivoDescarga") or registro.get("nomArchivoImportacion")

    return TicketFileInfo(
        nom_archivo      = nom_archivo or "",
        cod_tipo_archivo = cod_tipo_archivo,
        cod_proceso      = registro.get("codProceso"),
        per_tributario   = registro.get("perTributario") or periodo,
        archivo_reportes = archivo_reportes,
    )


def _get_estado(registro: dict) -> str:
    """
    Extrae el estado del ticket. El campo varía entre respuestas:
    - detalleTicket.desEstadoEnvio  → "Terminado"
    - desEstadoProceso              → "Terminado" / "En Proceso"
    - desEstado                     → legacy
    """
    detalle = registro.get("detalleTicket") or {}
    return (
        detalle.get("desEstadoEnvio")
        or registro.get("desEstadoProceso")
        or registro.get("desEstado")
        or ""
    )


async def consultar_ticket(
    get_token,
    ticket_url: str,
    num_ticket: str,
    periodo: str,
    cod_libro: str,
) -> tuple[str, TicketFileInfo] | None:
    """
    Consulta ÚNICA del estado de un ticket (sin polling).
    Devuelve (estado, TicketFileInfo) o None si SUNAT ya no conoce el ticket.
    """
    token = await get_token(False)
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.get(
            ticket_url,
            headers=_auth_headers(token),
            params={
                "perIni":         periodo,
                "perFin":         periodo,
                "page":           1,
                "perPage":        20,
                "codLibro":       cod_libro,
                "codOrigenEnvio": "2",
                "numTicket":      num_ticket,
            }
        )
        if resp.status_code == 401:
            token = await get_token(True)
            resp = await client.get(
                ticket_url,
                headers=_auth_headers(token),
                params={
                    "perIni":         periodo,
                    "perFin":         periodo,
                    "page":           1,
                    "perPage":        20,
                    "codLibro":       cod_libro,
                    "codOrigenEnvio": "2",
                    "numTicket":      num_ticket,
                }
            )
        resp.raise_for_status()

    registros = resp.json().get("registros", [])
    if not registros:
        return None
    registro = registros[0]
    return _get_estado(registro), _extract_file_info(registro, periodo)


async def poll_ticket(
    get_token,
    ticket_url: str,
    num_ticket: str,
    periodo: str,
    cod_libro: str,
) -> TicketFileInfo:
    """
    Hace polling hasta que el ticket esté Terminado.
    Devuelve TicketFileInfo con nombre de archivo y metadatos de descarga.
    Manual SIRE Ventas 5.16 / Compras 5.31.

    get_token: async callable (force_refresh: bool) -> str.
    El polling puede durar 30 min y SUNAT invalida el token si se emite otro
    para el mismo usuario SOL — ante un 401 se renueva y se reintenta.
    """
    for _ in range(POLL_MAX_ATTEMPTS):
        await asyncio.sleep(POLL_INTERVAL_SECONDS)

        token = await get_token(False)
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.get(
                    ticket_url,
                    headers=_auth_headers(token),
                    params={
                        "perIni":         periodo,
                        "perFin":         periodo,
                        "page":           1,
                        "perPage":        20,
                        "codLibro":       cod_libro,
                        "codOrigenEnvio": "2",
                        "numTicket":      num_ticket,
                    }
                )
        except httpx.TransportError:
            continue

        if resp.status_code == 401:
            await get_token(True)
            continue
        if resp.status_code >= 500:
            continue
        resp.raise_for_status()

        registros = resp.json().get("registros", [])
        if not registros:
            continue

        registro = registros[0]
        estado   = _get_estado(registro)

        if "terminado" in estado.lower():
            return _extract_file_info(registro, periodo)

        if "error" in estado.lower():
            raise ValueError(f"SUNAT devolvió error en ticket {num_ticket}: {registro}")

    raise TimeoutError(f"El ticket {num_ticket} no finalizó en {POLL_MAX_ATTEMPTS * POLL_INTERVAL_SECONDS}s")


async def download_file(
    get_token,
    download_url: str,
    info: TicketFileInfo,
    cod_libro: str,
    num_ticket: str,
) -> bytes:
    """
    Descarga el ZIP generado por SUNAT y devuelve los bytes del primer TXT.
    Manual SIRE Ventas 5.17 / Compras 5.32: endpoint archivoreporte.
    Soporta ZIP particionado (.z01, .z02, ..., .zip) — descarga y ensambla todas las partes.

    get_token: async callable (force_refresh: bool) -> str; renueva ante 401.
    """
    partes = info.archivo_reportes if info.archivo_reportes else [
        {
            "nomArchivoReporte":   info.nom_archivo,
            "codTipoAchivoReporte": info.cod_tipo_archivo,
        }
    ]

    partes_bytes: list[tuple[str, bytes]] = []

    for parte in partes:
        nombre   = parte.get("nomArchivoReporte", "")
        cod_tipo = parte.get("codTipoAchivoReporte") or parte.get("codTipoArchivoReporte")

        params = {
            "nomArchivoReporte": nombre,
            "codLibro":          cod_libro,
            "perTributario":     info.per_tributario,
            "numTicket":         num_ticket,
        }
        if cod_tipo is not None:
            params["codTipoArchivoReporte"] = cod_tipo
        if info.cod_proceso is not None:
            params["codProceso"] = info.cod_proceso

        token = await get_token(False)
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.get(download_url, headers=_auth_headers(token), params=params)
            if resp.status_code == 401:
                token = await get_token(True)
                resp = await client.get(download_url, headers=_auth_headers(token), params=params)
            resp.raise_for_status()

        partes_bytes.append((nombre, resp.content))

    return await asyncio.to_thread(_extract_txt_from_parts, partes_bytes)


def _extract_txt_from_parts(partes_bytes: list[tuple[str, bytes]]) -> bytes:
    """Extrae el TXT del ZIP (simple o particionado). Corre en hilo aparte."""
    if len(partes_bytes) == 1:
        with zipfile.ZipFile(io.BytesIO(partes_bytes[0][1])) as zf:
            txt_files = [f for f in zf.namelist() if f.lower().endswith(".txt")]
            target    = txt_files[0] if txt_files else (zf.namelist()[0] if zf.namelist() else None)
            if not target:
                raise ValueError("El ZIP de SUNAT no contiene ningún archivo")
            return zf.read(target)

    bin_7z = _find_7zip()
    if not bin_7z:
        raise RuntimeError(
            "ZIP particionado recibido de SUNAT pero 7-zip no está instalado. "
            "Windows: instalar https://www.7-zip.org/ | Linux: apt install p7zip-full"
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        partes_bytes.sort(key=lambda t: os.path.splitext(t[0])[1].lower())
        for nombre, data in partes_bytes:
            with open(os.path.join(tmpdir, nombre), "wb") as f:
                f.write(data)

        primer = os.path.join(tmpdir, partes_bytes[0][0])
        result = subprocess.run(
            [bin_7z, "e", primer, f"-o{tmpdir}", "-y", "-aoa"],
            capture_output=True, timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"7-zip falló ({result.returncode}): {result.stderr.decode(errors='replace')[:500]}"
            )

        txt_files = [f for f in os.listdir(tmpdir) if f.lower().endswith(".txt")]
        if not txt_files:
            archivos = os.listdir(tmpdir)
            if not archivos:
                raise ValueError("7-zip no extrajo ningún archivo")
            no_partes = [f for f in archivos if not re.match(r".*\.(z\d+|zip)$", f.lower())]
            txt_files = no_partes if no_partes else archivos

        with open(os.path.join(tmpdir, txt_files[0]), "rb") as f:
            return f.read()
