"""
Script de prueba: descarga la propuesta SUNAT (ventas o compras) para un periodo.

Qué hace:
  1. Obtiene token OAuth de SUNAT
  2. Solicita exportación de la propuesta → obtiene ticket
  3. Hace polling hasta que SUNAT termina de generar el archivo (puede tardar 30 min)
  4. Descarga el ZIP (puede estar partido en .z01, .z02, ...)
  5. Extrae el TXT y muestra las primeras líneas para verificar

Uso:
  python scripts/test_propuesta.py

Cambia las variables de configuración abajo según el periodo y libro a probar.
"""

import sys
import os
import asyncio
import zipfile
import json
import re
import subprocess

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import httpx


def _load_env():
    """Carga variables desde el .env de la raíz del proyecto (sin dependencias externas)."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


_load_env()

RUC           = os.environ.get("TEST_SUNAT_RUC", "")
USUARIO_SOL   = os.environ.get("TEST_SUNAT_USUARIO", "")
CLAVE_SOL     = os.environ.get("TEST_SUNAT_CLAVE", "")
CLIENT_ID     = os.environ.get("TEST_SUNAT_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("TEST_SUNAT_CLIENT_SECRET", "")

if not all([RUC, USUARIO_SOL, CLAVE_SOL, CLIENT_ID, CLIENT_SECRET]):
    print("ERROR: faltan credenciales. Define en el .env de la raíz:")
    print("  TEST_SUNAT_RUC, TEST_SUNAT_USUARIO, TEST_SUNAT_CLAVE,")
    print("  TEST_SUNAT_CLIENT_ID, TEST_SUNAT_CLIENT_SECRET")
    sys.exit(1)

PERIODO    = "202606"
TIPO_LIBRO = "ventas"

EXISTING_TICKET = ""

POLL_INTERVAL = 10
POLL_MAX      = 180

TOKEN_URL = "https://api-seguridad.sunat.gob.pe/v1/clientessol/{client_id}/oauth2/token/"
SCOPE     = "https://api-sire.sunat.gob.pe"
BASE      = "https://api-sire.sunat.gob.pe/v1/contribuyente/migeigv/libros"

CONFIGS = {
    "ventas": {
        "label":      "Ventas (RVIE)",
        "cod_libro":  "140000",
        "url_export": f"{BASE}/rvie/propuesta/web/propuesta/{{periodo}}/exportapropuesta",
        "params_exp": {"codTipoArchivo": "0"},
    },
    "compras": {
        "label":      "Compras (RCE)",
        "cod_libro":  "080000",
        "url_export": f"{BASE}/rce/propuesta/web/propuesta/{{periodo}}/exportacioncomprobantepropuesta",
        "params_exp": {"codTipoArchivo": "0", "codOrigenEnvio": "2"},
    },
}

URL_TICKET  = f"{BASE}/rvierce/gestionprocesosmasivos/web/masivo/consultaestadotickets"
URL_ARCHIVO = f"{BASE}/rvierce/gestionprocesosmasivos/web/masivo/archivoreporte"
SEVEN_ZIP   = next(
    (p for p in [r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe"]
     if os.path.exists(p)),
    None,
)


def separador(titulo=""):
    if titulo:
        print(f"\n{'─'*60}")
        print(f"  {titulo}")
        print(f"{'─'*60}")
    else:
        print(f"{'─'*60}")


async def main():
    cfg = CONFIGS.get(TIPO_LIBRO)
    if not cfg:
        print(f"ERROR: TIPO_LIBRO debe ser 'ventas' o 'compras', no '{TIPO_LIBRO}'")
        return

    output_dir = os.path.join(os.path.dirname(__file__), "output", f"{PERIODO}_{TIPO_LIBRO}")
    os.makedirs(output_dir, exist_ok=True)

    separador(f"Descarga propuesta SUNAT — {cfg['label']}")
    print(f"  RUC:     {RUC}")
    print(f"  Periodo: {PERIODO}")
    print(f"  Salida:  {output_dir}")

    separador("1/4  Token OAuth")
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            TOKEN_URL.format(client_id=CLIENT_ID),
            data={
                "grant_type":    "password",
                "scope":         SCOPE,
                "client_id":     CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "username":      f"{RUC}{USUARIO_SOL}",
                "password":      CLAVE_SOL,
            },
        )
    if r.status_code != 200:
        print(f"  ERROR {r.status_code}: {r.text[:500]}")
        return
    token = r.json()["access_token"]
    print(f"  OK — token: {token[:50]}...")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
        "Accept":        "application/json",
    }

    separador("2/4  Ticket de exportación")

    if EXISTING_TICKET:
        num_ticket = EXISTING_TICKET
        print(f"  Usando ticket existente: {num_ticket}")
    else:
        url_exp = cfg["url_export"].format(periodo=PERIODO)
        print(f"  URL:    {url_exp}")
        print(f"  Params: {cfg['params_exp']}")

        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(url_exp, headers=headers, params=cfg["params_exp"])

        data = r.json() if "application/json" in r.headers.get("content-type", "") else {}
        print(f"  Status: {r.status_code}")

        if r.status_code == 422:
            errors = data.get("errors", [])
            cod_e  = errors[0].get("cod") if errors else None
            if cod_e == 42209:
                msg   = errors[0].get("msg", "")
                match = re.search(r"Ticket:\s*(\d+)", msg)
                if match:
                    num_ticket = match.group(1)
                    print(f"  Proceso en curso — ticket reutilizado: {num_ticket}")
                else:
                    print(f"  ERROR 42209 sin ticket en mensaje: {msg}")
                    return
            else:
                print(f"  ERROR 422:\n{json.dumps(data, indent=2, ensure_ascii=False)[:600]}")
                return
        elif r.status_code != 200:
            print(f"  ERROR {r.status_code}: {r.text[:800]}")
            return
        else:
            num_ticket = data.get("numTicket")
            if not num_ticket:
                print(f"  ERROR: SUNAT no devolvió numTicket\n  Respuesta: {data}")
                return
            print(f"  Ticket obtenido: {num_ticket}")

    separador("3/4  Esperando que SUNAT procese")
    print(f"  Polling cada {POLL_INTERVAL}s, máximo {POLL_MAX * POLL_INTERVAL // 60} min")
    print(f"  (empresas grandes pueden tardar 10-30 min)\n")

    reg              = {}
    archivo_reportes = []
    cod_proceso      = None

    for intento in range(POLL_MAX):
        if intento > 0:
            await asyncio.sleep(POLL_INTERVAL)

        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(
                URL_TICKET,
                headers=headers,
                params={
                    "perIni":         PERIODO,
                    "perFin":         PERIODO,
                    "page":           1,
                    "perPage":        20,
                    "codLibro":       cfg["cod_libro"],
                    "codOrigenEnvio": "2",
                    "numTicket":      num_ticket,
                },
            )

        if r.status_code != 200:
            print(f"\n  ERROR polling {r.status_code}: {r.text[:300]}")
            return

        ticket_data = r.json()

        if intento < 2:
            print(f"  [debug intento {intento+1}]\n{json.dumps(ticket_data, indent=2, ensure_ascii=False)[:2000]}\n")

        registros = ticket_data.get("registros", [])
        if not registros:
            mins_transcurridos = (intento * POLL_INTERVAL) // 60
            print(f"  [{mins_transcurridos:2d} min] esperando...", end="\r")
            continue

        reg         = registros[0]
        cod_proceso = reg.get("codProceso")
        detalle     = reg.get("detalleTicket") or {}
        estado      = (
            detalle.get("desEstadoEnvio")
            or reg.get("desEstadoProceso")
            or reg.get("desEstado")
            or ""
        )

        mins_transcurridos = (intento * POLL_INTERVAL) // 60
        print(f"  [{mins_transcurridos:2d} min] estado: {estado!r}", end="\r")

        if "terminado" in estado.lower():
            archivo_reportes = reg.get("archivoReporte") or []
            print(f"\n  TERMINADO en {mins_transcurridos} min")
            print(f"  archivoReporte ({len(archivo_reportes)} parte(s)):")
            print(f"  {json.dumps(archivo_reportes, indent=2, ensure_ascii=False)}")
            break

        if "error" in estado.lower():
            print(f"\n  SUNAT devolvió error:\n  {json.dumps(reg, indent=2)[:800]}")
            return
    else:
        print(f"\n  ERROR: timeout — SUNAT no terminó en {POLL_MAX * POLL_INTERVAL // 60} min")
        return

    if not archivo_reportes:
        detalle = reg.get("detalleTicket") or {}
        nom = detalle.get("nomArchivoReporte") or reg.get("nomArchivoDescarga")
        if not nom:
            print(f"  ERROR: no se obtuvo nombre de archivo\n  {json.dumps(reg, indent=2)[:1000]}")
            return
        archivo_reportes = [{"nomArchivoReporte": nom}]

    separador(f"4/4  Descargando {len(archivo_reportes)} parte(s)")

    archivos_locales = []
    for idx, parte in enumerate(archivo_reportes):
        nombre   = parte.get("nomArchivoReporte")
        cod_tipo = parte.get("codTipoAchivoReporte") or parte.get("codTipoArchivoReporte")

        params_dl = {
            "nomArchivoReporte": nombre,
            "codLibro":          cfg["cod_libro"],
            "perTributario":     PERIODO,
            "numTicket":         num_ticket,
        }
        if cod_tipo is not None:
            params_dl["codTipoArchivoReporte"] = cod_tipo
        if cod_proceso is not None:
            params_dl["codProceso"] = cod_proceso

        print(f"  Parte {idx+1}/{len(archivo_reportes)}: {nombre}")
        print(f"    Params: {params_dl}")

        async with httpx.AsyncClient(timeout=300) as c:
            r = await c.get(URL_ARCHIVO, headers=headers, params=params_dl)

        print(f"    Status: {r.status_code}  |  {len(r.content):,} bytes")
        if r.status_code != 200:
            print(f"    ERROR: {r.text[:400]}")
            return

        ruta = os.path.join(output_dir, nombre)
        with open(ruta, "wb") as f:
            f.write(r.content)
        print(f"    Guardado: {ruta}")
        archivos_locales.append(ruta)

    separador("Extrayendo TXT del ZIP")

    txt_path = None

    if len(archivos_locales) == 1:
        try:
            with zipfile.ZipFile(archivos_locales[0]) as zf:
                contenido_zip = zf.namelist()
                print(f"  Contenido ZIP: {contenido_zip}")
                for nombre in contenido_zip:
                    datos     = zf.read(nombre)
                    ruta_out  = os.path.join(output_dir, nombre)
                    with open(ruta_out, "wb") as f:
                        f.write(datos)
                    print(f"  Extraído: {nombre}  ({len(datos):,} bytes)")
                    if nombre.lower().endswith(".txt"):
                        txt_path = ruta_out
        except zipfile.BadZipFile as e:
            print(f"  ERROR ZIP: {e}")
            return
    else:
        if not SEVEN_ZIP:
            print("  ERROR: ZIP particionado pero 7-zip no está instalado.")
            print("  Descarga: https://www.7-zip.org/")
            print("  Las partes están en:", output_dir)
            return

        primer = sorted(archivos_locales, key=lambda p: os.path.splitext(p)[1].lower())[0]
        print(f"  Usando 7-zip: {SEVEN_ZIP}")
        print(f"  Primer archivo: {primer}")

        result = subprocess.run(
            [SEVEN_ZIP, "e", primer, f"-o{output_dir}", "-y", "-aoa"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        print(f"  7-zip: {result.stdout[-600:] if result.stdout else '(sin salida)'}")
        if result.returncode != 0:
            print(f"  ERROR 7-zip ({result.returncode}): {result.stderr[:300]}")
            return

        txt_files = [f for f in os.listdir(output_dir) if f.lower().endswith(".txt")]
        for t in txt_files:
            ruta_out = os.path.join(output_dir, t)
            print(f"  Extraído: {t}  ({os.path.getsize(ruta_out):,} bytes)")
        if txt_files:
            txt_path = os.path.join(output_dir, txt_files[0])

    if txt_path and os.path.exists(txt_path):
        separador("Verificación — primeras 5 líneas del TXT")
        with open(txt_path, "rb") as f:
            head = f.read(4096)
        for enc in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                lines = head.decode(enc).splitlines()
                break
            except UnicodeDecodeError:
                continue
        print(f"  Archivo: {txt_path}")
        print(f"  Tamaño:  {os.path.getsize(txt_path):,} bytes")
        print(f"  Encoding detectado: {enc}")
        print()
        for i, line in enumerate(lines[:5], 1):
            cols = line.split("|")
            print(f"  Línea {i} ({len(cols)} columnas):")
            print(f"    {line[:120]}{'...' if len(line) > 120 else ''}")
        print()

    separador()
    print(f"  LISTO")
    print(f"  Archivos en: {output_dir}")
    separador()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--periodo",    default=None)
    ap.add_argument("--tipo-libro", default=None, dest="tipo_libro")
    ap.add_argument("--ticket",     default=None)
    args = ap.parse_args()
    if args.periodo:
        PERIODO = args.periodo
    if args.tipo_libro:
        TIPO_LIBRO = args.tipo_libro
    if args.ticket:
        EXISTING_TICKET = args.ticket
    asyncio.run(main())
