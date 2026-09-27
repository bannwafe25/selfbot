set -a
source /home/agentuser/selfbot/.env
set +a
exec /home/agentuser/selfbot/.venv/bin/selfbot
