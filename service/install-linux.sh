#!/bin/bash
# Install Claude Dispatcher as a systemd service
# Run as root

set -e

SERVICE_FILE="/etc/systemd/system/claude-dispatcher.service"
cp "$(dirname "$0")/claude-dispatcher.service" "$SERVICE_FILE"

systemctl daemon-reload
systemctl enable claude-dispatcher
systemctl start claude-dispatcher

echo "Service installed and started."
echo "  Status:  systemctl status claude-dispatcher"
echo "  Logs:    journalctl -u claude-dispatcher -f"
echo "  Stop:    systemctl stop claude-dispatcher"
echo "  Remove:  systemctl disable claude-dispatcher && rm $SERVICE_FILE"
