from pathlib import Path
import os

from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from auth_service.models import User
from auth_service.secrets import protected_text


class Command(BaseCommand):
    help = "Create a closed issuer account from a protected password file; never read a Notoli database."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--password-file", required=True)
        parser.add_argument("--subject-output", required=True)

    def handle(self, *args, **options):
        target = Path(options["subject_output"])
        if target.exists() or User.objects.filter(username=options["username"]).exists():
            raise CommandError("Existing account or output; explicit recovery required")
        password = protected_text(options["password_file"], maximum=1024).strip()
        user = User(username=options["username"])
        validate_password(password, user)
        with transaction.atomic():
            user.set_password(password)
            user.full_clean()
            user.save()
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                output.write(str(user.pk) + "\n")
        self.stdout.write("Issuer account created; immutable subject saved privately")
