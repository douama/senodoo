# Déploiement d'Odoo saas~19.2

## Pourquoi pas Vercel

Vercel exécute des fonctions serverless : sans état, système de fichiers
éphémère, 250 Mo maximum par fonction, durée d'exécution plafonnée. Odoo est
un serveur Python monolithique de 1,3 Go qui exige un processus persistant
(threads cron, websockets), un filestore sur disque et une base PostgreSQL
qu'il administre lui-même. Aucune configuration ne rend ces deux modèles
compatibles.

Les cibles ci-dessous conservent le confort de Vercel — `git push` puis
déploiement automatique — avec un conteneur persistant.

---

## Prérequis

| Élément | État | Action |
|---|---|---|
| Docker | présent (29.6.1) | — |
| Dépôt Git | **absent** | `git init` requis avant Render/Railway |
| PostgreSQL local | absent | fourni par le conteneur `db` |

Render et Railway déploient **depuis un dépôt Git hébergé**. Ce dossier n'en
est pas un (`git rev-parse` → *not a git repository*). Voir
[Étape 2](#étape-2--publier-le-dépôt).

---

## Fichiers ajoutés

| Fichier | Rôle |
|---|---|
| `Dockerfile` | Image en deux étages : compilation des dépendances, puis runtime sans compilateur |
| `docker/entrypoint.sh` | Traduit `DATABASE_URL`, génère `odoo.conf`, initialise la base au premier démarrage |
| `docker-compose.yml` | Pile locale et VPS : Odoo + PostgreSQL + volumes |
| `render.yaml` | Blueprint Render : service web + base managée + disque persistant |
| `railway.json` | Configuration de build et health check Railway |
| `.env.example` | Modèle de configuration locale |
| `.dockerignore` | Exclut `.venv` (185 Mo), `.odoo_local_data`, `doc/`, `windows/` du contexte |
| `custom_addons/senodoo_app_upgrade/` | Rend fonctionnel le bouton « Mettre à niveau » des applications Enterprise |
| `custom_addons/senodoo_knowledge/` | Application Connaissances : base d'articles hiérarchique |
| `custom_addons/senodoo_social/` | Application Marketing social : rédaction, planification, publication |
| `custom_addons/senodoo_documents/` | Application Documents : espaces de travail, fichiers et liens |
| `docker/sync_custom_addons.py` | Détecte les modules maison dont la version a changé, pour les mettre à jour au démarrage |

---

## Étape 1 — Valider en local

```bash
cp .env.example .env
# éditer .env : remplacer les valeurs changeme_*
docker compose up --build
```

Durées mesurées sur cette machine (Apple Silicon) :

- **construction de l'image : ~10 minutes** (compilation de `psycopg2`,
  `python-ldap`, `libsass` ; image finale 2,59 Go) ;
- **initialisation de la base : ~35 secondes** — le module `base` et ses 13
  dépendances, soit 135 tables.

Les logs affichent `[entrypoint] initialisation terminee` quand c'est fini.

Ensuite : <http://localhost:8069> — connexion `admin` / `admin`, à changer
immédiatement.

Les démarrages suivants sont rapides — l'entrypoint détecte le schéma existant
et saute l'initialisation.

```bash
docker compose logs -f odoo     # suivre les logs
docker compose down             # arrêter (les volumes sont conservés)
docker compose down -v          # ⚠ supprime la base ET le filestore
```

---

## Étape 2 — Publier le dépôt

```bash
git init
git add .
git commit -m "Odoo saas~19.2 + configuration de déploiement conteneurisé"
git branch -M main
git remote add origin git@github.com:<compte>/<depot>.git
git push -u origin main
```

Le dépôt fait environ 1,1 Go une fois `.venv` et les données locales exclus.
GitHub avertit au-delà de 1 Go et refuse les fichiers de plus de 100 Mo ; le
code Odoo ne contient aucun fichier de cette taille, le push passe.

---

## Étape 3a — Render

1. Dashboard Render → **New** → **Blueprint** → sélectionner le dépôt.
2. Render lit `render.yaml` et crée trois ressources : la base `senodoo-db`, le
   disque `senodoo-filestore`, le service web `senodoo` — servi sur
   `https://senodoo.onrender.com` si le nom est encore libre.
3. Récupérer le mot de passe maître généré : service `senodoo` → onglet
   **Environment** → `ODOO_ADMIN_PASSWD`.

Points d'attention :

- **Premier déploiement long.** L'essentiel du temps est la construction de
  l'image (~10 min : compilation de `psycopg2`, `python-ldap`, `libsass`, plus
  1,1 Go de contexte). L'initialisation de la base qui suit est courte
  (~35 s mesurées) et se produit avant l'ouverture du port. Si Render conclut
  malgré tout à un échec de health check, relancez le déploiement : la seconde
  tentative trouve le schéma en place et démarre en quelques secondes.
- **Le disque est obligatoire.** Sans lui, chaque redéploiement efface les
  pièces jointes et les assets compilés.
