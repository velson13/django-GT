from gtbook.models import WebhookEvent
from gtbook.utils.webhook_processing import process_webhook
from django.utils import timezone

def process_pending_webhooks():
    pending = WebhookEvent.objects.filter(processed=False)

    for webhook in pending:
        ok, error = process_webhook(webhook)

        if ok:
            webhook.delete()
        else:
            webhook.error = error
            webhook.save(update_fields=["error"])

    print(f"[{timezone.now()}] Processed {pending.count()} webhook(s)")
