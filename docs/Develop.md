# Developing
To start developing and contributing, install the locked dependencies including the dev tools (Python 3.12+, [uv](https://docs.astral.sh/uv/)):

`uv sync`

Review the [How It Works](How_It_Works.md) doc to understand the basics and then dive into the code.

As features and functions are added, be sure to add tests to keep the test coverage high.

# Testing
Bumper uses pytest. There are two suites:

- `tests/`: unit tests (pytest-asyncio, pytest-aiohttp)
- `tests/harness/`: the black-box characterisation harness, which starts Bumper as a subprocess and pins its observable HTTP/MQTT/XMPP/TLS behaviour against golden files recorded from the legacy code. See [tests/harness/README.md](../tests/harness/README.md) and [modernisation/](modernisation/CHANGES.md).

### Running tests

- Unit tests: `uv run pytest`
- Unit tests with every deprecation as an error (as CI runs them): `uv run pytest -W error::DeprecationWarning -W error::PendingDeprecationWarning`
- Harness: `uv run pytest tests/harness`
- Docker image smoke test (builds the image, runs the harness against it): `scripts/docker-smoke.sh`

Deprecation warnings raised from Bumper's own modules always fail the unit tests (`filterwarnings` in `pyproject.toml`).
