# ── Stage 1: Build Expo web app ───────────────────────────────────────────────
FROM node:20-slim AS web-builder

WORKDIR /web

# Install dependencies first (cache-friendly)
COPY mobile/package.json mobile/package-lock.json* ./
RUN npm ci

# Copy the rest of mobile source
COPY mobile/ ./

# Build Expo for web (output to /web/dist)
RUN npx expo export --platform web

# Inject PWA tags into generated index.html (Expo doesn't include manifest link)
RUN sed -i 's|</head>|<link rel="manifest" href="/manifest.json" />\n<link rel="apple-touch-icon" sizes="192x192" href="/pwa-icons/icon-192.png" />\n<meta name="apple-mobile-web-app-capable" content="yes" />\n<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />\n<meta name="apple-mobile-web-app-title" content="SpesaSmart" />\n</head>|' /web/dist/index.html \
    && sed -i 's|width=device-width, initial-scale=1, shrink-to-fit=no|width=device-width, initial-scale=1, shrink-to-fit=no, viewport-fit=cover|' /web/dist/index.html \
    && sed -i 's|</style>|html, body { height: 100dvh !important; } #root { height: 100dvh !important; }\n</style>|' /web/dist/index.html

# ── Stage 2: Python backend + static dist ─────────────────────────────────────
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

# Copy Expo web build from stage 1
COPY --from=web-builder /web/dist /app/dist

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
