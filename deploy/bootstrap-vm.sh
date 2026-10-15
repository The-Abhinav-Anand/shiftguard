#!/usr/bin/env bash
# Bring up the SHIFTGUARD judge stack on a fresh Ubuntu 22.04/24.04 VM (amd64 or arm64).
#
#   sudo SHIFTGUARD_DOMAIN=shiftguard.example.org bash deploy/bootstrap-vm.sh [--dataset-from DIR]
#
# Steps, each safe to repeat:
#   1. install Docker Engine and the compose plugin from Docker's apt repository;
#   2. clone the repository into SHIFTGUARD_DIR, or fast-forward an existing checkout;
#   3. build the image on this machine (so it matches the VM's CPU architecture), or use a
#      preloaded one when SHIFTGUARD_SKIP_BUILD=1;
#   4. create deploy/judge.env and deploy/postgres.env with a random database password,
#      only if they do not exist yet (an existing NEBIUS_API_KEY is never touched);
#   5. place the verified Bank dataset in deploy/datasets/ (copied from --dataset-from,
#      or downloaded from UCI and checked against the frozen SHA-256 contract);
#   6. docker compose up -d, with both assistant flags off unless deploy/.env turns them on.
#
# The script never prints a password, a database URL or an API key.
set -euo pipefail

REPO_URL="${SHIFTGUARD_REPO_URL:-https://github.com/The-Abhinav-Anand/shiftguard.git}"
BRANCH="${SHIFTGUARD_BRANCH:-main}"
APP_DIR="${SHIFTGUARD_DIR:-/opt/shiftguard}"
IMAGE="${SHIFTGUARD_IMAGE:-shiftguard:judge}"
DATASET_FROM=""

while [ $# -gt 0 ]; do
  case "$1" in
    --dataset-from) DATASET_FROM="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

log() { printf '[bootstrap] %s\n' "$*"; }

if [ "$(id -u)" -ne 0 ]; then
  echo "run as root (sudo)" >&2
  exit 1
fi
if [ -z "${SHIFTGUARD_DOMAIN:-}" ]; then
  echo "set SHIFTGUARD_DOMAIN to the public host name, for example shiftguard.duckdns.org" >&2
  exit 1
fi

