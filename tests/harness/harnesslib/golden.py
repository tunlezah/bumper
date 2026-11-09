"""Golden file storage and comparison.

Layout
------
``golden/<name>.json``
    Behaviour recorded from the **legacy** code base (Python 3.9 + the
    original pins, unmodified source). These files are only ever written with
    ``BUMPER_HARNESS_RECORD=1 BUMPER_HARNESS_PROFILE=legacy``.

``golden_changes/<name>.json``
    A deliberate, documented behaviour change. Hand-written, with::

        {"change": "C-00N", "reason": "...", "expected": <what the port does>}

    ``change`` refers to an entry in docs/modernisation/CHANGES.md. With the
    default ``modern`` profile the ``expected`` block replaces the legacy
    golden; with ``BUMPER_HARNESS_PROFILE=legacy`` it is ignored, so the legacy
    goldens stay provably tied to the legacy code.

All files are pretty-printed, key-sorted JSON.
"""

import difflib
import json
import os

import pytest

from . import config


def _dump(obj):
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write(path, obj):
    d = os.path.dirname(path)
    if not os.path.isdir(d):
        os.makedirs(d)
    with open(path, "w", encoding="utf-8") as f:
        f.write(_dump(obj))


def golden_path(name):
    return os.path.join(config.GOLDEN_DIR, name + ".json")


def change_path(name):
    return os.path.join(config.CHANGES_DIR, name + ".json")


def expected_for(name):
    """Return (expected, source description) for a golden name."""
    path = golden_path(name)
    if not os.path.exists(path):
        pytest.fail(
            "No golden file {}. Goldens are recorded from the legacy code base: "
            "BUMPER_HARNESS_PROFILE=legacy BUMPER_HARNESS_RECORD=1".format(os.path.relpath(path, config.REPO_DIR))
        )
    expected = _load(path)
    source = "legacy golden " + os.path.relpath(path, config.REPO_DIR)
    cpath = change_path(name)
    if config.PROFILE == "modern" and os.path.exists(cpath):
        change = _load(cpath)
        expected = change["expected"]
        source = "deliberate change {} ({})".format(change["change"], os.path.relpath(cpath, config.REPO_DIR))
    return expected, source


def check(name, actual):
    # JSON round trip so tuples/lists etc. compare the same way they are stored
    actual = json.loads(json.dumps(actual))

    if config.RECORD == "1":
        if config.PROFILE != "legacy":
            pytest.fail(
                "Refusing to record goldens from the modern code base. Goldens must come from the legacy "
                "code (BUMPER_HARNESS_PROFILE=legacy). Record a deliberate change in golden_changes/ instead."
            )
        _write(golden_path(name), actual)
        return

    if config.RECORD == "changes":
        cpath = change_path(name)
        if config.PROFILE == "modern" and os.path.exists(cpath):
            change = _load(cpath)
            change["expected"] = actual
            _write(cpath, change)
            return

    expected, source = expected_for(name)
    if actual != expected:
        diff = "".join(
            difflib.unified_diff(
                _dump(expected).splitlines(True),
                _dump(actual).splitlines(True),
                fromfile="expected: " + source,
                tofile="actual",
            )
        )
        pytest.fail("Behaviour differs from golden '{}':\n{}".format(name, diff), pytrace=False)


def check_cell(name, key, actual):
    """Compare one cell (``key``) of a golden mapping, e.g. one endpoint/version
    of the TLS matrix. Recording merges the cell into the existing file."""
    actual = json.loads(json.dumps(actual))
    if config.RECORD == "1":
        if config.PROFILE != "legacy":
            pytest.fail("Refusing to record goldens from the modern code base (see check()).")
        path = golden_path(name)
        data = _load(path) if os.path.exists(path) else {}
        data[key] = actual
        _write(path, data)
        return
    if config.RECORD == "changes":
        cpath = change_path(name)
        if config.PROFILE == "modern" and os.path.exists(cpath):
            change = _load(cpath)
            change["expected"][key] = actual
            _write(cpath, change)
            return
    expected, source = expected_for(name)
    if key not in expected:
        pytest.fail("Golden '{}' has no entry for {!r} ({})".format(name, key, source))
    if actual != expected[key]:
        pytest.fail(
            "Behaviour differs from golden '{}' [{}]: expected {!r} ({}), got {!r}".format(
                name, key, expected[key], source, actual
            ),
            pytrace=False,
        )
