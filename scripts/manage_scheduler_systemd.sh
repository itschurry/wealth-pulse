#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="daily-market-brief-scheduler.service"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$REPO_DIR/logs"
UNIT_PATH="/etc/systemd/system/$SERVICE_NAME"

if [[ ${SUDO_USER:-} != "" ]]; then
  RUN_USER="$SUDO_USER"
else
  RUN_USER="$(id -un)"
fi

RUN_GROUP="$(id -gn "$RUN_USER")"

resolve_python() {
  if [[ -x "$REPO_DIR/.venv/bin/python" ]]; then
    printf '%s\n' "$REPO_DIR/.venv/bin/python"
    return
  fi

  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return
  fi

  echo "python3 executable not found" >&2
  exit 1
}

PYTHON_BIN="$(resolve_python)"

run_root() {
  if [[ $(id -u) -eq 0 ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

write_unit() {
  mkdir -p "$LOG_DIR"

  cat <<EOF | run_root tee "$UNIT_PATH" >/dev/null
[Unit]
Description=Daily Market Brief Scheduler
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
Group=$RUN_GROUP
WorkingDirectory=$REPO_DIR
ExecStart=$PYTHON_BIN $REPO_DIR/scheduler.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
Environment=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
StandardOutput=append:$LOG_DIR/scheduler.systemd.out.log
StandardError=append:$LOG_DIR/scheduler.systemd.err.log

[Install]
WantedBy=multi-user.target
EOF
}

install_service() {
  write_unit
  run_root systemctl daemon-reload
  run_root systemctl enable --now "$SERVICE_NAME"

  echo "Installed and started: $SERVICE_NAME"
  echo "Unit: $UNIT_PATH"
  echo "Stdout log: $LOG_DIR/scheduler.systemd.out.log"
  echo "Stderr log: $LOG_DIR/scheduler.systemd.err.log"
}

uninstall_service() {
  run_root systemctl disable --now "$SERVICE_NAME" >/dev/null 2>&1 || true
  run_root rm -f "$UNIT_PATH"
  run_root systemctl daemon-reload
  echo "Uninstalled: $SERVICE_NAME"
}

start_service() {
  run_root systemctl start "$SERVICE_NAME"
  echo "Started: $SERVICE_NAME"
}

stop_service() {
  run_root systemctl stop "$SERVICE_NAME"
  echo "Stopped: $SERVICE_NAME"
}

restart_service() {
  run_root systemctl restart "$SERVICE_NAME"
  echo "Restarted: $SERVICE_NAME"
}

status_service() {
  run_root systemctl status "$SERVICE_NAME" --no-pager
}

logs_service() {
  run_root journalctl -u "$SERVICE_NAME" -n 100 -f
}

usage() {
  cat <<EOF
Usage: $0 <command>

Commands:
  install    Create systemd unit, enable service, and start scheduler
  uninstall  Stop scheduler, disable service, and remove unit file
  start      Start installed systemd service
  stop       Stop installed systemd service
  restart    Restart installed systemd service
  status     Show systemd service status
  logs       Tail service logs via journalctl
  unit       Print unit file path
EOF
}

case "${1:-}" in
  install)
    install_service
    ;;
  uninstall)
    uninstall_service
    ;;
  start)
    start_service
    ;;
  stop)
    stop_service
    ;;
  restart)
    restart_service
    ;;
  status)
    status_service
    ;;
  logs)
    logs_service
    ;;
  unit)
    echo "$UNIT_PATH"
    ;;
  *)
    usage
    exit 1
    ;;
esac