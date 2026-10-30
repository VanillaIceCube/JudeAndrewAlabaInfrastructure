"""Invalidate restored authorization state before the isolated service restarts."""
from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand
from django.db import transaction
from oauth2_provider.models import AccessToken, Grant, RefreshToken


class Command(BaseCommand):
    help = "Invalidate all MCP codes, tokens and browser sessions; service must be stopped."

    def handle(self, *args, **options):
        # The release controller holds its exclusive lock and stops issuance first.
        # Delete refresh tokens first: DOT may retain revoked rotation history.
        with transaction.atomic():
            for model in (RefreshToken, AccessToken, Grant, Session):
                model.objects.all().delete()
        self.stdout.write("All MCP grants and browser sessions invalidated.")
