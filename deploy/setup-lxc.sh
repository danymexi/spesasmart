#!/usr/bin/env bash
# ============================================================
# SpesaSmart — Setup automatico per LXC Debian 12 su Proxmox
# Eseguire come root dentro il container LXC:
#   bash /opt/spesasmart/deploy/setup-lxc.sh
# ============================================================

set -euo pipefail

PROJECT_DIR="/opt/spesasmart"
ENV_FILE="${PROJECT_DIR}/.env.production"

echo "========================================="
echo "  SpesaSmart — Setup LXC Container"
echo "========================================="
echo ""

# ── 1. Installa dipendenze base ─────────────────────────────
echo "[1/5] Installazione dipendenze di sistema..."
apt-get update -qq
apt-get install -y -qq ca-certificates curl gnupg lsb-release git > /dev/null

# ── 2. Installa Docker CE ───────────────────────────────────
if command -v docker &> /dev/null; then
    echo "[2/5] Docker gia' installato, skip."
else
    echo "[2/5] Installazione Docker CE..."
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/debian/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/debian \
      $(lsb_release -cs) stable" \
      | tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin > /dev/null
    systemctl enable docker
    systemctl start docker
    echo "    Docker installato: $(docker --version)"
fi

# ── 3. Verifica progetto ────────────────────────────────────
if [ ! -f "${PROJECT_DIR}/docker-compose.yml" ]; then
    echo ""
    echo "ERRORE: ${PROJECT_DIR}/docker-compose.yml non trovato."
    echo ""
    echo "Copia il progetto dal Mac con:"
    echo "  scp -r /Users/danielemessi/spesasmart root@<IP-CONTAINER>:/opt/spesasmart"
    echo ""
    echo "Oppure clona da git:"
    echo "  git clone https://github.com/TUO-UTENTE/spesasmart.git ${PROJECT_DIR}"
    echo ""
    exit 1
fi

# ── 4. Configurazione .env ──────────────────────────────────
echo "[3/5] Configurazione variabili d'ambiente..."

if [ ! -f "${ENV_FILE}" ]; then
    echo "ERRORE: ${ENV_FILE} non trovato."
    exit 1
fi

# Chiedi le API key solo se contengono ancora i placeholder
if grep -q "your-gemini-api-key-here" "${ENV_FILE}"; then
    echo ""
    read -rp "Inserisci la tua GEMINI_API_KEY: " GEMINI_KEY
    if [ -n "${GEMINI_KEY}" ]; then
        sed -i "s|your-gemini-api-key-here|${GEMINI_KEY}|g" "${ENV_FILE}"
        echo "    GEMINI_API_KEY configurata."
    else
        echo "    ATTENZIONE: GEMINI_API_KEY non configurata. Lo scraping AI non funzionera'."
    fi
fi

if grep -q "your-telegram-bot-token-here" "${ENV_FILE}"; then
    echo ""
    read -rp "Inserisci il tuo TELEGRAM_BOT_TOKEN: " TG_TOKEN
    if [ -n "${TG_TOKEN}" ]; then
        sed -i "s|your-telegram-bot-token-here|${TG_TOKEN}|g" "${ENV_FILE}"
        echo "    TELEGRAM_BOT_TOKEN configurato."
    else
        echo "    ATTENZIONE: TELEGRAM_BOT_TOKEN non configurato. Il bot non partira'."
    fi
fi

echo ""
echo "    File .env.production configurato."

# ── 5. Avvio Docker Compose ─────────────────────────────────
echo "[4/5] Build e avvio container Docker..."
cd "${PROJECT_DIR}"
docker compose up -d --build

echo ""
echo "    Attendo che il backend sia pronto..."
sleep 10

# Verifica che i container siano running
if docker compose ps | grep -q "running"; then
    echo "    Container avviati con successo!"
    docker compose ps
else
    echo "    ERRORE: Alcuni container non sono partiti."
    docker compose ps
    echo ""
    echo "    Controlla i log con: docker compose logs"
    exit 1
fi

# ── 6. Primo scraping ───────────────────────────────────────
echo ""
echo "[5/5] Esecuzione primo scraping Tiendeo (Esselunga)..."
echo ""

SCRAPING_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
    "http://localhost:8000/api/v1/scraping/trigger/esselunga/sync?source=tiendeo" 2>/dev/null || true)

HTTP_CODE=$(echo "${SCRAPING_RESPONSE}" | tail -1)
BODY=$(echo "${SCRAPING_RESPONSE}" | head -n -1)

if [ "${HTTP_CODE}" = "200" ]; then
    echo "    Scraping completato! Risposta:"
    echo "    ${BODY}" | head -c 500
    echo ""
else
    echo "    Scraping non riuscito (HTTP ${HTTP_CODE})."
    echo "    Puoi riprovare manualmente:"
    echo "    curl -X POST 'http://localhost:8000/api/v1/scraping/trigger/esselunga/sync?source=tiendeo'"
fi

# ── Done ─────────────────────────────────────────────────────
echo ""
echo "========================================="
echo "  SpesaSmart INSTALLATO!"
echo "========================================="
echo ""
echo "  API:      http://localhost:8000/api/v1/scraping/status"
echo "  Logs:     cd ${PROJECT_DIR} && docker compose logs -f"
echo ""
echo "  Prossimo passo: configura Cloudflare Tunnel"
echo "  Segui la guida: ${PROJECT_DIR}/deploy/GUIDA-PROXMOX.md"
echo ""
