#!/usr/bin/env bash
# ============================================================================
# Entrypoint Odoo pour plateformes conteneurisees (Render, Railway, VPS).
#
# Role :
#   1. Determiner le mode d'execution demande
#   2. Traduire DATABASE_URL (fourni par Render/Railway) en variables PG*
#   3. Generer /etc/odoo/odoo.conf a partir de l'environnement
#   4. Attendre PostgreSQL, puis initialiser la base au premier demarrage
#   5. Lancer la commande en tant qu'utilisateur non-root
# ============================================================================
set -euo pipefail

ODOO_BIN=/opt/odoo/odoo-bin
ODOO_CONF=/etc/odoo/odoo.conf
DATA_DIR="${ODOO_DATA_DIR:-/var/lib/odoo}"

log() { printf '[entrypoint] %s\n' "$*" >&2; }
die() { printf '[entrypoint] ERREUR: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 1. Mode d'execution
#
# Doit etre determine AVANT toute operation reseau : une commande utilitaire
# (`bash`, `psql`, `wkhtmltopdf --version`) ne doit pas attendre PostgreSQL.
# Sans ce tri, `docker run <image> bash` bloquerait jusqu'au timeout, ce qui
# rend inutilisable le shell de Render et de Railway.
# ---------------------------------------------------------------------------
MODE=server
NEEDS_DB=true

case "${1:-odoo}" in
    odoo|server)
        MODE=server
        ;;
    shell|db|i18n|module|neutralize|populate|start)
        # sous-commandes odoo-bin operant sur une base existante
        MODE=odoo_cli
        ;;
    cloc|deploy|help|obfuscate|scaffold|upgrade_code)
        # sous-commandes odoo-bin ne touchant pas a la base
        MODE=odoo_cli
        NEEDS_DB=false
        ;;
    -*)
        # arguments bruts pour le serveur ; --version et --help sortent
        # immediatement sans contacter PostgreSQL.
        MODE=server_args
        for arg in "$@"; do
            case "$arg" in
                --version|--help|-h) NEEDS_DB=false ;;
            esac
        done
        ;;
    *)
        # commande arbitraire : aucun traitement Odoo, execution directe.
        exec "$@"
        ;;
esac

# ---------------------------------------------------------------------------
# 2. DATABASE_URL -> PG*
# Render et Railway exposent une URL unique. Odoo lit PGHOST/PGPORT/PGUSER/
# PGPASSWORD/PGDATABASE/PGSSLMODE nativement (cf. env_name dans
# odoo/tools/config.py), mais on les materialise pour pg_isready et psql.
# ---------------------------------------------------------------------------
if [ -n "${DATABASE_URL:-}" ]; then
    log "DATABASE_URL detectee, extraction des parametres de connexion"
    # Le parsing passe par Python : gere le percent-encoding des mots de passe
    # (un @ ou un : dans un mot de passe casserait un parsing sed/awk).
    eval "$(python - <<'PY'
import os
import shlex
from urllib.parse import urlparse, parse_qs, unquote

url = urlparse(os.environ["DATABASE_URL"])
if url.scheme not in ("postgres", "postgresql"):
    raise SystemExit(f"schema d'URL non supporte: {url.scheme!r}")

mapping = {
    "PGHOST": url.hostname or "",
    "PGPORT": str(url.port or 5432),
    "PGUSER": unquote(url.username or ""),
    "PGPASSWORD": unquote(url.password or ""),
    "PGDATABASE": unquote((url.path or "/").lstrip("/")),
}
sslmode = parse_qs(url.query).get("sslmode", [""])[0]
if sslmode:
    mapping["PGSSLMODE"] = sslmode

for key, value in mapping.items():
    if value:
        print(f"export {key}={shlex.quote(value)}")
PY
)"
fi

PGHOST="${PGHOST:-db}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-odoo}"
PGPASSWORD="${PGPASSWORD:-}"
PGDATABASE="${PGDATABASE:-odoo}"
PGSSLMODE="${PGSSLMODE:-prefer}"
export PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE PGSSLMODE

