FROM node@sha256:4eefa1bfce4197942661ef9148247d779ddf1bb0ee006d3294a467609de60724 AS node
WORKDIR /app
COPY --from=upstream package.json package-lock.json ./
RUN npm ci --ignore-scripts --omit=dev --no-audit --no-fund && npm cache clean --force
RUN npm audit --omit=dev --audit-level=high

FROM python@sha256:69ebe56e2a764c399514a0a6117131cb730cc4d0e71e85c08deb9af74cbb9f41 AS python-deps
COPY requirements.txt /build/requirements.txt
RUN python -m pip install --no-cache-dir --disable-pip-version-check pip==26.2 && \
    python -m pip install --no-cache-dir --require-hashes --only-binary=:all: \
    --no-deps --target /opt/gateway-deps -r /build/requirements.txt

FROM python@sha256:69ebe56e2a764c399514a0a6117131cb730cc4d0e71e85c08deb9af74cbb9f41
LABEL org.opencontainers.image.source="https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure" \
      infrastructure.ynab.upstream="076aa5836658f8332058fa2bd58500aa14326dc9" \
      infrastructure.ynab.gateway="4.1.4"
RUN rm -rf /usr/local/lib/python3.12/site-packages/pip* /usr/local/lib/python3.12/ensurepip /usr/local/bin/pip*
ADD --checksum=sha256:393dcd32629f06d7d85409c272d142d0c082772d10b87ef55ee82f47de3be637 https://dl-cdn.alpinelinux.org/alpine/v3.24/main/x86_64/libgcc-15.2.0-r5.apk /build/libgcc.apk
ADD --checksum=sha256:14c987b556f5385a5db18376e788c75f37d85321b8dc1920d926ea7daac1d6f6 https://dl-cdn.alpinelinux.org/alpine/v3.24/main/x86_64/libstdc++-15.2.0-r5.apk /build/libstdcpp.apk
RUN --network=none apk add --no-network /build/libgcc.apk /build/libstdcpp.apk && rm /build/libgcc.apk /build/libstdcpp.apk
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/LICENSE /usr/share/doc/node/LICENSE
# Both pinned stages use Alpine 3.24/musl. Native APK metadata covers the
# hash-pinned, signature-verified C++ packages; copy no untracked libraries.
RUN ldd /usr/local/bin/node > /tmp/node-libraries && \
    cat /tmp/node-libraries && ! grep -F 'not found' /tmp/node-libraries && \
    /usr/local/bin/node -e "if (process.versions.node.split('.')[0] !== '24') process.exit(1)" && \
    /usr/local/bin/node --version && rm /tmp/node-libraries
COPY --from=python-deps /opt/gateway-deps /opt/gateway-deps
WORKDIR /app
COPY --from=node /app/node_modules ./node_modules
COPY --from=upstream package.json index.js LICENSE ./
COPY --from=upstream lib ./lib
COPY --from=upstream modules ./modules
COPY --from=runtime-policy entrypoint.mjs /policy/entrypoint.mjs
COPY gateway.py /gateway/gateway.py
ENV PYTHONPATH=/opt/gateway-deps PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    YNAB_ALLOW_WRITES=0 YNAB_DISABLE_AGENT_CONFIG_FALLBACK=1 HOME=/tmp
USER 65532:65532
ENTRYPOINT ["/usr/local/bin/python", "/gateway/gateway.py"]
