"""Closed, operator-provisioned registrations; no HTTP client-registration API."""
from urllib.parse import urlsplit


def valid_callback(value):
    try:
        uri = urlsplit(value)
        _ = uri.port
        return (len(value) <= 2048 and "*" not in value and not any(c.isspace() for c in value)
                and bool(uri.hostname) and not uri.username and not uri.password and not uri.fragment
                and (uri.scheme == "https" or uri.scheme == "http" and uri.hostname in {"127.0.0.1", "::1"}))
    except (TypeError, ValueError):
        return False
