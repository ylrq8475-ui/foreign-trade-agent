#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/customer-workspace"
PYTHON_BIN="python3"

sudo mkdir -p "$APP_DIR"
sudo chown -R "$USER":"$USER" "$APP_DIR"

rsync -av --delete \
  --exclude ".git" \
  --exclude "__pycache__" \
  --exclude "*.pyc" \
  ./ "$APP_DIR"/

cd "$APP_DIR"

$PYTHON_BIN -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

sudo cp deploy/aliyun-light/customer-workspace.service /etc/systemd/system/customer-workspace.service
sudo systemctl daemon-reload
sudo systemctl enable customer-workspace
sudo systemctl restart customer-workspace

echo "App deployed to $APP_DIR"
