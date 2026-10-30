FROM node@sha256:a43f7fc3e52e87d12a905f46eea0275def84ca8f2981a5b53fed44d7fb398ee0 AS dependencies
WORKDIR /app
COPY --from=upstream package.json package-lock.json ./
RUN npm ci --ignore-scripts --omit=dev --no-audit --no-fund && npm cache clean --force
RUN npm audit --omit=dev --audit-level=high

FROM gcr.io/distroless/nodejs24-debian13@sha256:bff50773e5717024e83e2527a777dc4da8980e08be4ba6641258f5f9fde17e85
LABEL org.opencontainers.image.source="https://github.com/oliverames/ynab-mcp-server" \
      org.opencontainers.image.revision="076aa5836658f8332058fa2bd58500aa14326dc9" \
      org.opencontainers.image.version="6.1.0"
WORKDIR /app
COPY --from=dependencies /app/node_modules ./node_modules
COPY --from=upstream package.json index.js LICENSE ./
COPY --from=upstream lib ./lib
COPY --from=upstream modules ./modules
COPY entrypoint.mjs /policy/entrypoint.mjs
ENV YNAB_ALLOW_WRITES=0 YNAB_DISABLE_AGENT_CONFIG_FALLBACK=1 HOME=/tmp/ynab
USER 65532:65532
ENTRYPOINT ["/nodejs/bin/node", "/policy/entrypoint.mjs"]
