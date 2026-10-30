import re
from urllib.parse import urlsplit

from .registration import valid_callback


class PrivateResponses:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response["Cache-Control"] = "no-store"
        response["Pragma"] = "no-cache"
        # Django's HTTPS CSRF fallback needs same-origin Referer when Origin is absent.
        response["Referrer-Policy"] = "same-origin"
        form_action = "'self'"
        # Only ConsentView's validated form may opt into its callback origin.
        # Never interpolate caller-controlled query/POST values or grant secrets.
        callback = getattr(response, "mcp_consent_callback", None)
        if callback and valid_callback(callback):
            uri = urlsplit(callback)
            if re.fullmatch(r"(?:[A-Za-z0-9.-]+|\[[0-9A-Fa-f:]+\])(?::[0-9]+)?", uri.netloc):
                form_action += " " + uri.scheme + "://" + uri.netloc
        response["Content-Security-Policy"] = (
            "default-src 'none'; form-action " + form_action + "; frame-ancestors 'none'; base-uri 'none'"
        )
        return response
