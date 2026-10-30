FROM python@sha256:69ebe56e2a764c399514a0a6117131cb730cc4d0e71e85c08deb9af74cbb9f41 AS dependencies
COPY requirements.txt /build/requirements.txt
RUN python -m pip install --no-cache-dir --disable-pip-version-check --no-compile \
    --require-hashes --only-binary=:all: --no-deps --target /opt/auth-deps -r /build/requirements.txt && \
    PYTHONPATH=/opt/auth-deps python -m pip check

FROM python@sha256:69ebe56e2a764c399514a0a6117131cb730cc4d0e71e85c08deb9af74cbb9f41
LABEL org.opencontainers.image.source="https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure" \
      infrastructure.mcp.authorization="django-oauth-toolkit3.4.1"
RUN rm -rf /usr/local/lib/python3.12/site-packages/pip* /usr/local/lib/python3.12/ensurepip /usr/local/bin/pip*
COPY --from=dependencies /opt/auth-deps /opt/auth-deps
WORKDIR /app
COPY backend/manage.py ./manage.py
COPY backend/auth_service ./auth_service
COPY backend/mcp_framework/__init__.py backend/mcp_framework/config.py backend/mcp_framework/proxy.py ./mcp_framework/
COPY SHARED-FRAMEWORK-LICENSE.md /usr/share/doc/mcp-framework/LICENSE.md
ENV PYTHONPATH=/app:/opt/auth-deps PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=auth_service.settings HOME=/tmp
USER 65532:65532
ENTRYPOINT ["/usr/local/bin/python", "-m", "uvicorn", "auth_service.asgi:application", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-proxy-headers", "--no-access-log"]
