"""Static check of golden_changes/ (needs no running Bumper).

Every override must (1) name change ids that are documented in
docs/modernisation/CHANGES.md, (2) actually differ from the legacy golden, and
(3) differ from it *only* in ways those changes explain (see
harnesslib/changes.py). This keeps "goldens unchanged except for justified
entries" mechanically true.
"""

import glob
import json
import os

import pytest

from harnesslib import changes, config

CHANGES_MD = os.path.join(config.REPO_DIR, "docs", "modernisation", "CHANGES.md")


def _change_files():
    pattern = os.path.join(config.CHANGES_DIR, "**", "*.json")
    return sorted(os.path.relpath(p, config.CHANGES_DIR)[: -len(".json")] for p in glob.glob(pattern, recursive=True))


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("name", _change_files())
def test_override_is_explained_by_its_changes(name):
    override = _load(os.path.join(config.CHANGES_DIR, name + ".json"))
    ids = override["changes"]
    assert ids and override.get("reason"), "an override needs change ids and a reason"

    with open(CHANGES_MD, encoding="utf-8") as f:
        documented = f.read()
    for change_id in ids:
        assert change_id in changes.PREDICATES, "{} has no predicate in harnesslib/changes.py".format(change_id)
        assert "### {}".format(change_id) in documented, "{} is not documented in CHANGES.md".format(change_id)

    legacy = _load(os.path.join(config.GOLDEN_DIR, name + ".json"))
    diffs = changes.minimal_diffs(legacy, override["expected"])
    assert diffs, "override is identical to the legacy golden; delete it"

    unexplained = [
        (path, old, new)
        for path, old, new in diffs
        if not any(changes.PREDICATES[i](name, path, old, new) for i in ids)
    ]
    assert not unexplained, "differences not explained by {}:\n{}".format(
        ", ".join(ids),
        "\n".join("  at {}: {!r} -> {!r}".format("/".join(map(str, p)), o, n) for p, o, n in unexplained[:10]),
    )
