# Docker

## Image

Images for `linux/amd64` and `linux/arm64` are published to the GitHub
Container Registry:

```
docker pull ghcr.io/tunlezah/bumper:latest
```

Tags: `latest` (default branch), `vX.Y.Z` for releases, and `sha-<commit>`.

To build it yourself (Docker 20.10+ with BuildKit):

```
docker build -t bumper .
docker buildx build --platform linux/amd64,linux/arm64 -t bumper .
```

The image is based on `python:3.14-slim`, installs the locked dependencies
from `uv.lock`, and builds `create_certs` from source for the target
architecture. It runs as the unprivileged user `bumper` (uid/gid 10001).

## Running

**Ports (-p):** `443`, `8007`, `8883` and `5223`, e.g.
`-p 443:443 -p 8007:8007 -p 8883:8883 -p 5223:5223`.

**Environment (-e):**

- `BUMPER_ANNOUNCE_IP` (required in practice): the IP address of the Docker
  host. Bots are told to connect to it when they check in.
- `TZ`, e.g. `Europe/Rome`.
- `BUMPER_TLS_MIN_VERSION`: lowest accepted TLS version (default `TLSv1`; see
  "TLS" below).
- Everything else is in [Env_Var.md](Env_Var.md). The image already sets
  `BUMPER_LISTEN=0.0.0.0` and `LOG_TO_STDOUT=true`.

**Volumes (-v):** `/bumper/data` (database, `passwd`), `/bumper/certs`
(certificates) and `/bumper/logs` (only used without `LOG_TO_STDOUT`).

```
docker run -d --name bumper \
  -e BUMPER_ANNOUNCE_IP=X.X.X.X \
  -p 443:443 -p 8007:8007 -p 8883:8883 -p 5223:5223 \
  -v bumper-data:/bumper/data -v bumper-certs:/bumper/certs \
  ghcr.io/tunlezah/bumper:latest
```

The container reports `healthy` once the HTTP config server on port 8007
answers.

## Certificates

On first start, if `/bumper/certs` holds no certificates, the entrypoint
generates a new CA and server certificate there and prints a banner.
**Persist `/bumper/certs`**: your robots and apps trust that CA, and if the
volume is lost a new CA is generated and every device has to be set up
again. Copy the CA for your devices with
`docker cp bumper:/bumper/certs/ca.crt .`. The generated certificates are
valid for 2 years.

To bring your own certificates, put `ca.crt`, `bumper.crt` and `bumper.key`
in the certs volume (or point `BUMPER_CA`/`BUMPER_CERT`/`BUMPER_KEY` at them).
The entrypoint never overwrites existing files. If only some of them exist,
it stops with an error.

## Non-root and port 443

Docker 20.10 and newer set `net.ipv4.ip_unprivileged_port_start=0` inside a
container's own network namespace, so the unprivileged `bumper` user can bind
443 with the default (bridge) networking and with port publishing.

**With `network_mode: host` this does not apply.** The host's value (usually
1024) is used, and port 443 cannot be bound without root. The entrypoint
detects this and stops with an explanation instead of starting without 443.
Options:

1. Move the HTTPS server to an unprivileged port and forward 443 to it, e.g.
   `BUMPER_PORT_HTTPS=8443` plus a port forward or reverse proxy from 443 to
   8443. Bots always connect to 443, and to 5223 for XMPP (see
   [Env_Var.md](Env_Var.md) for all `BUMPER_PORT_*` variables).
2. Grant the interpreter `CAP_NET_BIND_SERVICE` as a file capability in a
   derived image, keep `NET_BIND_SERVICE` in the container's capabilities
   (it is in Docker's default set; `cap_add: [NET_BIND_SERVICE]` if you drop
   capabilities), and disable the entrypoint check:

   ```dockerfile
   FROM ghcr.io/tunlezah/bumper:latest
   USER root
   # same as: setcap cap_net_bind_service=+ep /usr/local/bin/python3.14
   RUN python -c "import os, struct; os.setxattr(os.path.realpath('/usr/local/bin/python3'), 'security.capability', struct.pack('<IIIII', 0x02000001, 1 << 10, 0, 0, 0))"
   USER bumper
   ENV BUMPER_SKIP_PORT_CHECK=1
   ```
3. Run the container as root (`user: "0:0"`), as the old image did.
4. Lower the host's `net.ipv4.ip_unprivileged_port_start` to 443.

## Volume ownership

Named volumes take their ownership from the image, so nothing needs to be
done. For bind mounts, the directories must be writable by uid 10001
(`sudo chown 10001:10001 config certs`). Alternatively run the container as
the directories' owner (`--user 1000:1000` / `user: "1000:1000"`).

**Upgrading from the old `bmartin5692/bumper` image**, which ran as root: keep
your existing `certs` (and data) directories so the CA is kept, and `chown`
them to 10001 as above. Without that the new container cannot read
`bumper.key`.

## TLS

By default Bumper accepts TLS 1.0 and newer on 443, 8883 and XMPP STARTTLS
(5223), like the old image did, because older robots may not support anything
newer. Every TLS connection is logged with the version and cipher it
negotiated, e.g.:

```
TLS MQTT connection from 192.168.1.23:40112: TLSv1 ECDHE-RSA-AES256-SHA
```

If all your robots and apps use TLS 1.2 or newer, set
`BUMPER_TLS_MIN_VERSION=TLSv1_2`. Behind the nginx proxy below, the peer
address in these lines is the proxy's.

## Docker Compose

A Docker Compose example is in the
[example folder](https://github.com/tunlezah/bumper/tree/master/example/docker-compose).
It starts two services:

- Bumper itself
- an nginx stream proxy that routes port 443 by SNI: MQTT host names, and
  connections without SNI, go to Bumper's MQTT port 8883; everything else
  goes to Bumper's HTTPS port 443

App v2+ and robots with newer firmware connect to the MQTT server on port
443, which is why the proxy is needed.

## Testing the image

`scripts/docker-smoke.sh` builds the image, runs it with fresh volumes, waits
until it is healthy, runs the characterisation harness against it, restarts
it, and checks that the certificates and the database survived. CI runs it
for every change.
