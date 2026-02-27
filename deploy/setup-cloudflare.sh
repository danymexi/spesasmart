#!/usr/bin/env bash
# Setup Cloudflare Tunnel nel container LXC
set -euo pipefail

echo "=== Installazione cloudflared ==="

mkdir -p /usr/share/keyrings

curl -fsSL \
  https://pkg.cloudflare.com/cloudflare-main.gpg \
  --output /usr/share/keyrings/cloudflare-main.gpg

REPO="deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg]"
REPO="$REPO https://pkg.cloudflare.com/cloudflared"
REPO="$REPO bookworm main"
echo "$REPO" > /etc/apt/sources.list.d/cloudflared.list

apt-get update -qq
apt-get install -y cloudflared

echo ""
echo "=== cloudflared installato ==="
cloudflared --version
echo ""
echo "=== Login Cloudflare ==="
echo "Si aprira' un link. Copialo nel browser."
echo ""
cloudflared tunnel login

echo ""
echo "=== Creazione tunnel ==="
cloudflared tunnel create spesasmart

TUNNEL_ID=$(cloudflared tunnel list \
  | grep spesasmart | awk '{print $1}')
echo "Tunnel ID: $TUNNEL_ID"

mkdir -p /root/.cloudflared
cat > /root/.cloudflared/config.yml << ENDCONF
tunnel: $TUNNEL_ID
credentials-file: /root/.cloudflared/$TUNNEL_ID.json

ingress:
  - service: http://localhost:8000
  - service: http_status:404
ENDCONF

echo ""
echo "=== Avvio tunnel come servizio ==="
cloudflared service install
systemctl enable cloudflared
systemctl start cloudflared

echo ""
echo "========================================="
echo "  Cloudflare Tunnel ATTIVO!"
echo "========================================="
echo ""
echo "  URL: https://$TUNNEL_ID.cfargotunnel.com"
echo ""
echo "  Verifica:"
echo "  systemctl status cloudflared"
echo ""
