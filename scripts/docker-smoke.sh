#!/usr/bin/env bash
# Container smoke test.
#
#  1. build the image (unless IMAGE is given and SKIP_BUILD=1)
#  2. run it with fresh named volumes for data/certs/logs
#  3. wait for the HEALTHCHECK to report healthy
#  4. check it runs as non-root and serves 443 (ip_unprivileged_port_start)
#  5. run the characterisation harness against it (BUMPER_HARNESS_TARGET=host),
#     using the CA the container generated on first start
#  6. restart the container and check the certificates and the database
#     survived
#
# Environment:
#   IMAGE           image tag to build/test (default bumper:smoke)
#   SKIP_BUILD=1    test an existing IMAGE
#   PLATFORM        run the image for this platform (e.g. linux/arm64, needs QEMU)
#   PYTHON          interpreter with the harness deps (default: uv run python)
#   PYTHON_IMAGE, GO_IMAGE   override the Dockerfile's base images (mirrors)
#   BUILD_CA_CERT   CA bundle passed as build secret "ca" (TLS-intercepting proxies)
#   DOCKER_BUILD_NETWORK     e.g. "host"
set -euo pipefail

REPO=$(cd "$(dirname "$0")/.." && pwd)
IMAGE=${IMAGE:-bumper:smoke}
NAME=bumper-smoke-$$
VOLS=("$NAME-data" "$NAME-certs" "$NAME-logs")
WORK=$(mktemp -d)
CID=""

log() { echo "[smoke] $*"; }
cleanup() {
    status=$?
    if [ -n "$CID" ]; then
        if [ $status -ne 0 ]; then
            log "container log (last 200 lines):"
            docker logs --tail 200 "$CID" 2>&1 || true
        fi
        docker rm -f "$CID" >/dev/null 2>&1 || true
    fi
    docker volume rm "${VOLS[@]}" >/dev/null 2>&1 || true
    rm -rf "$WORK"
    exit $status
}
trap cleanup EXIT

if [ "${SKIP_BUILD:-0}" != 1 ]; then
    args=(-t "$IMAGE")
    [ -n "${PYTHON_IMAGE:-}" ] && args+=(--build-arg "PYTHON_IMAGE=$PYTHON_IMAGE")
    [ -n "${GO_IMAGE:-}" ] && args+=(--build-arg "GO_IMAGE=$GO_IMAGE")
    [ -n "${BUILD_CA_CERT:-}" ] && args+=(--secret "id=ca,src=$BUILD_CA_CERT")
    [ -n "${DOCKER_BUILD_NETWORK:-}" ] && args+=(--network "$DOCKER_BUILD_NETWORK")
    [ -n "${PLATFORM:-}" ] && args+=(--platform "$PLATFORM")
    log "building $IMAGE"
    docker build "${args[@]}" "$REPO"
fi

for v in "${VOLS[@]}"; do docker volume create "$v" >/dev/null; done
# The harness's file-auth tests need tests/passwd as data/passwd.
PLATFORM_ARGS=(); [ -n "${PLATFORM:-}" ] && PLATFORM_ARGS=(--platform "$PLATFORM")
docker run --rm "${PLATFORM_ARGS[@]}" -v "$NAME-data:/bumper/data" -v "$REPO/tests/passwd:/tmp/passwd:ro" \
    --entrypoint cp "$IMAGE" /tmp/passwd /bumper/data/passwd

# TZ=BHT-3 (POSIX for UTC+3) and BUMPER_ANNOUNCE_IP=127.0.0.1 are what the
# harness goldens expect (see tests/harness/README.md).
CID=$(docker run -d "${PLATFORM_ARGS[@]}" --name "$NAME" \
    -e TZ=BHT-3 -e BUMPER_ANNOUNCE_IP=127.0.0.1 \
    -v "$NAME-data:/bumper/data" -v "$NAME-certs:/bumper/certs" -v "$NAME-logs:/bumper/logs" \
    -p 127.0.0.1::443 -p 127.0.0.1::8007 -p 127.0.0.1::8883 -p 127.0.0.1::5223 \
    "$IMAGE")

wait_healthy() {
    for _ in $(seq 1 60); do
        state=$(docker inspect -f '{{.State.Health.Status}}' "$CID")
        [ "$state" = healthy ] && return 0
        [ "$(docker inspect -f '{{.State.Running}}' "$CID")" = true ] || { log "container exited"; return 1; }
        sleep 2
    done
    log "not healthy after 120s (state: $state)"
    return 1
}
log "waiting for healthy"
wait_healthy

uid=$(docker exec "$CID" id -u)
[ "$uid" != 0 ] || { log "FAIL: container runs as root"; exit 1; }
unpriv=$(docker exec "$CID" cat /proc/sys/net/ipv4/ip_unprivileged_port_start)
log "running as uid $uid; ip_unprivileged_port_start=$unpriv (443 bound without root)"
[ "$unpriv" -le 443 ] || { log "FAIL: this Docker cannot bind 443 as non-root"; exit 1; }

port() { docker port "$CID" "$1/tcp" | head -1 | sed 's/.*://'; }
docker cp "$CID:/bumper/certs/ca.crt" "$WORK/ca.crt"
ca_sum=$(docker exec "$CID" sha256sum /bumper/certs/ca.crt /bumper/certs/bumper.crt)

run_harness() {
    (cd "$REPO" && BUMPER_HARNESS_TARGET=host BUMPER_HARNESS_CA="$WORK/ca.crt" \
        BUMPER_PORT_HTTPS=$(port 443) BUMPER_PORT_HTTP=$(port 8007) \
        BUMPER_PORT_MQTT=$(port 8883) BUMPER_PORT_XMPP=$(port 5223) \
        ${PYTHON:-uv run python} -m pytest tests/harness -p no:warnings "$@")
}
log "running the harness against the container"
run_harness -q

devices() {
    curl_py='import json,sys,urllib.request
r = urllib.request.Request("http://127.0.0.1:%s/api/users/user.do" % sys.argv[1], data=b"{\"todo\": \"GetDeviceList\"}", headers={"Content-Type": "application/json"})
print(" ".join(sorted(str(d.get("did")) for d in json.load(urllib.request.urlopen(r, timeout=10))["devices"])))'
    ${PYTHON:-uv run python} -c "$curl_py" "$(port 8007)"
}
before=$(cd "$REPO" && devices)
log "bots in the database: $before"

log "restarting the container"
docker restart "$CID" >/dev/null
wait_healthy
after_sum=$(docker exec "$CID" sha256sum /bumper/certs/ca.crt /bumper/certs/bumper.crt)
[ "$ca_sum" = "$after_sum" ] || { log "FAIL: certificates changed across restart"; exit 1; }
docker logs "$CID" 2>&1 | grep -c "A NEW certificate authority" | grep -qx 1 \
    || { log "FAIL: certificates were generated more than once"; exit 1; }
after=$(cd "$REPO" && devices)
[ -n "$before" ] && [ "$before" = "$after" ] || { log "FAIL: database changed across restart: '$before' -> '$after'"; exit 1; }
log "certificates and database survived the restart"
log "PASS"
