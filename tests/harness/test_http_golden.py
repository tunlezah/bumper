"""HTTP behaviour of the config servers (443 TLS and 8007 plain), golden-tested.

Scenarios live in http_cases.json and run in file order. Steps within a
scenario are stateful (login -> token -> auth code -> ...). The whole module
needs a pristine instance, because device lists show every bot in the DB.
"""

import json

import pytest

from harnesslib import cases, golden, httpclient

SCENARIOS = cases.load_scenarios()


@pytest.fixture(scope="module")
def pristine(target):
    outcome = httpclient.request(
        target,
        "http",
        "POST",
        "/api/users/user.do",
        body=json.dumps({"todo": "GetDeviceList"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    devices = outcome.json().get("devices") if outcome.status == 200 else None
    if devices:
        pytest.fail(
            "test_http_golden.py needs a pristine Bumper instance (no bots in the DB), found {} bot(s). "
            "Run it first, or against a fresh data volume.".format(len(devices))
        )
    return target


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["id"] for s in SCENARIOS])
def test_http_scenario(pristine, scenario):
    runner = cases.ScenarioRunner(pristine)
    try:
        results = [runner.run_step(step) for step in scenario["steps"]]
    finally:
        runner.close()
    golden.check("http/" + scenario["id"], {"description": scenario["description"], "steps": results})
