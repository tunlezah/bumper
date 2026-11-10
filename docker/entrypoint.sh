#!/bin/sh
# Container entrypoint: make sure certificates exist, then run Bumper.
#
# Certificates are generated only when *none* of the CA/server files exist, so
# an existing CA (which robots and apps already trust) is never replaced. If
# only some of them exist, or BUMPER_CA/BUMPER_CERT/BUMPER_KEY point at missing
# files, the container stops with an error instead of guessing.
set -eu

CERTS_DIR="${BUMPER_CERTS:-/bumper/certs}"
CA="${BUMPER_CA:-$CERTS_DIR/ca.crt}"
CERT="${BUMPER_CERT:-$CERTS_DIR/bumper.crt}"
KEY="${BUMPER_KEY:-$CERTS_DIR/bumper.key}"

log() { echo "[entrypoint] $*" >&2; }

if [ ! -f "$CA" ] || [ ! -f "$CERT" ] || [ ! -f "$KEY" ]; then
    custom_paths="${BUMPER_CA:-}${BUMPER_CERT:-}${BUMPER_KEY:-}"
    existing=""
    for f in ca.crt ca.key bumper.crt bumper.key; do
        [ -e "$CERTS_DIR/$f" ] && existing="$existing $f"
    done
    if [ -n "$custom_paths" ] || [ -n "$existing" ]; then
        log "ERROR: certificate files are missing (CA=$CA CERT=$CERT KEY=$KEY)."
        [ -n "$existing" ] && log "ERROR: $CERTS_DIR already contains:$existing"
        log "ERROR: refusing to generate new certificates over an existing set; fix or remove them."
        exit 1
    fi

    log "No certificates found in $CERTS_DIR, generating a new CA and server certificate"
    /bumper/create_certs/create_certs -out "$CERTS_DIR" -inSAN /bumper/create_certs/Bumper_SAN.txt
    cat >&2 <<EOF
[entrypoint] ########################################################################
[entrypoint] # A NEW certificate authority was generated in $CERTS_DIR.
[entrypoint] # Robots and apps must trust $CA.
[entrypoint] # PERSIST $CERTS_DIR (mount a volume): if it is lost, a new CA is
[entrypoint] # generated on the next start and every device has to be set up again.
[entrypoint] # The certificates are valid for 2 years.
[entrypoint] ########################################################################
EOF
fi

# Without root, ports below ip_unprivileged_port_start cannot be bound. Docker
# >= 20.10 sets it to 0 inside a container's own network namespace, but with
# network_mode: host the host's value applies (usually 1024), and Bumper would
# then fail to serve 443 without logging anything.
# (BUMPER_SKIP_PORT_CHECK=1 for images that grant the interpreter
# CAP_NET_BIND_SERVICE as a file capability, see docs/Docker.md.)
if [ "$(id -u)" != 0 ] && [ "${BUMPER_SKIP_PORT_CHECK:-0}" != 1 ] && [ -r /proc/sys/net/ipv4/ip_unprivileged_port_start ]; then
    unpriv=$(cat /proc/sys/net/ipv4/ip_unprivileged_port_start)
    for var in BUMPER_PORT_HTTPS:443 BUMPER_PORT_HTTP:8007 BUMPER_PORT_MQTT:8883 BUMPER_PORT_XMPP:5223; do
        name=${var%%:*}
        eval "port=\${$name:-${var#*:}}"
        if [ "$port" -lt "$unpriv" ]; then
            log "ERROR: running as uid $(id -u), which cannot bind port $port ($name): ports below $unpriv are privileged here."
            log "ERROR: this happens with network_mode: host. Either set $name to a port >= $unpriv and"
            log "ERROR: forward $port to it, or run the container as root (user: \"0:0\"). See docs/Docker.md."
            exit 1
        fi
    done
fi

if [ -z "${BUMPER_ANNOUNCE_IP:-}" ]; then
    log "WARNING: BUMPER_ANNOUNCE_IP is not set; bots will be told to connect to ${BUMPER_LISTEN:-<listen address>}."
    log "WARNING: set it to the IP address of the Docker host that robots can reach."
fi

exec python -m bumper "$@"
