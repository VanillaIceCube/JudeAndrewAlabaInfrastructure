FROM ubuntu/squid@sha256:94f844158e12b52f51b4ae996515e37e8fb3e8d85e1c86caba1a297376e4ec4f
LABEL org.opencontainers.image.source="https://github.com/VanillaIceCube/JudeAndrewAlabaInfrastructure"
# Official Ubuntu security packages; hashes also verified against signed apt metadata.
ADD --checksum=sha256:219f43b1cd836a4da550938db5fda93160d269d39a4edcf1f1ce698a470db797 https://archive.ubuntu.com/ubuntu/pool/main/o/openssl/libssl3t64_3.0.13-0ubuntu3.16_amd64.deb /tmp/ynab-security/libssl3t64.deb
ADD --checksum=sha256:675b84971ffd4467707008c25ef7520f90ea7c23ef27b7a76b0dccf1d7c4dc3f https://archive.ubuntu.com/ubuntu/pool/main/o/openssl/openssl_3.0.13-0ubuntu3.16_amd64.deb /tmp/ynab-security/openssl.deb
RUN --network=none dpkg -i /tmp/ynab-security/libssl3t64.deb /tmp/ynab-security/openssl.deb && \
    dpkg --audit && rm -rf /tmp/ynab-security
USER 13:13
ENTRYPOINT ["/usr/sbin/squid"]
CMD ["-N", "-f", "/etc/squid/squid.conf", "-d0"]
