import httpx
from app.services.sire.base import (
    SIRE_BASE, TicketFileInfo, _auth_headers, poll_ticket, download_file,
    _extract_ticket, consultar_ticket,
)

COD_LIBRO_COMPRAS = "080000"

ENDPOINTS = {
    "anio_mes":       f"{SIRE_BASE}/rvierce/padron/web/omisos/{{cod_libro}}/periodos",
    "exportar_prop":  f"{SIRE_BASE}/rce/propuesta/web/propuesta/{{periodo}}/exportacioncomprobantepropuesta",
    "estado_ticket":  f"{SIRE_BASE}/rvierce/gestionprocesosmasivos/web/masivo/consultaestadotickets",
    "descargar_arch": f"{SIRE_BASE}/rvierce/gestionprocesosmasivos/web/masivo/archivoreporte",
}


async def get_periodos_compras(token: str) -> list[dict]:
    headers = _auth_headers(token)
    url = ENDPOINTS["anio_mes"].format(cod_libro=COD_LIBRO_COMPRAS)
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
    return resp.json()


async def solicitar_export_compras(get_token, periodo: str) -> str:
    """
    Fase 1 RCE: GET exportacioncomprobantepropuesta → numTicket.
    Si ya hay un proceso en curso (42209), reutiliza ese ticket.
    """
    url = ENDPOINTS["exportar_prop"].format(periodo=periodo)
    params_exp = {"codTipoArchivo": "0", "codOrigenEnvio": "2"}

    token = await get_token(False)
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.get(url, headers=_auth_headers(token), params=params_exp)
        if resp.status_code == 401:
            token = await get_token(True)
            resp = await client.get(url, headers=_auth_headers(token), params=params_exp)

    return _extract_ticket(resp, f"compras periodo {periodo}")


async def consultar_ticket_compras(get_token, num_ticket: str, periodo: str) -> tuple[str, TicketFileInfo] | None:
    """Consulta única del estado de un ticket de compras. None si SUNAT ya no lo conoce."""
    return await consultar_ticket(
        get_token, ENDPOINTS["estado_ticket"], num_ticket, periodo, COD_LIBRO_COMPRAS,
    )


async def descargar_ticket_compras(get_token, num_ticket: str, periodo: str) -> bytes:
    """
    Fases 2-3 RCE: polling del ticket hasta Terminado + descarga del ZIP → TXT bytes.
    """
    info = await poll_ticket(
        get_token,
        ENDPOINTS["estado_ticket"],
        num_ticket,
        periodo,
        COD_LIBRO_COMPRAS,
    )
    return await download_file(
        get_token,
        ENDPOINTS["descargar_arch"],
        info,
        COD_LIBRO_COMPRAS,
        num_ticket,
    )


async def descargar_propuesta_compras(get_token, periodo: str, ruc: str) -> bytes:
    """
    Flujo completo RCE (fase 1 + fases 2-3).

    get_token: async callable (force_refresh: bool) -> str.
    """
    num_ticket = await solicitar_export_compras(get_token, periodo)
    return await descargar_ticket_compras(get_token, num_ticket, periodo)
