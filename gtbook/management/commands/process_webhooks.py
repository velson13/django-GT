from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

from gtbook.models import WebhookEvent
from gtbook.utils.webhook_processing import process_webhook


class Command(BaseCommand):
    help = "Process pending webhook events"

    def handle(self, *args, **options):
        pending = (WebhookEvent.objects.select_for_update(skip_locked=True))

        processed_count = 0

        for webhook in pending:
            ok, error = process_webhook(webhook)

            if ok:
                webhook.delete()
                processed_count += 1
            else:
                webhook.error = error
                webhook.save(update_fields=["error"])

        self.stdout.write(
            f"[{timezone.now()}] Processed {processed_count} webhook(s)"
        )
