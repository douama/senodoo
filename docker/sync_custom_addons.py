#!/usr/bin/env python3
"""Liste les modules maison dont la version du manifeste a change.

Ecrit sur stdout :

    UPDATE=<modules installes dont la version du manifeste a change>
    AVAILABLE=<modules presents sur disque mais non installes -- information>

Sans ce controle il faudrait manipuler ODOO_UPDATE_MODULES a la main a chaque
modification d'un module maison, et l'oublier laisserait du code neuf avec des
vues et des donnees perimees en base.

Ce script n'installe RIEN de sa propre initiative : deposer un repertoire dans
custom_addons/ ne doit pas ajouter une application a une base de production
sans decision explicite. Les installations passent par ODOO_INSTALL_MODULES ou
par le bouton « Activer » de l'ecran Apps.
"""

# La sortie standard EST l'interface de ce script : l'entrypoint la lit
# avec sed. T201 (interdiction de print) vise le code applicatif Odoo, pas
# un utilitaire en ligne de commande.
# ruff: noqa: T201
import ast
import os
import pathlib
import sys

sys.path.insert(0, os.environ.get("ODOO_HOME", "/opt/odoo"))

import psycopg2  # noqa: E402

from odoo.modules.module import adapt_version  # noqa: E402

CUSTOM = pathlib.Path(os.environ.get("ODOO_HOME", "/opt/odoo")) / "custom_addons"


def declared_modules():
    """Nom -> version normalisee, lue directement dans le manifeste.

    On n'utilise pas `Manifest.for_addon` : elle s'appuie sur l'addons_path
    de la configuration Odoo, qui n'est pas encore chargee a ce stade du
    demarrage. Lire le fichier evite cette dependance.
    """
    if not CUSTOM.is_dir():
        return {}
    found = {}
    for entry in sorted(CUSTOM.iterdir()):
        manifest_file = entry / "__manifest__.py"
        if not manifest_file.is_file():
            continue
        try:
            manifest = ast.literal_eval(manifest_file.read_text(encoding="utf-8"))
        except (SyntaxError, ValueError) as error:
            print(f"# manifeste illisible pour {entry.name}: {error}", file=sys.stderr)
            continue
        if manifest.get("installable", True) and manifest.get("version"):
            found[entry.name] = adapt_version(str(manifest["version"]))
    return found


def main():
    modules = declared_modules()
    if not modules:
        print("UPDATE=")
        print("AVAILABLE=")
        return

    connection = psycopg2.connect(
        host=os.environ["PGHOST"], port=os.environ["PGPORT"],
        user=os.environ["PGUSER"], password=os.environ.get("PGPASSWORD") or None,
        dbname=os.environ["PGDATABASE"],
        sslmode=os.environ.get("PGSSLMODE", "prefer"),
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT name, state, latest_version FROM ir_module_module "
                "WHERE name = ANY(%s)", (list(modules),),
            )
            rows = {name: (state, version) for name, state, version in cursor.fetchall()}
    finally:
        connection.close()

    update, available = [], []
    for name, manifest_version in modules.items():
        state, db_version = rows.get(name, (None, None))
        if state != "installed":
            available.append(name)
        elif db_version != manifest_version:
            update.append(name)

    print("UPDATE=" + ",".join(update))
    print("AVAILABLE=" + ",".join(available))


if __name__ == "__main__":
    main()
