"""Session fixture for the characterisation harness.

One Bumper instance is shared by the whole session, in both target modes, so
a local run has the same topology as a run against a container. Every module
is written to be independent of what other modules did to that instance
(they use their own device ids and select only their own rows), except
test_http_golden.py, which needs a pristine instance and checks for one.
"""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from harnesslib import config as hconfig, target as target_mod  # noqa: E402

_LOCAL = {}


@pytest.fixture(scope="session")
def target():
    if hconfig.TARGET == "host":
        yield target_mod.host_target()
        return
    bumper = target_mod.LocalBumper()
    _LOCAL["instance"] = bumper
    try:
        yield bumper.start()
    finally:
        bumper.stop()


def pytest_report_header(config):  # noqa: ARG001
    return "bumper harness: target={} profile={} record={} src={}".format(
        hconfig.TARGET, hconfig.PROFILE, hconfig.RECORD or "no", hconfig.SRC_DIR
    )


def pytest_terminal_summary(terminalreporter, exitstatus, config):  # noqa: ARG001
    """On failure, show what the Bumper subprocess logged."""
    instance = _LOCAL.get("instance")
    if instance is None:
        return
    failed = terminalreporter.stats.get("failed") or terminalreporter.stats.get("error")
    if failed or os.environ.get("BUMPER_HARNESS_SHOW_LOG"):
        log = instance.read_log()
        lines = log.splitlines()
        terminalreporter.section("bumper subprocess output (last 300 lines)")
        terminalreporter.write_line("\n".join(lines[-300:]))
    instance.cleanup()
