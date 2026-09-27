# Headless cloud runner for the Naukri bot (EC2). Local `nk` runs stay headed.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    RUN_HEADLESS=true

WORKDIR /app

# Playwright Chromium system deps (single layer, cleaned up)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2 libatspi2.0-0 \
    libx11-6 libxcb1 libxext6 libxi6 libxtst6 wget ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt \
 && python -m playwright install chromium

COPY src/ ./src/
COPY dashboard/ ./dashboard/

# Runtime mounts: resume + persistent browser profile + data live outside image
VOLUME ["/app/data"]

CMD ["python", "-m", "src.orchestrator.run"]
