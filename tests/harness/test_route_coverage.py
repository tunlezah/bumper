"""Every HTTP route must be exercised by at least one case in http_cases.json.

This test runs in-process: it only needs the aiohttp router, not a server.
Each case's (method, path) is resolved through the real router, so a case
counts for a route only if aiohttp would actually dispatch it there. A
``web.get`` route registers GET and HEAD separately; both need a case.
"""

import asyncio
import os
import sys

from harnesslib import cases, config

EXPECTED_MIN_ROUTES = 57  # route entries at the time the harness was written


def _import_confserver(tmp_path, monkeypatch):
    monkeypatch.setenv("BUMPER_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("BUMPER_CERTS", str(tmp_path / "certs"))
    monkeypatch.setenv("BUMPER_LOGS", str(tmp_path / "logs"))
    monkeypatch.setenv("BUMPER_CA", os.path.join(config.TEST_CERTS_DIR, "ca.crt"))
    monkeypatch.setenv("BUMPER_CERT", os.path.join(config.TEST_CERTS_DIR, "bumper.crt"))
    monkeypatch.setenv("BUMPER_KEY", os.path.join(config.TEST_CERTS_DIR, "bumper.key"))
    monkeypatch.setenv("BUMPER_LISTEN", "127.0.0.1")
    monkeypatch.setenv("LOG_TO_STDOUT", "true")
    # Legacy bumper writes rotating logs to the relative path "logs/"
    monkeypatch.chdir(tmp_path)
    if config.SRC_DIR not in sys.path:
        sys.path.insert(0, config.SRC_DIR)
    import bumper  # noqa: F401  (import side effects: plugin discovery)
    from bumper.confserver import ConfServer

    return ConfServer


def _walk_routes(app):
    """Yield (method, path template, route) for every route, recursing into sub-apps."""
    for resource in app.router.resources():
        info = resource.get_info()
        if "app" in info:
            for item in _walk_routes(info["app"]):
                yield item
            continue
        template = info.get("path", info.get("formatter"))
        for route in resource:
            yield route.method, template, route


def test_every_route_has_a_case(tmp_path, monkeypatch):
    ConfServer = _import_confserver(tmp_path, monkeypatch)
    from aiohttp.test_utils import make_mocked_request

    async def build_and_resolve():
        server = ConfServer(("127.0.0.1", 0), usessl=False)
        server.confserver_app()
        app = server.app
        # A running server freezes the app; freezing turns the root route's
        # empty path "" into "/". Resolve against the same router state.
        app.freeze()
        all_routes = list(_walk_routes(app))
        hits = {}
        for scenario_id, step in cases.http_steps():
            path = cases.VAR.sub("x", step["path"]).split("?", 1)[0]
            req = make_mocked_request(step["method"], path, app=app)
            match = await app.router.resolve(req)
            if match.http_exception is not None:
                continue
            hits.setdefault(id(match.route), []).append("{}: {}".format(scenario_id, step["name"]))
        return all_routes, hits

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        all_routes, hits = loop.run_until_complete(build_and_resolve())
    finally:
        asyncio.set_event_loop(None)
        loop.close()

    assert len(all_routes) >= EXPECTED_MIN_ROUTES, "router walk found only {} routes".format(len(all_routes))
    missing = ["{} {}".format(method, template) for method, template, route in all_routes if id(route) not in hits]
    assert not missing, "{} of {} routes have no case in http_cases.json:\n  {}".format(
        len(missing), len(all_routes), "\n  ".join(sorted(missing))
    )
