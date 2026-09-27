#!/usr/bin/env bash
# One-time EC2 setup. Run ONCE over SSH as ubuntu. The CI/CD pipeline
# handles every deploy after this — you never touch the server again.
set -euo pipefail

APP_DIR=/opt/naukri-bot
REPO_URL="https://github.com/Imran2909/imran.git"

echo "--- docker ---"
if ! command -v docker >/dev/null; then
  sudo apt-get update
  sudo apt-get install -y ca-certificates curl gnupg
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list
  sudo apt-get update
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  sudo usermod -aG docker ubuntu
fi

echo "--- repo ---"
if [ ! -d "$APP_DIR/.git" ]; then
  sudo mkdir -p /opt
  sudo chown ubuntu:ubuntu /opt
  git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

echo "--- data dirs ---"
mkdir -p naukri-bot/data
touch naukri-bot/data/blocklist.txt

echo ""
echo "NEXT STEPS (on this server):"
echo "  1. Copy your resume in as PDF:  scp 'Imran Sutar - Full Stack Developer.pdf' ubuntu@<EC2-IP>:/opt/naukri-bot/naukri-bot/data/resume.pdf"
echo "  2. Edit blocklist if needed:    nano /opt/naukri-bot/naukri-bot/data/blocklist.txt"
echo "  3. Push to main on your PC — GitHub Actions deploys from here."
echo "  4. Watch logs:                 docker logs -f naukri-bot-bot-1"
