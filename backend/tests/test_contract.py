from app import main

ENDPOINTS = [
    ("POST", "/sessions/{id}/panel/generate"),
    ("POST", "/sessions/{id}/panel/confirm"),
    ("POST", "/sessions/{id}/discussion/start"),
    ("POST", "/sessions/{id}/discussion/pause"),
    ("POST", "/sessions/{id}/discussion/resume"),
    ("POST", "/sessions/{id}/discussion/end"),
    ("POST", "/sessions/{id}/retry"),
    ("GET", "/sessions/{id}"),
    ("GET", "/sessions/{id}/events"),
    ("DELETE", "/sessions/{id}"),
]


def test_routes_registered():
    registered = set()
    for r in main.app.routes:
        if hasattr(r, "methods") and hasattr(r, "path"):
            for m in r.methods:
                registered.add((m, r.path))
    for method, path in ENDPOINTS:
        assert (method, path) in registered, f"missing {method} {path}"
