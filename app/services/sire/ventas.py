import httpx
from app.services.sire.base import (
    SIRE_BASE, TicketFileInfo, _auth_headers, poll_ticket, download_file,
    _extract_ticket, consultar_ticket,
)

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
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
    return resp.json()


async def solicitar_export_ventas(get_token, periodo: str) -> str:
    """
    Fase 1 RVIE: GET exportapropuesta?codTipoArchivo=0 → numTicket.
    Si ya hay un proceso en curso (42209), reutiliza ese ticket.
    """
    url = ENDPOINTS["exportar_prop"].format(periodo=periodo)

    token = await get_token(False)
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.get(url, headers=_auth_headers(token), params={"codTipoArchivo": "0"})
        if resp.status_code == 401:
            token = await get_token(True)
            resp = await client.get(url, headers=_auth_headers(token), params={"codTipoArchivo": "0"})

    return _extract_ticket(resp, f"ventas periodo {periodo}")


async def consultar_ticket_ventas(get_token, num_ticket: str, periodo: str) -> tuple[str, TicketFileInfo] | None:
    """Consulta única del estado de un ticket de ventas. None si SUNAT ya no lo conoce."""
    return await consultar_ticket(
        get_token, ENDPOINTS["estado_ticket"], num_ticket, periodo, COD_LIBRO_VENTAS,
    )


async def descargar_ticket_ventas(get_token, num_ticket: str, periodo: str) -> str:
    """
    Fases 2-3 RVIE: polling del ticket hasta Terminado + descarga del ZIP.
    Devuelve la RUTA a un archivo temporal con el TXT (el llamador lo borra).
    """
    info = await poll_ticket(
        get_token,
        ENDPOINTS["estado_ticket"],
        num_ticket,
        periodo,
        COD_LIBRO_VENTAS,
    )
    return await download_file(
        get_token,
        ENDPOINTS["descargar_arch"],
        info,
        COD_LIBRO_VENTAS,
        num_ticket,
    )


async def descargar_propuesta_ventas(get_token, periodo: str, ruc: str) -> str:
    """
    Flujo completo RVIE (fase 1 + fases 2-3).

    get_token: async callable (force_refresh: bool) -> str.
    """
    num_ticket = await solicitar_export_ventas(get_token, periodo)
    return await descargar_ticket_ventas(get_token, num_ticket, periodo)
