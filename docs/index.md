# Bumper

Bumper is a standalone and self-hosted implementation of the central server used by Ecovacs vacuum robots. It lets you control your robots without the robots or the app talking to the Ecovacs servers.

This documentation describes [tunlezah/bumper](https://github.com/tunlezah/bumper), a fork of the original project that runs on current Python (3.12 or newer) and current Docker. What changed in the fork is listed under [Modernisation](modernisation/CHANGES.md). The fork has not yet been tried with a real robot or the current Ecovacs apps; reports are welcome in the [issue tracker](https://github.com/tunlezah/bumper/issues).

# Requirements

- An Ecovacs wifi-enabled robot
- A computer on your local network to run the Bumper server
- Docker, OR Python 3.12 or newer with [uv](https://docs.astral.sh/uv/)
- A network router or DNS server that can override DNS queries
- A client that can connect to Bumper and talk to the robot over the Ecovacs protocol.
  - The "Ecovacs" or "Ecovacs Home" Android or iOS apps can be used if configured properly.
    - See the docs on [Using Bumper with the official Android/iOS App](Use_With_App.md).
  - [Sucks](https://github.com/wpietri/sucks) can also be used, which can act as a client and control the robots via command-line.
    - See the doc on [Using Bumper with Sucks](Use_With_Sucks.md)

# Quick Start Usage

 - Configure your Ecovacs vacuum using the official mobile app (if you haven't done this already)
 - Configure your DNS server as described in the [DNS Setup](DNS_Setup.md) doc.

## Choose Installation Type

 - Docker - [See Docker Details](Docker.md)
 - Manual/Python
    - Download Bumper and install the locked dependencies:

            git clone https://github.com/tunlezah/bumper.git
            cd bumper
            uv sync --no-dev

    - Start Bumper - see the [Starting Bumper](#starting-bumper) section.

 - Control your robots like normal
    - [Using Bumper with the official Android/iOS App](Use_With_App.md)
    - [Using Bumper with Sucks](Use_With_Sucks.md)

# Starting Bumper

Bumper requires certificates to function. If `certs/` holds none on the first start, Bumper runs the bundled `create_certs` tool to generate them and then starts. The bundled binaries only cover some platforms; see the [Creating Certs](Create_Certs.md) doc for the others and for creating certificates yourself.

- Start Bumper from the repository directory with `uv run --no-dev bumper` (or `uv run --no-dev python -m bumper`)
    - Bumper listens on the address your host name resolves to. On many Linux systems that is a loopback address, so name the address explicitly: `uv run --no-dev bumper --listen 192.168.1.10` (see [Command-Line](CmdLine.md)).
    - On Linux, ports below 1024 need extra rights, and Bumper serves HTTPS on port 443. See [Troubleshooting](#troubleshooting).

- Reboot your robot
    - **Note:** Some models may require removing and re-inserting the battery pack.
    - This doesn't seem to be required for models that don't have easily accessible batteries such as the 900/901.
- If your configuration is correct, the robot will connect to Bumper within about 30 seconds. Bumper will output information about the connection status.

Bumper serves a status page over plain HTTP on port 8007 (`http://{bumper server ip}:8007/`) that lists the robots and clients it has seen.

# Troubleshooting

Logs are written to the `logs` directory (or `BUMPER_LOGS`). With `LOG_TO_STDOUT` set, which the Docker image does, they go to the console instead (`docker logs bumper`).

If there is an issue, enable debug logging with the `--debug` switch for additional detail.

**The robot or app cannot reach port 443.** On Linux only root may bind ports below 1024 by default, and Bumper does not report a port it could not bind. Either use the Docker image, or allow unprivileged processes to bind 443 (`sudo sysctl -w net.ipv4.ip_unprivileged_port_start=443`), or start Bumper as root (`sudo .venv/bin/python -m bumper`), or move the HTTPS server to another port with `BUMPER_PORT_HTTPS` and forward 443 to it (see [Environment Variables](Env_Var.md)).

**Which TLS version does my robot use?** Bumper logs one line per TLS connection with the negotiated version and cipher. See the TLS section of the [Docker](Docker.md#tls) doc.
