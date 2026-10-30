from django.contrib.auth.views import LoginView, LogoutView, PasswordChangeView, PasswordChangeDoneView
from django.urls import include, path
from oauth2_provider.views import TokenView, RevokeTokenView, AuthorizedTokensListView, AuthorizedTokenDeleteView

from .views import ConsentView, IntrospectionView, MetadataView, live, ready

oauth_urls = ([
    path("authorize/", ConsentView.as_view(), name="authorize"),
    path("token/", TokenView.as_view(), name="token"),
    path("revoke_token/", RevokeTokenView.as_view(), name="revoke-token"),
    path("introspect/", IntrospectionView.as_view(), name="introspect"),
    path("authorized_tokens/", AuthorizedTokensListView.as_view(), name="authorized-token-list"),
    path("authorized_tokens/<slug:pk>/delete/", AuthorizedTokenDeleteView.as_view(), name="authorized-token-delete"),
], "oauth2_provider")
urlpatterns = [
    path(".well-known/oauth-authorization-server", MetadataView.as_view()), path("o/", include(oauth_urls)),
    path("accounts/login/", LoginView.as_view(), name="login"),
    path("accounts/logout/", LogoutView.as_view(), name="logout"),
    path("accounts/password_change/", PasswordChangeView.as_view(), name="password_change"),
    path("accounts/password_change/done/", PasswordChangeDoneView.as_view(), name="password_change_done"),
    path("health/live", live), path("health/ready", ready),
]
