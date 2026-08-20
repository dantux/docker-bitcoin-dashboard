FROM python:3.12-slim

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
