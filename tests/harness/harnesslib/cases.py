"""Loading and executing the scenarios in http_cases.json."""

import hashlib
import json
import os
import re
import time

from . import config, httpclient, mqttclient

CASES_FILE = os.path.join(config.HARNESS_DIR, "http_cases.json")
VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def load_scenarios():
    with open(CASES_FILE, encoding="utf-8") as f:
        return json.load(f)["scenarios"]


def http_steps():
    """Every HTTP step as (scenario id, step) - used by the route-coverage test."""
    for scenario in load_scenarios():
        for step in scenario["steps"]:
            if "method" in step:
                yield scenario["id"], step


def substitute(value, variables):
    if isinstance(value, str):

        def repl(m):
            name = m.group(1)
            if name not in variables:
                raise KeyError("case uses ${{{}}} before it was captured".format(name))
            return str(variables[name])

        return VAR.sub(repl, value)
    if isinstance(value, list):
        return [substitute(v, variables) for v in value]
    if isinstance(value, dict):
        return {k: substitute(v, variables) for k, v in value.items()}
    return value


def get_path(obj, dotted):
    for key in dotted.split("."):
        obj = obj[key]
    return obj


def canonical_digest(obj):
    canonical = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return {"sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(), "length": len(canonical)}


class ScenarioRunner(object):
    def __init__(self, target):
        self.target = target
        self.variables = {}
        self.mqtt = {}

    def close(self):
        for conn in self.mqtt.values():
            conn.disconnect()
        self.mqtt.clear()

    def run_step(self, step):
        if "mqtt_connect" in step:
            spec = step["mqtt_connect"]
            conn = mqttclient.MqttConn(self.target, spec["client_id"], spec.get("username"), spec.get("password"))
            connack = conn.connect()
            self.mqtt[spec["handle"]] = conn
            return {"step": step["name"], "mqtt_connack": connack}
        if "mqtt_disconnect" in step:
            conn = self.mqtt.pop(step["mqtt_disconnect"])
            conn.disconnect()
            time.sleep(step.get("settle", 0))
            return {"step": step["name"], "mqtt_disconnected": True}

        method = step["method"]
        path = substitute(step["path"], self.variables)
        body, headers = httpclient.encode_body(substitute(step.get("body"), self.variables))
        outcome = httpclient.request(self.target, step["port"], method, path, body=body, headers=headers)

        for name, dotted in (step.get("capture") or {}).items():
            # A capture failing means the flow itself broke; record that
            # rather than crashing so the golden diff shows the real response.
            try:
                self.variables[name] = get_path(outcome.json(), dotted)
            except Exception:  # noqa: BLE001
                # URL-safe, so the following steps still run and show diffs
                self.variables[name] = "CAPTURE-FAILED-" + dotted

        record = httpclient.describe(outcome, variables=self.variables_for_normalise(step))
        if step.get("record") == "digest" and isinstance(record.get("body"), dict) and "data" in record["body"]:
            # Large static payloads: keep the (normalised) envelope readable
            # and replace only the "data" field with a digest of its canonical
            # JSON. Any change to the data still changes the digest.
            record["body"] = dict(record["body"], data={"_digest": canonical_digest(record["body"]["data"])})
        return {
            "step": step["name"],
            "request": {"method": method, "port": step["port"], "path": step["path"], "body": step.get("body")},
            "response": record,
        }

    def variables_for_normalise(self, step):
        # Values captured by this very step must not be reported as <var:..>
        # of themselves; they get the generic placeholder on first sight.
        own = set((step.get("capture") or {}).keys())
        return {k: v for k, v in self.variables.items() if k not in own}
