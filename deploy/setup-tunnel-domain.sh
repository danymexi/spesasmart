#!/usr/bin/env bash
set -euo pipefail

TID="722eb1ba-6c52-46fc-81a5-bc1d6cf49e1a"
DOMAIN="spesasmart.spazioitech.it"
CRED="/root/.cloudflared/$TID.json"
CONF="/etc/cloudflared/config.yml"

echo "=== Setup tunnel con dominio ==="

echo "[1/4] Creazione record DNS..."
cloudflared tunnel route dns spesasmart "$DOMAIN" || true

echo "[2/4] Scrittura configurazione..."
mkdir -p /etc/cloudflared
python3 -c "
conf = '''tunnel: $TID
credentials-file: $CRED
ingress:
  - hostname: $DOMAIN
    service: http://localhost:8000
  - service: http_status:404
'''
with open('$CONF', 'w') as f:
    f.write(conf)
print('Config scritto.')
"
cat "$CONF"

echo ""
echo "[3/4] Avvio servizio cloudflared..."
systemctl enable cloudflared 2>/dev/null || true
systemctl restart cloudflared
sleep 3

echo ""
echo "[4/4] Verifica..."
systemctl status cloudflared --no-pager

echo ""
echo "========================================="
echo "  TUNNEL ATTIVO!"
echo "  https://$DOMAIN"
echo "========================================="
