#!/bin/bash
# Record harness goldens from the *unmodified* legacy code running in a
# legacy-style Docker image, and keep the files that differ from golden/.
#
# usage: record_legacy_image.sh OUTPUT_DIR [GIT_REF] [BASE_IMAGE]
#   GIT_REF     legacy commit to build (default df36bdd, the last upstream commit)
#   BASE_IMAGE  default python:3.7-alpine (the legacy Dockerfile's base)
#
# Environment:
#   PYTHON          interpreter with the harness deps (default .venv-legacy-harness/bin/python)
#   BUILD_CA_CERT   extra CA bundle for pip inside the build (TLS-intercepting proxies)
#
# Used to produce golden_reference/py37/: on Python 3.7 the legacy code still
# had Element.getchildren(), so these files show what the getchildren() fix
# (CHANGES.md C-005) must reproduce.
set -euo pipefail
OUT=$(realpath -m "$1"); REF=${2:-df36bdd}; BASE=${3:-python:3.7-alpine}
REPO=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
PYTHON=${PYTHON:-$REPO/.venv-legacy-harness/bin/python}
WORK=$(mktemp -d); trap 'rm -rf "$WORK"; [ -n "${CID:-}" ] && docker rm -f "$CID" >/dev/null 2>&1 || true' EXIT

git -C "$REPO" archive "$REF" bumper requirements.txt create_certs | tar -x -C "$WORK"
cat > "$WORK/Dockerfile" <<DOCKERFILE
# Final stage of the legacy Dockerfile ($REF), without the QEMU scaffolding.
FROM $BASE
COPY requirements.txt /requirements.txt
RUN --mount=type=secret,id=ca,required=false \\
    if [ -f /run/secrets/ca ]; then export PIP_CERT=/run/secrets/ca; fi; pip3 install -r requirements.txt
WORKDIR /bumper
COPY create_certs/ create_certs/
COPY bumper/ bumper/
ENTRYPOINT ["python3", "-m", "bumper"]
DOCKERFILE
SECRET=(); [ -n "${BUILD_CA_CERT:-}" ] && SECRET=(--secret "id=ca,src=$BUILD_CA_CERT")
docker build -q --network host "${SECRET[@]}" -t bumper-legacy-ref "$WORK" >/dev/null

mkdir -p "$WORK/data" "$WORK/golden"; cp "$REPO/tests/passwd" "$WORK/data/passwd"
CID=$(docker run -d -e TZ=BHT-3 -e LOG_TO_STDOUT=true -e BUMPER_LISTEN=0.0.0.0 -e BUMPER_ANNOUNCE_IP=127.0.0.1 \
  -v "$REPO/tests/test_certs:/bumper/certs:ro" -v "$WORK/data:/bumper/data" \
  -p 127.0.0.1::443 -p 127.0.0.1::8007 -p 127.0.0.1::8883 -p 127.0.0.1::5223 bumper-legacy-ref)
port() { docker port "$CID" "$1/tcp" | head -1 | sed 's/.*://'; }

cd "$REPO"
BUMPER_HARNESS_TARGET=host BUMPER_HARNESS_PROFILE=legacy BUMPER_HARNESS_RECORD=1 \
BUMPER_HARNESS_GOLDEN_DIR="$WORK/golden" \
BUMPER_PORT_HTTPS=$(port 443) BUMPER_PORT_HTTP=$(port 8007) BUMPER_PORT_MQTT=$(port 8883) BUMPER_PORT_XMPP=$(port 5223) \
  "$PYTHON" -m pytest tests/harness -q -p no:warnings \
    --ignore=tests/harness/test_golden_changes.py --ignore=tests/harness/test_route_coverage.py

mkdir -p "$OUT"
( cd "$WORK/golden" && find . -name '*.json' | sort ) | while read -r f; do
  if ! cmp -s "$WORK/golden/$f" "$REPO/tests/harness/golden/$f"; then
    mkdir -p "$OUT/$(dirname "$f")"; cp "$WORK/golden/$f" "$OUT/$f"; echo "differs from golden/: ${f#./}"
  fi
done