- **Plans.** `standard` (2 Go de RAM) est le minimum réaliste : en dessous, le
  processus est tué pendant la compilation des assets web. Les noms de plans
  évoluent — vérifiez-les dans le dashboard avant le premier déploiement.

---

## Étape 3b — Railway

1. **New Project** → **Deploy from GitHub repo**.
2. Ajouter un service **PostgreSQL** au projet.
3. Sur le service Odoo, onglet **Variables** :

   ```
   DATABASE_URL      = ${{Postgres.DATABASE_URL}}
   ODOO_ADMIN_PASSWD = <mot de passe fort>
   ODOO_DATA_DIR     = /var/lib/odoo
   ODOO_WORKERS      = 0
   ODOO_PROXY_MODE   = True
   ODOO_LIST_DB      = False
   ODOO_DB_MAXCONN   = 16
   ```

4. Onglet **Settings** → **Volumes** → monter un volume sur `/var/lib/odoo`.

Railway injecte `PORT` automatiquement ; l'entrypoint le reprend.

Railway permet aussi de déployer sans dépôt Git distant :

```bash
npm i -g @railway/cli
railway login
railway link
railway up
```

---

## Étape 4 — Façade Vercel (optionnelle)

Vercel ne peut pas *héberger* Odoo (voir plus haut), mais il peut en être la
**façade publique** : votre domaine et le réseau edge Vercel devant l'origine
Odoo hébergée sur Render.

```
navigateur ──> Vercel (domaine, TLS, WAF) ──> Render (conteneur Odoo) ──> PostgreSQL
```

### Mise en place

La configuration vit dans [`vercel-facade/`](vercel-facade/) et **non à la
racine** : déployer depuis la racine ferait transférer 1,1 Go de code Odoo à
Vercel pour une configuration de 20 lignes, alors que la façade n'est qu'un
proxy sans build.

1. Déployer Odoo sur Render (étape 3a) et relever son URL, par exemple
   `https://senodoo.onrender.com`.
2. Remplacer le placeholder dans
   [`vercel-facade/vercel.json`](vercel-facade/vercel.json) :

   ```json
   "destination": "https://senodoo.onrender.com/:path*"
   ```

3. Déployer :

   ```bash
   cd vercel-facade
   vercel --prod
   ```
4. Dans Odoo : **Paramètres → Technique → Paramètres système**, régler
   `web.base.url` sur le domaine Vercel, sinon les liens des courriels et les
   URL absolues pointeront vers l'URL Render.
5. Laisser `ODOO_PROXY_MODE = True` sur Render : Odoo reconstruit les URL à
   partir des en-têtes `X-Forwarded-*` envoyés par Vercel.

### Pourquoi le cache est désactivé

`vercel.json` force `x-vercel-enable-rewrite-caching: 0`. Vercel met en cache
les réponses des rewrites externes par défaut ; sur une application
authentifiée comme Odoo, une page mise en cache pour un utilisateur serait
resservie à un autre — fuite de données entre sessions. **Ne retirez pas cet
en-tête.** Si vous voulez du cache sur les assets statiques, restreignez-le
explicitement à `/web/static/:path*`, jamais à `/:path*`.

### Limites à accepter

| Limite | Conséquence |
|---|---|
| Websockets non supportés par les rewrites | Le bus Odoo (`/websocket`) échoue : chat interne et notifications temps réel muets. L'ERP reste utilisable. |
| Corps de requête plafonné à 4,5 Mo | Les pièces jointes plus lourdes sont rejetées. |
| Tout le trafic transite par Vercel | La bande passante des assets Odoo est facturée par Vercel en plus de Render. |
| Un saut réseau supplémentaire | Latence accrue par rapport à un accès direct à Render. |

Si le temps réel vous importe, exposez Odoo directement via un domaine
personnalisé sur Render et n'utilisez pas cette façade.

---

## Choix techniques et raisons

