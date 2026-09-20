from app.main import app


def test_the_api_surface():
    # From the OpenAPI schema, not app.routes: included routers with a prefix are nested there.
    routes = {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    }

    assert routes >= {
        ("POST", "/auth/register"),
        ("POST", "/auth/login"),
        ("GET", "/users/me"),
        ("PATCH", "/users/me"),
        ("POST", "/sessions"),
        ("GET", "/sessions"),
        ("GET", "/sessions/{session_id}"),
        ("GET", "/sessions/{session_id}/messages"),
        ("DELETE", "/sessions/{session_id}"),
        ("POST", "/chat"),
        ("GET", "/health"),
    }
    assert ("POST", "/auth/refresh") not in routes  # no refresh tokens: access tokens never expire


def test_the_openapi_schema_builds():
    assert app.openapi()["paths"]["/chat"]["post"]
