[![CI](https://github.com/tunlezah/bumper/actions/workflows/ci.yml/badge.svg)](https://github.com/tunlezah/bumper/actions/workflows/ci.yml)
[![License GPLv3](https://img.shields.io/github/license/tunlezah/bumper.svg?color=brightgreen)](LICENSE.txt)

# Bumper

Bumper is a standalone and self-hosted implementation of the central server used by Ecovacs vacuum robots.  Bumper allows you to have full control of your Ecovacs robots, without the robots or app talking to the Ecovacs servers and transmitting data outside of your home.

![Bumper Diagram](./docs/images/BumperDiagram.png "Bumper Diagram")

***Please note**: this software is experimental and not ready for production use. Use at your own risk.*

## About this fork

This repository is a fork of [bmartin5692/bumper](https://github.com/bmartin5692/bumper), whose last change dates from June 2021 and which no longer runs on current Python. The fork ports that code to current software without changing what robots and apps see on the network:

- Python 3.12 to 3.15 (the original ran on 3.7 to 3.9)
- maintained dependencies: amqtt (replacing hbmqtt), aiohttp 3.14, TinyDB 4 and libpass (replacing passlib)
- a non-root Docker image for `linux/amd64` and `linux/arm64`, published to the GitHub Container Registry
- GitHub Actions CI, with a test harness that compares the HTTP, MQTT, XMPP and TLS behaviour against recordings of the original code

Every deliberate difference from the original is listed in [docs/modernisation/CHANGES.md](docs/modernisation/CHANGES.md).

**Testing needed:** the port has not yet been tried with a real robot or with the current Ecovacs apps. If you run it with your robot, please [open an issue](https://github.com/tunlezah/bumper/issues) with the model and the result, working or not.

| | |
| --- | --- |
| CI (tests on Python 3.12–3.15, legacy harness, Docker) | [![CI](https://github.com/tunlezah/bumper/actions/workflows/ci.yml/badge.svg)](https://github.com/tunlezah/bumper/actions/workflows/ci.yml) |
| Container image (amd64, arm64) | [ghcr.io/tunlezah/bumper](https://github.com/tunlezah/bumper/pkgs/container/bumper) |

## Why?

For fun, mostly :)

But seriously, there are a several reasons for eliminating the central server:

1. Convenience: It works without an internet connection or if Ecovacs servers are down
2. Performance: No need for messages to travel to Ecovacs server and back.
3. Security: We can completely isolate the robot from the public Internet.

## Quick start

With Docker (certificates are generated on first start):

```
docker run -d --name bumper \
  -e BUMPER_ANNOUNCE_IP=X.X.X.X \
  -p 443:443 -p 8007:8007 -p 8883:8883 -p 5223:5223 \
  -v bumper-data:/bumper/data -v bumper-certs:/bumper/certs \
  ghcr.io/tunlezah/bumper:latest
```

`X.X.X.X` is the address of the Docker host on your network. Or from source, with Python 3.12+ and [uv](https://docs.astral.sh/uv/):

```
git clone https://github.com/tunlezah/bumper.git
cd bumper
uv sync --no-dev
uv run --no-dev bumper
```

Then point the Ecovacs domains at Bumper in your DNS server and trust Bumper's CA certificate on your phone. The documentation below covers each step.

## Documentation

The documentation is in the [docs](docs/index.md) folder:

| | |
| --- | --- |
| [Getting started](docs/index.md) | Requirements, installation, starting Bumper, troubleshooting |
| [Docker](docs/Docker.md) | The container image, volumes, non-root and port 443, Docker Compose |
| [Command-line](docs/CmdLine.md) and [environment variables](docs/Env_Var.md) | Configuration |
| [Certificates](docs/Create_Certs.md) | Creating the CA and server certificate |
| [DNS](docs/DNS_Setup.md) | Pointing the Ecovacs domains at Bumper |
| [Using the Ecovacs apps](docs/Use_With_App.md) | Importing the CA certificate on iOS and Android |
| [Using Sucks](docs/Use_With_Sucks.md) | Controlling a robot from the command line or a script |
| [How it works](docs/How_It_Works.md) | The services Bumper provides and the protocols involved |
| [Developing and testing](docs/Develop.md) | Development setup, tests, building these docs |
| [Modernisation](docs/modernisation/CHANGES.md) | What changed in this fork, known issues and follow-ups |

The docs are an [MkDocs](https://www.mkdocs.org/) site (`mkdocs.yml`) that can be built locally or on Read the Docs; see [Developing and testing](docs/Develop.md#documentation). The site at [bumper.readthedocs.io](https://bumper.readthedocs.io) belongs to the original project and describes its 2021 code, not this fork.

## Compatibility

As work to reverse the protocols and provide a self-hosted central server is still in progress, Bumper has had limited testing.  There are a number of EcoVacs models that it hasn't been tested against.  Bumper should be compatible with most wifi-enabled robots that use either the Ecovacs Android/iOS app or the Ecovacs Home Android/iOS app, but has only been reported to work on the below.

These reports were made against the original project between 2019 and 2021, with the firmware and app versions of that time:

| Model           | Protocol Used | Bumper Version Tested | EcoVacs App Tested   |
| --------------- | ------------- | --------------------- | -------------------- |
| Deebot 900/901  | MQTT          | original master       | Ecovacs/Ecovacs Home |
| Deebot 600      | MQTT          | original master       | Ecovacs Home         |
| Deebot Ozmo 950 | MQTT          | original master       | Ecovacs Home         |
| Deebot Ozmo 601 | XMPP          | original master       | Ecovacs              |
| Deebot Ozmo 930 | XMPP          | original master       | Ecovacs              |
| Deebot M81 Pro  | XMPP          | v0.1.0                | Ecovacs              |

## Getting help

- Problems with this fork: [issues](https://github.com/tunlezah/bumper/issues).
- The original project's chat room (Gitter, now on Matrix): [ecovacs-bumper/community](https://app.gitter.im/#/room/#ecovacs-bumper_community:gitter.im).

---
### Thanks
A big thanks to the original project creator @torbjornaxelsson, without whose work this project would have taken much longer to build, and to @bmartin5692, who developed Bumper from 2019 to 2021.

Bumper wouldn't exist without [Sucks](https://github.com/wpietri/sucks), an open source client for Ecovacs robots. Thanks to @wpietri and contributors!
