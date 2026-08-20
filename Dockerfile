FROM python:3.12-slim@sha256:2c941e860699f878900b0edc2403613c234d4b32eda3cc9fa7036991a2a63c4a

ARG APP_VERSION=dev
ARG VCS_REF=unknown
ARG BUILD_DATE=unknown

LABEL org.opencontainers.image.title="Docker Bitcoin Dashboard" \
      org.opencontainers.image.description="A lightweight Docker-native dashboard for Bitcoin Knots" \
      org.opencontainers.image.url="https://github.com/dantux/docker-bitcoin-dashboard" \
      org.opencontainers.image.source="https://github.com/dantux/docker-bitcoin-dashboard" \
      org.opencontainers.image.documentation="https://github.com/dantux/docker-bitcoin-dashboard#readme" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.opencontainers.image.created="${BUILD_DATE}" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN useradd --system --uid 10001 --home-dir /app dashboard

WORKDIR /app
COPY --chown=dashboard:dashboard app.py app.js index.html styles.css icon.svg ./

USER dashboard
EXPOSE 8335

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8335/readyz', timeout=3)"]

CMD ["python", "app.py"]