**`http_interface = 0.0.0.0`** — le défaut d'Odoo est `127.0.0.1`
([odoo/tools/config.py:247](odoo/tools/config.py#L247)), ce qui rend le
conteneur injoignable de l'extérieur. C'est l'erreur la plus fréquente lors
d'une mise en conteneur d'Odoo.

**`workers = 0` (mode threadé)** — en mode prefork, le worker gevent écoute sur
un *second* port, `gevent_port`
([odoo/service/server.py:783](odoo/service/server.py#L783)). Render et Railway
n'exposent qu'un seul port : les websockets (notifications, chat, temps réel)
seraient cassés. En mode threadé, `ThreadedServer` sert HTTP et websocket sur
le même port. Sur un VPS où vous contrôlez le reverse proxy, vous pouvez passer
`ODOO_WORKERS` à 2 ou plus.

**Initialisation automatique de la base** — quand le schéma est absent, Odoo
refuse de démarrer et journalise *« Database not initialized, you can force it
with `-i base` »* ([odoo/modules/loading.py:372](odoo/modules/loading.py#L372)).
L'entrypoint détecte l'absence de la table `ir_module_module` et lance
`--init base --stop-after-init`. Aucun droit `CREATEDB` n'est nécessaire :
Odoo écrit dans la base vide déjà fournie par la plateforme, ce que les
utilisateurs PostgreSQL managés autorisent.

**`db_maxconn = 16`** — le défaut Odoo est 64. Les bases managées plafonnent
les connexions bien plus bas ; un pool trop large produit des erreurs
*too many connections* sous charge.

**wkhtmltopdf 0.12.6 « patched qt »** — la version des dépôts Debian génère des
en-têtes et pieds de page cassés dans les rapports PDF. Le `.deb` officiel de
`wkhtmltopdf/packaging` est installé explicitement.

**Image en deux étages** — `psycopg2` (2.9.9) et `python-ldap` (3.4.4) n'ont pas
de wheel manylinux et doivent être compilés. Les compiler dans un étage jeté
ensuite évite d'embarquer `build-essential` et les headers dans l'image finale.

---

## Exploitation

### Sécurité avant mise en production

- `ODOO_ADMIN_PASSWD` : indispensable. Le repli est `admin`, et l'entrypoint
  émet un avertissement dans les logs s'il n'est pas défini.
- `ODOO_LIST_DB = False` : déjà par défaut. Ferme
  `/web/database/manager`, qui permettrait sinon de créer et supprimer des
  bases depuis le web.
- Changer le mot de passe de l'utilisateur `admin` dès la première connexion.

### Mettre à jour des modules

Définir la variable puis redéployer ; l'entrypoint exécute la mise à jour avant
de démarrer le serveur :

```
ODOO_UPDATE_MODULES = base,web
```

Retirer la variable après le déploiement, sinon la mise à jour est rejouée à
chaque démarrage.

### Installer des modules

Contrairement à `ODOO_UPDATE_MODULES`, cette variable peut rester en place :
l'entrypoint interroge `ir_module_module` et ne relance Odoo que s'il reste
un module à installer.

```
ODOO_INSTALL_MODULES = senodoo_app_upgrade,senodoo_knowledge,senodoo_social,senodoo_documents
```

### Mise à jour automatique des modules maison

Au démarrage, `docker/sync_custom_addons.py` compare la version déclarée dans
chaque `custom_addons/*/__manifest__.py` à celle enregistrée en base, et
l'entrypoint met à jour ce qui a changé. **Il suffit donc d'incrémenter la
version du manifeste** après avoir modifié un module : plus besoin de toucher
à `ODOO_UPDATE_MODULES`.

Ce mécanisme n'installe jamais rien de lui-même — déposer un répertoire dans
`custom_addons/` ne doit pas ajouter une application à une base de production
sans décision explicite. Il journalise les modules disponibles non installés
et s'arrête là. Désactivable avec `ODOO_SYNC_CUSTOM_ADDONS=false`.

### Ajouter un dépôt d'addons

`addons_path` contient `addons/` puis `custom_addons/`. Pour en ajouter un
troisième — un volume monté, un dépôt tiers, les addons Odoo Enterprise si
vous disposez d'un abonnement :

```
ODOO_EXTRA_ADDONS_PATH = /mnt/enterprise
```

Au démarrage suivant, `update_list()` détecte les manifestes trouvés et
bascule automatiquement les fiches correspondantes de « Mettre à niveau »
vers le bouton « Activer » natif (voir
`custom_addons/senodoo_app_upgrade/README.md`).

### Console Odoo

```bash
docker compose run --rm odoo shell        # local
# Render : onglet Shell → /usr/local/bin/entrypoint.sh shell
```

### Sauvegardes

Deux éléments distincts, à sauvegarder **ensemble** :

```bash
# 1. la base
pg_dump "$DATABASE_URL" -Fc -f odoo-$(date +%F).dump

# 2. le filestore (pièces jointes) — absent du dump SQL
docker compose exec odoo tar czf - /var/lib/odoo/filestore > filestore-$(date +%F).tar.gz
```

Render sauvegarde automatiquement la base managée, mais **pas** le disque
persistant.

---

## Diagnostic

| Symptôme | Cause | Correctif |
|---|---|---|
| Health check en échec au 1er déploiement | Initialisation de la base plus longue que le délai imparti | Relancer le déploiement |
| `Database not initialized` | `ODOO_AUTO_INIT` mis à `false` | Le repasser à `true`, ou lancer `--init base` via le shell |
| Pièces jointes disparues après déploiement | Pas de disque monté sur `/var/lib/odoo` | Ajouter le volume persistant |
| Notifications temps réel muettes | `ODOO_WORKERS > 0` sur une plateforme mono-port | Repasser `ODOO_WORKERS` à `0` |
| `too many connections` | `db_maxconn` trop élevé pour le plan | Baisser `ODOO_DB_MAXCONN` |
| Liens et images en HTTP au lieu de HTTPS | `proxy_mode` désactivé | `ODOO_PROXY_MODE = True` |
| PDF sans en-tête ni pied de page | wkhtmltopdf non patché | Vérifier `wkhtmltopdf --version` → doit indiquer `(with patched qt)` |
