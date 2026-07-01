# FlowBlow -- container image for Google Cloud Run (or any container host).
#
#   docker build -t flowblow .
#   docker run -p 8080:8080 flowblow
#
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/opt/mplcache

# System dependency: a colour emoji font so node `icon` glyphs render.
# (Pillow and matplotlib ship self-contained wheels, so nothing else is needed.)
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

# Pre-build the matplotlib font cache and warm the LaTeX renderer so the first
# request isn't slow. Baked into the image, read at runtime.
RUN mkdir -p /opt/mplcache && chmod 777 /opt/mplcache \
    && python -c "import matplotlib.pyplot" \
    && python -c "from flowblow.mathtex import render_math; render_math(r'\$x^2\$')"

# Cloud Run provides $PORT (default 8080). Bind to 0.0.0.0.
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn flowblow.api:app --host 0.0.0.0 --port ${PORT:-8080}"]
