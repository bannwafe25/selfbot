#!/bin/bash
# watchdog tg-selfbot: restart kalau log diam > 10 menit
LAST=$(sudo journalctl -u tg-selfbot --since '-10 min' --no-pager -o cat | wc -l)
if [ "$LAST" -eq 0 ]; then
    echo "$(date) - log diam 10 menit, restart tg-selfbot" >> /home/agentuser/watchdog.log
    sudo systemctl restart tg-selfbot
fi