[ -n "$PGDATABASE" ] || die "PGDATABASE vide : impossible de determiner la base cible"

# ---------------------------------------------------------------------------
# 3. Generation de la configuration
#
# Choix contraints par la plateforme :
#   * http_interface = 0.0.0.0 : le defaut Odoo est 127.0.0.1, injoignable
#     depuis l'exterieur d'un conteneur (odoo/tools/config.py:247).
#   * workers = 0 (mode threade) : en prefork, le worker gevent ecoute sur un
#     SECOND port (gevent_port, odoo/service/server.py:783) alors que Render et
#     Railway n'exposent qu'un seul port. En mode threade, ThreadedServer sert
#     HTTP et websocket sur le meme port.
#   * db_maxconn bas : les bases PostgreSQL managees plafonnent le nombre de
#     connexions bien en dessous du defaut Odoo (64).
#   * admin_passwd doit passer par le fichier : c'est une FileOnlyOption
#     (odoo/tools/config.py:197), non surchargeable en CLI.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# addons_path : les addons Community d'origine, puis les modules maison.
#
# custom_addons/ contient senodoo_app_upgrade, qui remplace le lien mort vers
# odoo.com/pricing des applications Enterprise par une vraie operation
# serveur. Le repertoire est teste avant d'etre ajoute : une image construite
# sans lui doit continuer a demarrer.
#
# ODOO_EXTRA_ADDONS_PATH permet d'ajouter un chemin supplementaire (volume
# monte, depot d'addons tiers) sans reconstruire l'image.
# ---------------------------------------------------------------------------
ODOO_HOME="${ODOO_HOME:-/opt/odoo}"
ADDONS_PATH="${ODOO_HOME}/addons"
if [ -d "${ODOO_HOME}/custom_addons" ]; then
    ADDONS_PATH="${ADDONS_PATH},${ODOO_HOME}/custom_addons"
fi
if [ -n "${ODOO_EXTRA_ADDONS_PATH:-}" ]; then
    ADDONS_PATH="${ADDONS_PATH},${ODOO_EXTRA_ADDONS_PATH}"
fi
log "addons_path = ${ADDONS_PATH}"

ADMIN_PASSWD="${ODOO_ADMIN_PASSWD:-}"
if [ -z "$ADMIN_PASSWD" ]; then
    log "AVERTISSEMENT: ODOO_ADMIN_PASSWD non defini, valeur de repli 'admin'."
    log "               A changer imperativement avant toute mise en production."
    ADMIN_PASSWD=admin
fi

HTTP_PORT="${PORT:-${ODOO_HTTP_PORT:-8069}}"

umask 077
cat > "$ODOO_CONF" <<EOF
[options]
; genere par docker/entrypoint.sh au demarrage - ne pas editer a la main
addons_path = ${ADDONS_PATH}
data_dir = ${DATA_DIR}

db_host = ${PGHOST}
db_port = ${PGPORT}
db_user = ${PGUSER}
db_password = ${PGPASSWORD}
db_name = ${PGDATABASE}
db_sslmode = ${PGSSLMODE}
db_maxconn = ${ODOO_DB_MAXCONN:-16}

admin_passwd = ${ADMIN_PASSWD}
list_db = ${ODOO_LIST_DB:-False}
dbfilter = ${ODOO_DBFILTER:-^${PGDATABASE}$}

http_interface = 0.0.0.0
http_port = ${HTTP_PORT}
proxy_mode = ${ODOO_PROXY_MODE:-True}

workers = ${ODOO_WORKERS:-0}
max_cron_threads = ${ODOO_MAX_CRON_THREADS:-1}
limit_time_cpu = ${ODOO_LIMIT_TIME_CPU:-120}
limit_time_real = ${ODOO_LIMIT_TIME_REAL:-300}

