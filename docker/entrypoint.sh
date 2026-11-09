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

if [ -z "${BUMPER_ANNOUNCE_IP:-}" ]; then
    log "WARNING: BUMPER_ANNOUNCE_IP is not set; bots will be told to connect to ${BUMPER_LISTEN:-<listen address>}."
    log "WARNING: set it to the IP address of the Docker host that robots can reach."
fi

exec python -m bumper "$@"
