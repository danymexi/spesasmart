# ── Build: Python backend + pre-built static dist ─────────────────────────────
# NOTE: Expo web build is done on the dev machine (npx expo export --platform web)
# and the output (mobile/dist/) is rsynced alongside backend/. This avoids running
# Node.js inside Docker, which OOMs on the 1GB Proxmox LXC.
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for Playwright, pdf2image, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browser and its dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-unifont \
    fonts-dejavu-core \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2t64 libxshmfence1 libxfixes3 \
    && rm -rf /var/lib/apt/lists/* \
    && playwright install chromium

# Copy backend source
COPY backend/ .

# Copy pre-built Expo web assets (built on dev machine, rsynced to server)
COPY mobile/dist/ /app/dist

# Fix: Expo bundles use import.meta which breaks in non-module <script> tags.
# Replace all occurrences with a safe fallback so the bundle loads correctly.
RUN for f in /app/dist/_expo/static/js/web/*.js; do sed -i 's/import\.meta/\(\{\}\)/g' "$f"; done

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