without_demo = ${ODOO_WITHOUT_DEMO:-all}
log_level = ${ODOO_LOG_LEVEL:-info}
EOF
umask 022
chmod 640 "$ODOO_CONF"
log "configuration ecrite dans $ODOO_CONF (base=$PGDATABASE hote=$PGHOST port=$HTTP_PORT)"

# ---------------------------------------------------------------------------
# 4. Droits sur le volume persistant
# Les disques Render / volumes Railway sont montes appartenant a root.
# ---------------------------------------------------------------------------
mkdir -p "$DATA_DIR"
if [ "$(id -u)" -eq 0 ]; then
    chown odoo:odoo "$ODOO_CONF"
    # -R uniquement si le proprietaire ne correspond pas deja : evite de
    # parcourir un filestore de plusieurs Go a chaque redemarrage.
    if [ "$(stat -c '%U' "$DATA_DIR")" != "odoo" ]; then
        log "correction des droits sur $DATA_DIR"
        chown -R odoo:odoo "$DATA_DIR"
    fi
fi

run_odoo() {
    if [ "$(id -u)" -eq 0 ]; then
        exec gosu odoo "$@"
    fi
    exec "$@"
}

as_odoo() {
    if [ "$(id -u)" -eq 0 ]; then
        gosu odoo "$@"
    else
        "$@"
    fi
}

