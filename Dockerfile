FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends p7zip-full \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
COPY scripts ./scripts

EXPOSE 8000

# --proxy-headers + --forwarded-allow-ips=*: detrás del proxy de Railway, hace que
# request.client.host sea la IP real del cliente (X-Forwarded-For) y no la del proxy,
# para que el rate limiting por-IP del login funcione. El contenedor solo es accesible
# vía el proxy de Railway, así que confiar en el header es aceptable aquí.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips=*"]
