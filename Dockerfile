# syntax=docker/dockerfile:1

# ============================================================================
# Odoo saas~19.2 - image de deploiement (Render / Railway / VPS)
#
# Python 3.12 : odoo/release.py declare MIN_PY_VERSION = (3, 12) et
# requirements.txt epingle les versions "Noble" (Ubuntu 24.04) sur
# python_version >= '3.12' and < '3.13'.
# ============================================================================

# ---------------------------------------------------------------------------
# Etage 1 : compilation des dependances Python dans un venv isole.
# psycopg2 (2.9.9) et python-ldap (3.4.4) n'ont pas de wheel manylinux :
# ils exigent un compilateur + les headers libpq / libldap / libsasl.
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        libldap2-dev \
        libsasl2-dev \
        libxml2-dev \
        libxslt1-dev \
        libjpeg62-turbo-dev \
        zlib1g-dev \
        libffi-dev \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip setuptools wheel \
    && pip install -r /tmp/requirements.txt

# ---------------------------------------------------------------------------
# Etage 2 : image finale (aucun compilateur, uniquement les libs runtime)
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

# TARGETARCH est renseigne automatiquement par BuildKit (amd64 sur Render et
# Railway, arm64 sur un Mac Apple Silicon). Ne PAS lui donner de valeur par
# defaut : elle ecraserait la valeur reelle et ferait installer un paquet
# d'architecture etrangere, dont les dependances sont introuvables.
ARG TARGETARCH
ARG WKHTMLTOPDF_VERSION=0.12.6.1-3

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    ODOO_HOME=/opt/odoo \
    ODOO_DATA_DIR=/var/lib/odoo

RUN apt-get update && apt-get install -y --no-install-recommends \
        postgresql-client \
        libpq5 \
        libldap-2.5-0 \
        libsasl2-2 \
        libxml2 \
        libxslt1.1 \
        libmagic1 \
        fonts-dejavu-core \
        fonts-freefont-ttf \
        fonts-liberation \
        fonts-noto-core \
        fonts-noto-cjk \
        fontconfig \
        libxrender1 \
        libxext6 \
        libx11-6 \
        libjpeg62-turbo \
        xfonts-75dpi \
        xfonts-base \
        ca-certificates \
        curl \
        gosu \
    && rm -rf /var/lib/apt/lists/*

# wkhtmltopdf 0.12.6 "patched qt" : version requise par Odoo pour les rapports
# PDF. Les builds Debian standards cassent les en-tetes / pieds de page.
RUN set -eux; \
    url="https://github.com/wkhtmltopdf/packaging/releases/download/${WKHTMLTOPDF_VERSION}/wkhtmltox_${WKHTMLTOPDF_VERSION}.bookworm_${TARGETARCH}.deb"; \
    curl -fSL -o /tmp/wkhtmltox.deb "$url"; \
    apt-get update; \
    apt-get install -y --no-install-recommends /tmp/wkhtmltox.deb; \
    rm -f /tmp/wkhtmltox.deb; \
    rm -rf /var/lib/apt/lists/*; \
    wkhtmltopdf --version

COPY --from=builder /opt/venv /opt/venv

RUN groupadd -r odoo && useradd -r -g odoo -d "$ODOO_HOME" -s /sbin/nologin odoo

WORKDIR $ODOO_HOME
COPY --chown=odoo:odoo . $ODOO_HOME
COPY --chown=root:root docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh /opt/odoo/odoo-bin

# /var/lib/odoo doit etre monte sur un volume persistant : il contient le
# filestore (pieces jointes, assets compiles) et les sessions.
RUN mkdir -p "$ODOO_DATA_DIR" /etc/odoo && chown -R odoo:odoo "$ODOO_DATA_DIR" /etc/odoo
VOLUME ["/var/lib/odoo"]

EXPOSE 8069

HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-8069}/web/health" || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["odoo"]
