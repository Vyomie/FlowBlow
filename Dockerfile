# FlowBlow -- container image for Google Cloud Run (or any container host).
#
#   docker build -t flowblow .
#   docker run -p 8080:8080 flowblow
#
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    FLOWBLOW_MODE=html

# System dependency: a colour emoji font so node `icon` glyphs render.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

# Cloud Run provides $PORT (default 8080). Bind to 0.0.0.0.
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn flowblow.api:app --host 0.0.0.0 --port ${PORT:-8080}"]
