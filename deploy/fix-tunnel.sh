#!/usr/bin/env bash
set -euo pipefail
TID="722eb1ba-6c52-46fc-81a5-bc1d6cf49e1a"
systemctl stop cloudflared || true
CF="/etc/cloudflared/config.yml"
echo "tunnel: $TID" > $CF
echo "credentials-file: /root/.cloudflared/$TID.json" >> $CF
echo "ingress:" >> $CF
echo "  - service: http://localhost:8000" >> $CF
cat $CF
systemctl start cloudflared
sleep 3
systemctl status cloudflared
echo ""
echo "URL: https://$TID.cfargotunnel.com"
