#!/usr/bin/env bash
set -euo pipefail
exec 9>/docker/langchain-demo/deploy.lock
flock -x 9
repo=/docker/langchain-demo/repo
compose=examples/langchain-transcreveai/docker-compose.yml
previous=$(git -C "$repo" rev-parse HEAD)
rollback() {
  git -C "$repo" checkout --detach "$previous"
  (cd "$repo" && docker compose -f "$compose" up -d --build)
  install -m 644 "$repo/examples/langchain-transcreveai/traefik.yml" /docker/traefik/dynamic/langchain-demo.yml
}
trap 'rollback' ERR
git -C "$repo" fetch --no-tags origin main
git -C "$repo" checkout --detach origin/main
cd "$repo"
docker compose -f "$compose" up -d --build
install -m 644 examples/langchain-transcreveai/traefik.yml /docker/traefik/dynamic/langchain-demo.yml
python3 - <<'PY'
import base64
import time
import urllib.request

values = dict(line.rstrip().split('=', 1) for line in open('/docker/langchain-demo/secrets.env') if '=' in line)
auth = base64.b64encode(('demo:' + values['DEMO_PASSWORD']).encode()).decode()
for attempt in range(15):
    try:
        request = urllib.request.Request('http://127.0.0.1:18051/', headers={'Authorization': 'Basic ' + auth})
        with urllib.request.urlopen(request, timeout=3) as response:
            assert response.status == 200
        break
    except Exception:
        if attempt == 14:
            raise
        time.sleep(2)
print('Aplicação autenticada respondeu HTTP 200.')
PY
install -m 700 examples/langchain-transcreveai/deploy-main.sh /docker/langchain-demo/deploy-main.new
mv -f /docker/langchain-demo/deploy-main.new /docker/langchain-demo/deploy-main
trap - ERR
printf 'Implantado commit %s\n' "$(git rev-parse HEAD)"
