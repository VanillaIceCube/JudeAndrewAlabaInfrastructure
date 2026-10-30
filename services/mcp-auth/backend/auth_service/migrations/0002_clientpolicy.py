from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    dependencies = [("auth_service", "0001_initial"), migrations.swappable_dependency(settings.OAUTH2_PROVIDER_APPLICATION_MODEL)]
    operations = [
        migrations.CreateModel(
            name="ClientPolicy",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("resource", models.URLField(max_length=256)),
                (
                    "allowed_user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "application",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="mcp_policy",
                        to=settings.OAUTH2_PROVIDER_APPLICATION_MODEL,
                    ),
                ),
            ],
        ),
    ]