# ---------------------------------------------------------------------------
# 5. Attente de PostgreSQL, initialisation et mises a jour
#
# odoo/modules/loading.py:372 : si le schema est absent, Odoo refuse de
# demarrer ("Database not initialized, you can force it with `-i base`") sauf
# si update_module est actif. On installe donc le module `base` dans la base
# vide fournie par la plateforme. Aucun droit CREATEDB n'est requis : Odoo
# ecrit dans une base deja existante.
# ---------------------------------------------------------------------------
if [ "$NEEDS_DB" = true ]; then
    WAIT_TIMEOUT="${ODOO_DB_WAIT_TIMEOUT:-120}"
    log "attente de PostgreSQL sur ${PGHOST}:${PGPORT} (timeout ${WAIT_TIMEOUT}s)"
    elapsed=0
    until pg_isready -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -q; do
        if [ "$elapsed" -ge "$WAIT_TIMEOUT" ]; then
            die "PostgreSQL injoignable apres ${WAIT_TIMEOUT}s"
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    log "PostgreSQL est pret"

    if [ "${ODOO_AUTO_INIT:-true}" = "true" ]; then
        schema_present="$(psql -d "$PGDATABASE" -tAc \
            "SELECT 1 FROM pg_catalog.pg_tables WHERE schemaname='public' AND tablename='ir_module_module'" \
            2>/dev/null || true)"

        if [ "$schema_present" != "1" ]; then
            INIT_MODULES="${ODOO_INIT_MODULES:-base}"
            log "base '$PGDATABASE' vide -> initialisation avec: $INIT_MODULES"
            log "(cette etape peut prendre plusieurs minutes)"
            as_odoo "$ODOO_BIN" -c "$ODOO_CONF" \
                --database "$PGDATABASE" \
                --init "$INIT_MODULES" \
                --without-demo=all \
                --stop-after-init
            log "initialisation terminee"
        else
            log "schema Odoo deja present, initialisation ignoree"
        fi
    fi

    # ---------------------------------------------------------------
    # Synchronisation des modules maison (custom_addons/)
    #
    # docker/sync_custom_addons.py compare la version de chaque manifeste a
    # celle enregistree en base et repond quoi installer et quoi mettre a
    # jour. Sans ce controle il faudrait manipuler ODOO_UPDATE_MODULES a la
    # main a chaque changement -- et l'oublier laisserait du code neuf avec
    # des vues et des donnees perimees.
    #
    # ODOO_SYNC_CUSTOM_ADDONS=false desactive le mecanisme.
    # ---------------------------------------------------------------
    if [ "${ODOO_SYNC_CUSTOM_ADDONS:-true}" = "true" ] \
       && [ -f "${ODOO_HOME}/docker/sync_custom_addons.py" ]; then
        sync_output="$(as_odoo python "${ODOO_HOME}/docker/sync_custom_addons.py" 2>&1)" || {
            log "AVERTISSEMENT: synchronisation des modules maison impossible :"
            printf '%s\n' "$sync_output" >&2
            sync_output=""
        }
        to_update="$(printf '%s\n' "$sync_output" | sed -n 's/^UPDATE=//p')"
        available="$(printf '%s\n' "$sync_output" | sed -n 's/^AVAILABLE=//p')"

        if [ -n "${to_update:-}" ]; then
            log "modules maison a mettre a jour: $to_update"
            as_odoo "$ODOO_BIN" -c "$ODOO_CONF" \
                --database "$PGDATABASE" --update "$to_update" --stop-after-init
        else
            log "modules maison a jour"
        fi
        # Purement informatif : l'installation reste une decision explicite.
        if [ -n "${available:-}" ]; then
            log "modules maison disponibles mais non installes: $available"
        fi
    fi

    # Installation de modules a la demande (ODOO_INSTALL_MODULES="stock,mrp").
    #
    # Complement manuel a la synchronisation ci-dessus, pour un module qui
    # n'est pas dans custom_addons/. `-i` est deja idempotent cote Odoo
    # (modules/loading.py : seuls les modules `uninstalled` sont installes),
    # mais chaque passage coute un cycle de demarrage : on interroge donc
    # d'abord l'etat en base.
    if [ -n "${ODOO_INSTALL_MODULES:-}" ]; then
        pending=""
        for candidate in $(printf '%s' "$ODOO_INSTALL_MODULES" | tr ',' ' '); do
            # Un nom de module Odoo est [a-z0-9_] : tout le reste est rejete
            # plutot qu'interpole dans la requete SQL.
            case "$candidate" in
                *[!a-z0-9_]*|'')
                    die "nom de module invalide dans ODOO_INSTALL_MODULES: '$candidate'" ;;
            esac
            state="$(psql -d "$PGDATABASE" -tAc \
                "SELECT state FROM ir_module_module WHERE name = '$candidate'" 2>/dev/null || true)"
            if [ "$state" != "installed" ]; then
                pending="${pending:+$pending,}$candidate"
            fi
        done
        if [ -n "$pending" ]; then
            log "installation des modules: $pending"
            as_odoo "$ODOO_BIN" -c "$ODOO_CONF" \
                --database "$PGDATABASE" \
                --init "$pending" \
                --stop-after-init
            log "installation terminee"
        else
            log "modules deja installes, rien a faire: $ODOO_INSTALL_MODULES"
        fi
    fi

    # Mise a jour de modules a la demande (ODOO_UPDATE_MODULES="web,base").
    # Retirer la variable apres coup, sinon la mise a jour est rejouee a
    # chaque redemarrage.
    if [ -n "${ODOO_UPDATE_MODULES:-}" ]; then
        log "mise a jour des modules: $ODOO_UPDATE_MODULES"
        as_odoo "$ODOO_BIN" -c "$ODOO_CONF" \
            --database "$PGDATABASE" \
            --update "$ODOO_UPDATE_MODULES" \
            --stop-after-init
        log "mise a jour terminee"
    fi
fi

# ---------------------------------------------------------------------------
# 6. Lancement
# ---------------------------------------------------------------------------
case "$MODE" in
    server)
        log "demarrage du serveur Odoo"
        run_odoo "$ODOO_BIN" -c "$ODOO_CONF"
        ;;
    server_args)
        run_odoo "$ODOO_BIN" -c "$ODOO_CONF" "$@"
        ;;
    odoo_cli)
        run_odoo "$ODOO_BIN" "$@" -c "$ODOO_CONF"
        ;;
esac
