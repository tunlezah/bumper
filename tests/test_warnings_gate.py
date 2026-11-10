"""The warnings gate in pyproject.toml really applies to Bumper's modules."""

import warnings

import pytest


def warn_from(module_name, category):
    code = "import warnings\ndef f():\n    warnings.warn('deprecated thing', {}, stacklevel=1)\n".format(category.__name__)
    namespace = {"__name__": module_name}
    exec(compile(code, module_name.replace(".", "/") + ".py", "exec"), namespace)
    namespace["f"]()


@pytest.mark.parametrize("module_name", ["bumper.confserver", "bumper_confserver_portal_lg"])
@pytest.mark.parametrize("category", [DeprecationWarning, PendingDeprecationWarning])
def test_deprecations_from_bumper_code_are_errors(module_name, category):
    with pytest.raises(category):
        warn_from(module_name, category)


def test_other_modules_are_not_affected():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("default")
        warn_from("somelibrary.module", DeprecationWarning)
    assert caught and caught[0].category is DeprecationWarning
