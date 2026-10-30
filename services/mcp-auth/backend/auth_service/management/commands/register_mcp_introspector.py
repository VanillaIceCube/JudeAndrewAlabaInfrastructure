from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from oauth2_provider.models import Application

from auth_service.secrets import protected_text


class Command(BaseCommand):
    help = "Install a dedicated app introspection credential from a protected file; cannot issue tokens."

    def add_arguments(self, parser):
        parser.add_argument("--secret-file", required=True)
        parser.add_argument("--resource", choices=("notoli", "macromapper"), required=True)
        parser.add_argument("--rotate", action="store_true")

    def handle(self, *args, **options):
        client_id = options["resource"] + "-introspection"
        existing = Application.objects.filter(client_id=client_id).first()
        if bool(existing) != options["rotate"]:
            raise CommandError("Registration state differs; rotation requires an existing dedicated client")
        if existing and (existing.client_type != Application.CLIENT_CONFIDENTIAL or hasattr(existing, "mcp_policy")):
            raise CommandError("Existing client is not a dedicated introspector")
        secret = protected_text(options["secret_file"], maximum=256).strip()
        if len(secret) < 32 or any(c.isspace() for c in secret):
            raise CommandError("Invalid protected introspection secret")
        if existing:
            existing.client_secret = secret
            existing.save(update_fields=["client_secret"])
        else:
            Application.objects.create(client_id=client_id, name=options["resource"] + " introspection",
                                       client_secret=secret, client_type=Application.CLIENT_CONFIDENTIAL,
                                       authorization_grant_type=Application.GRANT_CLIENT_CREDENTIALS)
        self.stdout.write("Dedicated introspection registration created")
