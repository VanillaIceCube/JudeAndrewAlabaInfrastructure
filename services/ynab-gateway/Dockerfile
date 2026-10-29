FROM node@sha256:a43f7fc3e52e87d12a905f46eea0275def84ca8f2981a5b53fed44d7fb398ee0 AS node
WORKDIR /app
COPY --from=upstream package.json package-lock.json ./
RUN npm ci --ignore-scripts --omit=dev --no-audit --no-fund && npm cache clean --force
RUN npm audit --omit=dev --audit-level=high

FROM python@sha256:623674a14ef93d052bb9b0de4dbf5f28eb578a35263838941cc8aa43213c1487 AS python-deps
COPY requirements.txt /build/requirements.txt
RUN python -m pip install --no-cache-dir --disable-pip-version-check pip==26.2 && \
    python -m pip install --no-cache-dir --require-hashes --only-binary=:all: \
    --no-deps --target /opt/gateway-deps -r /build/requirements.txt

FROM python@sha256:623674a14ef93d052bb9b0de4dbf5f28eb578a35263838941cc8aa43213c1487
LABEL org.opencontainers.image.source="https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure" \
      infrastructure.ynab.upstream="076aa5836658f8332058fa2bd58500aa14326dc9" \
      infrastructure.ynab.gateway="4.1.4"
RUN rm -rf /usr/local/lib/python3.12/site-packages/pip* /usr/local/lib/python3.12/ensurepip /usr/local/bin/pip*
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/LICENSE /usr/share/doc/node/LICENSE
COPY --from=node /usr/lib/x86_64-linux-gnu/libstdc++.so.6 /usr/lib/x86_64-linux-gnu/libstdc++.so.6
COPY --from=node /lib/x86_64-linux-gnu/libgcc_s.so.1 /lib/x86_64-linux-gnu/libgcc_s.so.1
# The immutable Debian bookworm base supplies glibc/libm/libdl/libpthread;
# the two deliberate copies above supply Node's C++ runtime.
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
