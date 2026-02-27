# Deploy SpesaSmart su Proxmox

Guida per hostare SpesaSmart su un mini PC con Proxmox, accessibile da internet tramite Cloudflare Tunnel (gratis, senza dominio proprio).

**Architettura finale:**

```
Internet → Cloudflare Tunnel → LXC Container (Proxmox)
                                  ├── Docker: PostgreSQL
                                  ├── Docker: Backend FastAPI (porta 8000)
                                  └── Docker: Telegram Bot
```

---

## Parte 1 — Creare il Container LXC su Proxmox

### 1.1 Scaricare il template Debian 12

1. Apri la UI di Proxmox (`https://<IP-PROXMOX>:8006`)
2. Nel pannello sinistro, seleziona il tuo nodo (es. `pve`)
3. Vai su **local (pve)** → **CT Templates** → **Templates**
4. Cerca `debian-12-standard` e clicca **Download**

### 1.2 Creare il container

1. Clicca **Create CT** (in alto a destra)
2. Compila i campi:

| Campo | Valore |
|-------|--------|
| CT ID | `100` (o il primo libero) |
| Hostname | `spesasmart` |
| Password | scegli una password per root |
| Template | `debian-12-standard` (appena scaricato) |
| Disk | `20 GB` |
| CPU | `2 cores` |
| Memory | `1024 MB` |
| Swap | `512 MB` |
| Network | `DHCP` (o IP statico se preferisci) |

3. Clicca **Finish** per creare il container

### 1.3 Abilitare Nesting (necessario per Docker)

1. Seleziona il container `100` nel pannello sinistro
2. Vai su **Options** → **Features**
3. Spunta **Nesting** ✅
4. (Opzionale) Spunta **keyctl** se disponibile

### 1.4 Avviare il container

1. Seleziona il container e clicca **Start**
2. Vai su **Console** per accedere alla shell

---

## Parte 2 — Setup automatico (1 comando)

### 2.1 Accedere alla shell del container

Dalla console Proxmox, effettua il login come `root` con la password scelta.

### 2.2 Eseguire lo script di setup

Copia tutto il progetto SpesaSmart dal Mac al container. Dal Mac:

```bash
# Dal Mac, copia il progetto nel container LXC
scp -r /Users/danielemessi/spesasmart root@<IP-CONTAINER>:/opt/spesasmart
```

Poi, dentro il container:

```bash
bash /opt/spesasmart/deploy/setup-lxc.sh
```

Lo script:
- Installa Docker CE e il plugin docker compose
- Chiede interattivamente le API key (Gemini, Telegram)
- Avvia tutti e 3 i container Docker
- Esegue il primo scraping Tiendeo

**Alternativa — Se il progetto e' su un repo Git:**

```bash
apt update && apt install -y curl git
git clone https://github.com/TUO-UTENTE/spesasmart.git /opt/spesasmart
bash /opt/spesasmart/deploy/setup-lxc.sh
```

---

## Parte 3 — Cloudflare Tunnel (accesso esterno gratuito)

Il tunnel Cloudflare permette di esporre la porta 8000 su internet senza aprire porte sul router e senza possedere un dominio.

### 3.1 Creare un account Cloudflare

1. Vai su [dash.cloudflare.com](https://dash.cloudflare.com) e registrati (gratis)
2. Non serve aggiungere un dominio per usare i tunnel

### 3.2 Installare cloudflared nel container

Dentro il container LXC:

```bash
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
  | tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null

echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" \
  | tee /etc/apt/sources.list.d/cloudflared.list

apt update && apt install -y cloudflared
```

### 3.3 Autenticarsi e creare il tunnel

```bash
# Login (apre un link da copiare nel browser)
cloudflared tunnel login

# Creare il tunnel
cloudflared tunnel create spesasmart
```

Prendi nota dell'**ID del tunnel** (es. `a1b2c3d4-...`).

### 3.4 Configurare il tunnel

Crea il file di configurazione:

```bash
cat > /root/.cloudflared/config.yml << 'EOF'
tunnel: <TUNNEL-ID>
credentials-file: /root/.cloudflared/<TUNNEL-ID>.json

ingress:
  - service: http://localhost:8000
  - service: http_status:404
EOF
```

Sostituisci `<TUNNEL-ID>` con l'ID del tunnel ottenuto al passo precedente.

### 3.5 Testare il tunnel

```bash
cloudflared tunnel run spesasmart
```

L'app sara' raggiungibile su:
```
https://<TUNNEL-ID>.cfargotunnel.com
```

### 3.6 Avviare il tunnel come servizio (avvio automatico)

```bash
cloudflared service install
systemctl enable cloudflared
systemctl start cloudflared
```

Verifica che sia attivo:

```bash
systemctl status cloudflared
```

### 3.7 (Opzionale) Dominio personalizzato

Se in futuro vuoi usare un tuo dominio (es. `spesasmart.tuodominio.it`):

1. Aggiungi il dominio a Cloudflare (gratis per DNS)
2. Vai su **Zero Trust** → **Tunnels** → **spesasmart** → **Public Hostname**
3. Aggiungi: `spesasmart.tuodominio.it` → `http://localhost:8000`

---

## Parte 4 — Verifica

### 4.1 Controllare i container Docker

```bash
cd /opt/spesasmart
docker compose ps
```

Devono essere tutti **running**:
- `spesasmart-db-1`
- `spesasmart-backend-1`
- `spesasmart-telegram-bot-1`

### 4.2 Test API in locale

```bash
# Status scraping
curl http://localhost:8000/api/v1/scraping/status

# Trigger scraping manuale Esselunga
curl -X POST "http://localhost:8000/api/v1/scraping/trigger/esselunga/sync?source=tiendeo"
```

Il trigger dovrebbe restituire >100 prodotti.

### 4.3 Test accesso esterno

Da un browser o dal telefono, apri:
```
https://<TUNNEL-ID>.cfargotunnel.com/api/v1/scraping/status
```

### 4.4 Test Telegram Bot

1. Apri Telegram e cerca il tuo bot
2. Invia `/start`
3. Invia `/offerte`
4. Invia `/cerca latte`

---

## Manutenzione

### Aggiornare l'app

```bash
cd /opt/spesasmart
git pull                          # se usi git
docker compose build --no-cache
docker compose up -d
```

### Vedere i log

```bash
docker compose logs -f backend      # log backend
docker compose logs -f telegram-bot  # log bot
docker compose logs -f db           # log database
```

### Riavviare tutto

```bash
cd /opt/spesasmart
docker compose restart
```

### Backup database

```bash
docker compose exec db pg_dump -U spesasmart spesasmart > backup_$(date +%Y%m%d).sql
```

### Ripristino database

```bash
docker compose exec -T db psql -U spesasmart spesasmart < backup_XXXXXXXX.sql
```
