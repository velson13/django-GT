# import hmac
# import hashlib
# import base64
# from django.conf import settings


# def verify_hookrelay_signature(request):
#     """
#     Validates the HookRelay signature using HMAC SHA256.
#     Returns True if valid, False otherwise.
#     """

#     secret = settings.HOOKRELAY_SECRET
#     if not secret:
#         return False

#     signature = request.headers.get("X-Hookrelay-Signature")
#     if not signature:
#         return False

#     # Decode secret to raw bytes
#     secret_bytes = secret.encode("utf-8")

#     # Raw request body as bytes
#     body = request.body

#     # Compute HMAC SHA256
#     computed = hmac.new(secret_bytes, body, hashlib.sha256).digest()

#     # HookRelay sends Base64-encoded signature
#     try:
#         received = base64.b64decode(signature)
#     except Exception:
#         return False

#     # Constant-time comparison
#     return hmac.compare_digest(computed, received)
import hmac
import hashlib
import base64
from django.conf import settings

def verify_hookrelay_signature(request, debug=False):
    """
    Validates the HookRelay signature using HMAC SHA256.
    Returns True if valid, False otherwise.
    If debug=True, prints received vs computed signature and body.
    """
    secret = getattr(settings, "HOOKRELAY_SECRET", None)
    if not secret:
        if debug:
            print("[HookRelay] No HOOKRELAY_SECRET configured")
        return False

    signature = request.headers.get("X-Hookrelay-Signature")
    if not signature:
        if debug:
            print("[HookRelay] No X-Hookrelay-Signature header found")
        return False

    # Raw body as bytes
    body = request.body
    secret_bytes = secret.encode("utf-8")

    # Compute HMAC SHA256
    computed = hmac.new(secret_bytes, body, hashlib.sha256).digest()

    # HookRelay sends Base64-encoded signature
    try:
        received = base64.b64decode(signature)
    except Exception:
        if debug:
            print("[HookRelay] Failed to decode Base64 signature:", signature)
        return False

    if debug:
        print("=== HookRelay Signature Debug ===")
        print("Raw body bytes:", body)
        print("Received signature:", signature)
        print("Computed signature:", base64.b64encode(computed).decode())
        print("Matches:", hmac.compare_digest(computed, received))
        print("=== End Debug ===")

    return hmac.compare_digest(computed, received)
