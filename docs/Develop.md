# Developing
To start developing and contributing, install the locked dependencies including the dev tools (Python 3.12+, [uv](https://docs.astral.sh/uv/)):

`uv sync`

Review the [How It Works](How_It_Works.md) doc to understand the basics and then dive into the code.

As features and functions are added, be sure to add tests to keep the test coverage high.

| Path | Contents |
| ---- | -------- |
| `bumper/` | The server: `confserver.py` (HTTP/HTTPS), `mqttserver.py`, `xmppserver.py`, `tls.py`, `db.py`, `models.py` |
| `bumper/plugins/` | The REST API, one file per API area |
| `create_certs/` | The certificate tool (Go source in `src/`, prebuilt binaries) |
| `tests/` | Unit tests |
| `tests/harness/` | Characterisation harness and its golden files |
| `Dockerfile`, `docker/`, `scripts/docker-smoke.sh` | The container image and its smoke test |
| `docs/`, `mkdocs.yml`, `.readthedocs.yaml` | This documentation |

# Testing
Bumper uses pytest. There are two suites:

- `tests/`: unit tests (pytest-asyncio, pytest-aiohttp)
- `tests/harness/`: the black-box characterisation harness, which starts Bumper as a subprocess and pins its observable HTTP/MQTT/XMPP/TLS behaviour against golden files recorded from the legacy code. See the [harness README](https://github.com/tunlezah/bumper/blob/master/tests/harness/README.md) and [Modernisation](modernisation/CHANGES.md).

### Running tests

- Unit tests: `uv run pytest`
- Unit tests with every deprecation as an error (as CI runs them): `uv run pytest -W error::DeprecationWarning -W error::PendingDeprecationWarning`
- Harness: `uv run pytest tests/harness`
- Docker image smoke test (builds the image, runs the harness against it): `scripts/docker-smoke.sh`

Deprecation warnings raised from Bumper's own modules always fail the unit tests (`filterwarnings` in `pyproject.toml`).

### Continuous integration

GitHub Actions (`.github/workflows/ci.yml`) runs both suites on Python 3.12 to 3.15, runs the harness against the pre-port code on Python 3.9, builds the Docker image for `linux/amd64` and `linux/arm64`, and runs the smoke test. On the default branch and on `v*` tags the image is pushed to `ghcr.io/tunlezah/bumper`.

# Documentation

The documentation is the Markdown in `docs/`, built into a site with [MkDocs](https://www.mkdocs.org/) (`mkdocs.yml`, "readthedocs" theme).

- Preview while editing: `uvx --with-requirements docs/requirements.txt mkdocs serve`
- Build into `site/`, failing on broken links: `uvx --with-requirements docs/requirements.txt mkdocs build --strict`

`.readthedocs.yaml` is the build configuration for [Read the Docs](https://about.readthedocs.com/). To host the docs of this repository there, import the repository as a new project on Read the Docs; no further settings are needed.
