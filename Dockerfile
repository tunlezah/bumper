# syntax=docker/dockerfile:1
#
# Bumper image: Python 3.14 (Debian slim), locked dependencies (uv.lock),
# create_certs built from source for the target architecture, runs as a
# non-root user.
#
#   docker build -t bumper .
#   docker buildx build --platform linux/amd64,linux/arm64 -t ghcr.io/<owner>/bumper .
#
# Base images are build arguments so mirrors can be used. The optional build
# secret "ca" adds a CA bundle for TLS-intercepting proxies while downloading
# dependencies; it is not copied into the image.

ARG PYTHON_IMAGE=python:3.14-slim
ARG GO_IMAGE=golang:1.27-trixie
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.7

# --- create_certs, cross-compiled for the target architecture --------------
FROM --platform=$BUILDPLATFORM ${GO_IMAGE} AS certs-tool
ARG TARGETOS TARGETARCH TARGETVARIANT
WORKDIR /src
COPY create_certs/src/create_certs.go .
RUN GOARM="${TARGETVARIANT#v}" CGO_ENABLED=0 GOOS="$TARGETOS" GOARCH="$TARGETARCH" \
    go build -trimpath -ldflags="-s -w" -o /out/create_certs create_certs.go

# --- locked Python dependencies in /opt/venv ------------------------------
FROM ${UV_IMAGE} AS uv

FROM ${PYTHON_IMAGE} AS deps
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=secret,id=ca,required=false \
    if [ -f /run/secrets/ca ]; then export SSL_CERT_FILE=/run/secrets/ca; fi; \
    uv sync --frozen --no-dev --no-install-project

# --- runtime ---------------------------------------------------------------
FROM ${PYTHON_IMAGE}
ARG BUMPER_UID=10001
RUN groupadd --system --gid "$BUMPER_UID" bumper \
    && useradd --system --uid "$BUMPER_UID" --gid bumper --home-dir /bumper --shell /usr/sbin/nologin bumper

COPY --from=deps /opt/venv /opt/venv
COPY --from=certs-tool /out/create_certs /bumper/create_certs/create_certs
COPY create_certs/Bumper_SAN.txt /bumper/create_certs/Bumper_SAN.txt
COPY bumper/ /bumper/bumper/
COPY LICENSE.txt /bumper/LICENSE.txt
COPY --chmod=0755 docker/entrypoint.sh /usr/local/bin/bumper-entrypoint
RUN mkdir -p /bumper/data /bumper/certs /bumper/logs \
    && chown bumper:bumper /bumper/data /bumper/certs /bumper/logs

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LOG_TO_STDOUT=true \
    BUMPER_LISTEN=0.0.0.0 \
    BUMPER_DATA=/bumper/data \
    BUMPER_CERTS=/bumper/certs \
    BUMPER_LOGS=/bumper/logs

WORKDIR /bumper
USER bumper

# HTTPS config server, plain HTTP config server, MQTT (TLS), XMPP.
# Binding 443 as non-root works on Docker >= 20.10 (ip_unprivileged_port_start=0
# in the container's network namespace); see docs/Docker.md for host networking.
EXPOSE 443 8007 8883 5223
VOLUME ["/bumper/data", "/bumper/certs", "/bumper/logs"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8007/', timeout=4)"]

ENTRYPOINT ["bumper-entrypoint"]
