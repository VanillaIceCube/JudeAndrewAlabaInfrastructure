"""Only issuer identities and resource-client policy; no application user data."""
import uuid
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)


class ClientPolicy(models.Model):
    application = models.OneToOneField("oauth2_provider.Application", on_delete=models.CASCADE, related_name="mcp_policy")
    resource = models.URLField(max_length=256)
    allowed_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)

    def clean(self):
        if self.resource not in settings.RESOURCE_SCOPES or (self.resource == settings.YNAB_RESOURCE and self.allowed_user_id is None):
            raise ValidationError("Resource or owner policy is invalid")
        if (self.resource == settings.YNAB_RESOURCE and ClientPolicy.objects.filter(resource=self.resource)
                .exclude(pk=self.pk).exclude(allowed_user_id=self.allowed_user_id).exists()):
            raise ValidationError("All YNAB clients must use the same fixed owner")