# 1. Docker Engine and the compose plugin (https://docs.docker.com/engine/install/ubuntu/).
if ! docker compose version >/dev/null 2>&1; then
  log "installing Docker Engine and the compose plugin"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install --yes ca-certificates curl git openssl
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${UBUNTU_CODENAME:-$VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update
  apt-get install --yes docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
else
  log "Docker $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo present) already installed"
fi
command -v git >/dev/null || apt-get install --yes git
command -v openssl >/dev/null || apt-get install --yes openssl

# Some cloud images (Oracle's Ubuntu among them) ship an iptables INPUT chain that rejects
# everything except SSH. Open 80/443 there too; the cloud firewall must allow them as well.
if command -v iptables >/dev/null && iptables -S INPUT 2>/dev/null | grep -q -- '-j REJECT'; then
  for port in 80 443; do
    iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null \
      || iptables -I INPUT 1 -p tcp --dport "$port" -j ACCEPT
  done
  iptables -C INPUT -p udp --dport 443 -j ACCEPT 2>/dev/null || iptables -I INPUT 1 -p udp --dport 443 -j ACCEPT
  if command -v netfilter-persistent >/dev/null; then netfilter-persistent save >/dev/null 2>&1 || true; fi
  log "opened TCP 80/443 and UDP 443 in the host firewall"
fi

# 2. Repository.
if [ -d "$APP_DIR/.git" ]; then
  log "updating $APP_DIR ($BRANCH)"
  git -C "$APP_DIR" fetch --quiet origin "$BRANCH"
  git -C "$APP_DIR" checkout --quiet "$BRANCH"
  git -C "$APP_DIR" merge --ff-only --quiet "origin/$BRANCH"
else
  log "cloning $REPO_URL ($BRANCH) into $APP_DIR"
  git clone --quiet --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"
log "source commit $(git rev-parse HEAD)"

# 3. Image, built natively for this architecture. On a small VM (about 1 GB of RAM) the frontend
#    build can run out of memory; load an image built elsewhere for the same architecture
#    (docker save | ssh ... docker load) and set SHIFTGUARD_SKIP_BUILD=1.
if [ "${SHIFTGUARD_SKIP_BUILD:-0}" = "1" ] && docker image inspect "$IMAGE" >/dev/null 2>&1; then
  log "using the preloaded image $IMAGE (SHIFTGUARD_SKIP_BUILD=1)"
else
  log "building $IMAGE for $(dpkg --print-architecture)"
  docker build --quiet -t "$IMAGE" . >/dev/null
fi
log "image $(docker image inspect --format '{{.Id}}' "$IMAGE")"

# 4. Secrets, created once and readable by root only.
umask 077
if [ ! -f deploy/postgres.env ] || [ ! -f deploy/judge.env ]; then
  if [ -f deploy/postgres.env ] || [ -f deploy/judge.env ]; then
    echo "only one of deploy/judge.env and deploy/postgres.env exists; fix or remove it first" >&2
    exit 1
  fi
  password="$(openssl rand -hex 24)"
  printf 'POSTGRES_USER=shiftguard\nPOSTGRES_DB=shiftguard\nPOSTGRES_PASSWORD=%s\n' "$password" > deploy/postgres.env
  printf 'SHIFTGUARD_DB_URL=postgresql://shiftguard:%s@postgres:5432/shiftguard\nNEBIUS_API_KEY=\n' "$password" > deploy/judge.env
  unset password
  log "created deploy/judge.env and deploy/postgres.env with a new random password"
else
  log "keeping existing deploy/judge.env and deploy/postgres.env"
fi
# Compose interpolation values (not secrets). Existing lines win.
touch deploy/.env
grep -q '^SHIFTGUARD_DOMAIN=' deploy/.env || echo "SHIFTGUARD_DOMAIN=$SHIFTGUARD_DOMAIN" >> deploy/.env
grep -q '^SHIFTGUARD_IMAGE=' deploy/.env || echo "SHIFTGUARD_IMAGE=$IMAGE" >> deploy/.env
grep -q '^SHIFTGUARD_AGENT_ENABLED=' deploy/.env || echo "SHIFTGUARD_AGENT_ENABLED=false" >> deploy/.env
grep -q '^SHIFTGUARD_GENERAL_CHAT_ENABLED=' deploy/.env || echo "SHIFTGUARD_GENERAL_CHAT_ENABLED=false" >> deploy/.env
umask 022

# 5. Verified Bank dataset (readiness re-checks the frozen identity on every start).
mkdir -p deploy/datasets
csv=deploy/datasets/bank-additional-full.csv
manifest=deploy/datasets/bank-marketing.manifest.json
if [ -n "$DATASET_FROM" ]; then
  log "copying the Bank dataset from $DATASET_FROM"
  install -m 0644 "$DATASET_FROM/bank-additional-full.csv" "$csv"
  install -m 0644 "$DATASET_FROM/bank-marketing.manifest.json" "$manifest"
elif [ ! -f "$csv" ] || [ ! -f "$manifest" ]; then
  log "downloading the Bank dataset from UCI and checking it against data/manifests/bank.json"
  docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp \
    -v "$APP_DIR:/src:ro" -v "$APP_DIR/deploy/datasets:/out" -w /tmp \
    --entrypoint python "$IMAGE" /src/scripts/download_datasets.py --dataset bank \
    --manifest /src/data/manifests/bank.json --cache /tmp/no-cache.zip \
    --raw-output /tmp/bank-marketing.zip --clean-output /out/bank-additional-full.csv \
    --run-manifest-output /out/bank-marketing.manifest.json >/dev/null
fi
chmod 0755 deploy/datasets
chmod 0644 "$csv" "$manifest"

# 6. Start.
log "starting the stack for https://$SHIFTGUARD_DOMAIN"
docker compose -f deploy/compose.judge.yaml up -d --remove-orphans
for _ in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8000/health/ready >/dev/null 2>&1; then
    log "ready: $(curl -fsS http://127.0.0.1:8000/health/ready)"
    log "next: python3 scripts/check_hosted_release.py --base-url https://$SHIFTGUARD_DOMAIN --output probe.json"
    exit 0
  fi
  sleep 5
done
echo "the API did not become ready within 5 minutes; see: docker compose -f deploy/compose.judge.yaml logs api" >&2
curl -sS http://127.0.0.1:8000/health/ready >&2 || true
exit 1
