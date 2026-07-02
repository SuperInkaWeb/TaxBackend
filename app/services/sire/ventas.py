import httpx
from app.services.sire.base import SIRE_BASE, _auth_headers, poll_ticket, download_file, _extract_ticket

COD_LIBRO_VENTAS = "140000"

ENDPOINTS = {
    "anio_mes":      f"{SIRE_BASE}/rvierce/padron/web/omisos/{{cod_libro}}/periodos",
    "exportar_prop": f"{SIRE_BASE}/rvie/propuesta/web/propuesta/{{periodo}}/exportapropuesta",
    "estado_ticket": f"{SIRE_BASE}/rvierce/gestionprocesosmasivos/web/masivo/consultaestadotickets",
    "descargar_arch": f"{SIRE_BASE}/rvierce/gestionprocesosmasivos/web/masivo/archivoreporte",
}


async def get_periodos_ventas(token: str) -> list[dict]:
    headers = _auth_headers(token)
    url = ENDPOINTS["anio_mes"].format(cod_libro=COD_LIBRO_VENTAS)
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
    return resp.json()


async def descargar_propuesta_ventas(token: str, periodo: str, ruc: str) -> bytes:
    """
    Flujo completo RVIE:
    1. GET exportapropuesta?codTipoArchivo=0 → numTicket
    2. Polling consultaestadotickets → TicketFileInfo
    3. GET archivoreporte → ZIP → TXT bytes
    """
    headers = _auth_headers(token)
    url = ENDPOINTS["exportar_prop"].format(periodo=periodo)

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=headers, params={"codTipoArchivo": "0"})

    num_ticket = _extract_ticket(resp, f"ventas periodo {periodo}")

    info = await poll_ticket(
        token,
        ENDPOINTS["estado_ticket"],
        num_ticket,
        periodo,
        COD_LIBRO_VENTAS,
    )
    return await download_file(
        token,
        ENDPOINTS["descargar_arch"],
        info,
        COD_LIBRO_VENTAS,
        num_ticket,
    )
