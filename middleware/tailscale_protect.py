import re
from django.conf import settings
from django.http import HttpResponseForbidden

class TailscaleProtectMiddleware:
    """
    - Allows all access if DEBUG=True (local development)
    - Allows public access ONLY to configured public paths (webhooks)
    - Allows access to everything else ONLY if the client comes from Tailscale (100.x.x.x)
    """

    PUBLIC_PATHS = [
        r"^/api/efaktura/",
        # r"^/api/",
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        
        # 1) Allow everything in DEBUG mode (local dev)
        if settings.DEBUG:
            return self.get_response(request)
        
        # 2) Allow explicitly public webhook paths
        path = request.path
        for pattern in self.PUBLIC_PATHS:
            if re.match(pattern, path):
                return self.get_response(request)

        # Allow Tailscale clients (MagicDNS IP range: 100.0.0.0/8)
        client_ip = request.META.get("REMOTE_ADDR", "")

        if client_ip.startswith("100."):
            return self.get_response(request)

        # Reject all other Internet traffic
        return HttpResponseForbidden("403 Zabranjeno van Tailscale mreže.")
