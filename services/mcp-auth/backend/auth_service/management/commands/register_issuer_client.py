from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from oauth2_provider.models import Application

from auth_service.models import ClientPolicy, User
from auth_service.registration import valid_callback


class Command(BaseCommand):
    help = "Register one exact resource/client; refuses existing IDs and ambiguous callbacks."

    def add_arguments(self, parser):
        parser.add_argument("--resource", choices=("ynab", "notoli", "macromapper"), required=True)
        parser.add_argument("--client", choices=("chatgpt", "codex"), required=True)
        parser.add_argument("--owner-subject", required=True)
        parser.add_argument("--redirect-uri", action="append", required=True)

    def handle(self, *args, **options):
        client_id = options["resource"] + "-" + options["client"]
        redirects = options["redirect_uri"]
        if (Application.objects.filter(client_id=client_id).exists() or len(redirects) != len(set(redirects))
                or not all(valid_callback(value) for value in redirects)
                or options["client"] == "chatgpt" and not all(value.startswith("https://") for value in redirects)):
            raise CommandError("Existing registration or invalid exact callbacks")
        try:
            owner = User.objects.get(pk=options["owner_subject"], is_active=True)
        except (User.DoesNotExist, ValueError, ValidationError):
            raise CommandError("An existing active issuer owner is required") from None
        resource = {"ynab": settings.YNAB_RESOURCE, "notoli": settings.NOTOLI_RESOURCE,
                    "macromapper": settings.MACROMAPPER_RESOURCE}[options["resource"]]
        with transaction.atomic():
            application = Application.objects.create(
                client_id=client_id, name=client_id, user=owner, client_type=Application.CLIENT_PUBLIC,
                authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
                redirect_uris=" ".join(redirects), skip_authorization=False)
            policy = ClientPolicy(application=application, resource=resource,
                                  allowed_user=owner if options["resource"] == "ynab" else None)
            policy.full_clean()
            policy.save()
        self.stdout.write("Exact resource/client registration created")
