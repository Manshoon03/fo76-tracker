#!/bin/bash
# ============================================================
# FO76 Tracker — Complete Pi Setup
# Safe to re-run: detects existing state and updates in place
# Usage: bash setup-pi.sh
# ============================================================

set -e

REPO_URL="https://github.com/Manshoon03/fo76-tracker.git"
APP_DIR="/home/manny/fo76-tracker"
APP_USER="${USER:-manny}"
SERVICE="fo76-tracker"
PORT=5000
UPDATE_SCRIPT="/home/$APP_USER/update-fo76-tracker.sh"
NGINX_CONF="/etc/nginx/sites-available/fo76.home"
LOG_FILE="/home/$APP_USER/fo76-tracker-update.log"

# ── Colours ──────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn(){ echo -e "${YELLOW}[!]${NC} $1"; }
die() { echo -e "${RED}[✗]${NC} $1"; exit 1; }
hdr() { echo -e "\n${YELLOW}── $1 ──${NC}"; }

echo ""
echo "╔══════════════════════════════════════╗"
echo "║     FO76 Tracker — Pi Setup          ║"
echo "╚══════════════════════════════════════╝"

# ── 1. Clone or pull ─────────────────────────────────────────
hdr "1/6  Repository"
if [ -d "$APP_DIR/.git" ]; then
    warn "Already cloned — pulling latest from master"
    git -C "$APP_DIR" pull origin master
else
    ok "Cloning from GitHub..."
    git clone "$REPO_URL" "$APP_DIR"
fi
ok "Repo ready at $APP_DIR"

# ── 2. Virtual environment ────────────────────────────────────
hdr "2/6  Python virtual environment"
if [ ! -f "$APP_DIR/venv/bin/python" ]; then
    ok "Creating venv..."
    python3 -m venv "$APP_DIR/venv"
else
    ok "venv already exists"
fi
ok "Installing / upgrading dependencies..."
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"
ok "Dependencies installed"

# ── 3. Systemd service ────────────────────────────────────────
hdr "3/6  Systemd service"
sudo python3 - << PYEOF
content = """[Unit]
Description=FO76 Tracker
After=network.target

[Service]
Type=simple
User=$APP_USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python run.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
Environment=FO76_PORT=$PORT

[Install]
WantedBy=multi-user.target
"""
with open('/etc/systemd/system/$SERVICE.service', 'w') as f:
    f.write(content)
print("  Service file written")
PYEOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE"
ok "Service registered and enabled"

# ── 4. Nginx config ───────────────────────────────────────────
hdr "4/6  Nginx reverse proxy"
if [ -f "$NGINX_CONF" ]; then
    ok "Nginx config already exists — leaving it alone"
else
    ok "Writing Nginx config for fo76.home → localhost:$PORT"
    sudo python3 - << PYEOF
content = """server {
    listen 80;
    server_name fo76.home;

    location / {
        proxy_pass         http://localhost:$PORT;
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_read_timeout 120;
    }
}
"""
with open('$NGINX_CONF', 'w') as f:
    f.write(content)
print("  Nginx config written")
PYEOF

    sudo ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/fo76.home
    sudo nginx -t && sudo systemctl reload nginx
    ok "Nginx reloaded"
fi

# ── 5. Auto-update script + cron ─────────────────────────────
hdr "5/6  Auto-update (git pull every 5 min)"
python3 - << PYEOF
content = """#!/bin/bash
# Auto-updater for FO76 Tracker
APP_DIR="$APP_DIR"
cd "\\$APP_DIR"
OLD=\\$(git rev-parse HEAD)
git pull --quiet origin master 2>&1
NEW=\\$(git rev-parse HEAD)
if [ "\\$OLD" != "\\$NEW" ]; then
    echo "[\\$(date '+%Y-%m-%d %H:%M')] Updated \\$OLD -> \\$NEW — reinstalling deps and restarting"
    "\\$APP_DIR/venv/bin/pip" install --quiet -r "\\$APP_DIR/requirements.txt"
    sudo systemctl restart $SERVICE
else
    echo "[\\$(date '+%Y-%m-%d %H:%M')] Up to date (\\${NEW:0:7})"
fi
"""
with open('$UPDATE_SCRIPT', 'w') as f:
    f.write(content)
print("  Update script written")
PYEOF
chmod +x "$UPDATE_SCRIPT"

if crontab -l 2>/dev/null | grep -q "update-fo76-tracker"; then
    ok "Cron job already set"
else
    (crontab -l 2>/dev/null; echo "*/5 * * * * $UPDATE_SCRIPT >> $LOG_FILE 2>&1") | crontab -
    ok "Cron job added (runs every 5 minutes)"
fi

# ── 6. Start and verify ───────────────────────────────────────
hdr "6/6  Start service + health check"
sudo systemctl restart "$SERVICE"

echo -n "  Waiting for port $PORT to open"
for i in $(seq 1 20); do
    if ss -tlnp 2>/dev/null | grep -q ":$PORT"; then
        echo ""
        ok "Port $PORT is listening"
        break
    fi
    echo -n "."
    sleep 1
done

if ! ss -tlnp 2>/dev/null | grep -q ":$PORT"; then
    echo ""
    warn "Port $PORT not yet open — check logs below"
fi

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║           Setup Complete                     ║"
echo "╚══════════════════════════════════════════════╝"
echo ""
sudo systemctl status "$SERVICE" --no-pager
echo ""
LOCAL_IP=$(hostname -I | awk '{print $1}')
ok  "Direct:     http://$LOCAL_IP:$PORT"
ok  "Local DNS:  http://fo76.home"
warn "Logs:       sudo journalctl -u $SERVICE -f"
warn "Update log: tail -f $LOG_FILE"
warn "PiHole DNS: Add 'fo76.home → $LOCAL_IP' if not already set"
echo ""
