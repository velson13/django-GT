import hmac
import hashlib
import base64
from django.conf import settings


def verify_hookrelay_signature(request):
    """
    Validates the HookRelay signature using HMAC SHA256.
    Returns True if valid, False otherwise.
    """

    secret = settings.HOOKRELAY_SECRET
    if not secret:
        return False

    signature = request.headers.get("X-Hookrelay-Signature")
    if not signature:
        return False

    # Decode secret to raw bytes
    secret_bytes = secret.encode("utf-8")

    # Raw request body as bytes
    body = request.body

    # Compute HMAC SHA256
    computed = hmac.new(secret_bytes, body, hashlib.sha256).digest()

    # HookRelay sends Base64-encoded signature
    try:
        received = base64.b64decode(signature)
    except Exception:
        return False

    # Constant-time comparison
    return hmac.compare_digest(computed, received)
