# Installer Odoo saas~19.2 sur un PC Windows

Ce dépôt contient le code source d'Odoo saas~19.2. Le dossier [windows/](windows/)
ajoute un kit d'installation automatisé pour Windows : il installe Python,
PostgreSQL et wkhtmltopdf, prépare un environnement virtuel, crée le rôle de base
de données et génère un `odoo.conf` adapté à Windows.

---

## 1. En bref

1. Copiez le dossier du projet sur le PC Windows.
2. Double-cliquez sur **`windows\install-odoo.bat`** et acceptez l'invite UAC.
3. À la fin, double-cliquez sur **`windows\start-odoo.bat`**.

Le navigateur s'ouvre sur `http://localhost:8069`. Créez votre base avec le
**mot de passe maître** affiché en fin d'installation.

Comptez 15 à 30 minutes selon le débit de la connexion.

---

## 2. Prérequis

| Élément | Exigence | Vérification |
|---|---|---|
| Système | Windows 10 (build 1809+) ou Windows 11, **64 bits** | `winver` |
| Droits | Administrateur | le script demande l'élévation lui-même |
| `winget` | App Installer (Microsoft Store) | `winget --version` |
| Disque | ~4 Go (Python + PostgreSQL + dépendances + base) | |
| Mémoire | 4 Go minimum, 8 Go recommandés | |
| Réseau | Accès à PyPI, winget et nssm.cc | |

Sans `winget`, l'installation automatique des logiciels tiers est impossible :
voir [Installation manuelle des logiciels tiers](#9-installation-manuelle-des-logiciels-tiers).

---

## 3. Installation

### En un double-clic

Faites un double-clic sur `windows\install-odoo.bat`. Le script PowerShell
demande de lui-même l'élévation des privilèges et poursuit dans une console
administrateur.

### En ligne de commande

```powershell
cd "C:\chemin\vers\odoo saas"
.\windows\Install-Odoo.ps1
```

### Vérifier avant d'installer

```powershell
.\windows\Install-Odoo.ps1 -CheckOnly     # ou : windows\check-odoo.bat
```

Le mode diagnostic n'installe rien et ne modifie rien : il se contente de
signaler ce qui est présent et ce qui manque.

### Options

| Option | Défaut | Rôle |
|---|---|---|
| `-DbName` | `odoo_saas19` | Nom de la base par défaut |
| `-DbUser` | `odoo` | Rôle PostgreSQL applicatif |
| `-DbPassword` | *(généré)* | Mot de passe du rôle |
| `-DbHost` / `-DbPort` | `localhost` / `5432` | Serveur PostgreSQL |
| `-HttpPort` | `8069` | Port HTTP d'Odoo |
| `-MasterPassword` | *(généré)* | Mot de passe maître (`admin_passwd`) |
| `-PostgresSuperPassword` | *(généré ou demandé)* | Mot de passe du superutilisateur `postgres` |
| `-PostgresVersion` | `17` | Version de PostgreSQL à installer (`16`, `17` ou `18`) |
| `-ListenOnAllInterfaces` | *(absent)* | Rend Odoo accessible depuis le réseau local |
| `-SkipPostgres` | *(absent)* | N'installe pas PostgreSQL (serveur déjà en place) |
| `-SkipWkhtmltopdf` | *(absent)* | N'installe pas wkhtmltopdf |
| `-Force` | *(absent)* | Recrée l'environnement virtuel |
| `-CheckOnly` | *(absent)* | Diagnostic seul |
| `-NoElevate` | *(absent)* | N'essaie pas d'élever les privilèges |

Exemple :

```powershell
.\windows\Install-Odoo.ps1 -DbName odoo_prod -HttpPort 8080 -PostgresVersion 16
```

### Ce que fait le script

| Étape | Action |
|---|---|
| 1 | Vérifie Windows 64 bits, les droits administrateur, `winget`, et la limite `MAX_PATH` |
| 2 | Installe **Python 3.12** s'il est absent (`winget install Python.Python.3.12`) |
| 3 | Installe **PostgreSQL** s'il est absent, avec un mot de passe superutilisateur généré |
| 4 | Installe **wkhtmltopdf** et l'ajoute au `PATH` machine |
| 5 | Crée `.venv-win\` et installe `requirements.txt` |
| 6 | Crée le rôle PostgreSQL `odoo` (`LOGIN`, `CREATEDB`) |
| 7 | Génère `odoo.conf` à la racine, avec des permissions restreintes |
| 8 | Vérifie : `odoo-bin --version`, imports Python, connexion SQL réelle |

Le script est **idempotent** : le relancer ne casse rien. Un `odoo.conf`
existant est sauvegardé sous `odoo.conf.bak-<horodatage>` avant d'être réécrit.

### Fichiers créés

```
odoo saas\
├── odoo.conf                  ← généré (contient des mots de passe)
├── .venv-win\                 ← environnement virtuel Windows
├── .odoo_local_data\          ← filestore, sessions, addons téléchargés
└── windows\
    ├── logs\                  ← odoo.log et journaux du service
    └── tools\nssm\            ← NSSM, si le service est installé
```

`.venv-win` est volontairement distinct de `.venv` : le dossier du projet peut
ainsi être partagé entre macOS/Linux et Windows sans que les deux environnements
virtuels se marchent dessus.

---

## 4. Premier démarrage

```powershell
.\windows\Start-Odoo.ps1 -Open
```

ou double-clic sur `windows\start-odoo.bat`.

Le premier démarrage est long : Odoo construit son registre et compile les
assets. Une fois la page ouverte :

1. Renseignez le **mot de passe maître** affiché en fin d'installation.
2. Choisissez le nom de la base, la langue, le pays.
3. Cochez « Charger les données de démonstration » pour un environnement d'essai.

Le mot de passe maître se retrouve dans `odoo.conf`, clé `admin_passwd`.

---

## 5. Utilisation quotidienne

| Besoin | Commande |
|---|---|
| Démarrer | `.\windows\Start-Odoo.ps1` |
| Démarrer et ouvrir le navigateur | `.\windows\Start-Odoo.ps1 -Open` |
| Arrêter | `Ctrl+C` dans la console |
| Mettre à jour un module | `.\windows\Start-Odoo.ps1 -- -u sale -d odoo_saas19` |
| Installer un module | `.\windows\Start-Odoo.ps1 -- -i crm -d odoo_saas19` |
| Mode développeur | `.\windows\Start-Odoo.ps1 -- --dev=xml,reload` |
| Console Python d'Odoo | `.\windows\Start-Odoo.ps1 -- shell -d odoo_saas19` |
| Suivre le journal | `Get-Content windows\logs\odoo.log -Wait -Tail 50` |

Tout ce qui suit `--` est transmis tel quel à `odoo-bin`.

Pour utiliser directement l'environnement virtuel :

```powershell
.\.venv-win\Scripts\Activate.ps1
python odoo-bin -c odoo.conf --help
```

---

## 6. Exécuter Odoo en service Windows

Odoo démarre alors automatiquement avec la machine, sans session ouverte.

```powershell
.\windows\Install-Service.ps1                       # installe et démarre
.\windows\Install-Service.ps1 -StartupType Manual   # démarrage manuel
.\windows\Install-Service.ps1 -Remove               # supprime le service
```

Le service s'appuie sur **NSSM**, l'outil qu'utilise l'installeur officiel
d'Odoo pour Windows. Il est installé via `winget` ou, à défaut, téléchargé
depuis `nssm.cc` dans `windows\tools\nssm`.

| Propriété | Valeur |
|---|---|
| Nom | `odoo-server-saas-19.2` (valeur de `odoo.release.nt_service_name`) |
| Dépendance | le service PostgreSQL détecté |
| Redémarrage | automatique, temporisé à 10 s après un arrêt imprévu |
| Journaux | `windows\logs\service-stdout.log` et `service-stderr.log`, rotation à 16 Mio |

Le nom du service n'est pas arbitraire : lorsqu'Odoo doit se relancer après la
mise à jour d'un module, [`odoo/service/server.py`](odoo/service/server.py#L1611)
exécute `net stop <nt_service_name> && net start <nt_service_name>`. Un service
nommé autrement empêcherait ce redémarrage automatique.

Gestion courante :

```powershell
Get-Service 'odoo-server-saas-19.2'
Restart-Service 'odoo-server-saas-19.2'
Stop-Service 'odoo-server-saas-19.2'
```

---

## 7. Le fichier `odoo.conf`

Généré à la racine du projet. Odoo le trouve automatiquement : sous Windows,
la configuration par défaut est cherchée à côté d'`odoo-bin`
([`odoo/tools/config.py`](odoo/tools/config.py#L514)).

| Clé | Rôle |
|---|---|
| `addons_path` | Dossiers de modules, en **chemins absolus** (un service ne partage pas le répertoire courant) |
| `data_dir` | Filestore, sessions et modules téléchargés |
| `db_host`, `db_port`, `db_user`, `db_password` | Connexion PostgreSQL |
| `db_name` | Base utilisée par défaut |
| `http_port` | Port d'écoute (8069) |
| `http_interface` | `127.0.0.1` par défaut : accessible depuis ce PC uniquement |
| `admin_passwd` | Mot de passe maître du gestionnaire de bases |
| `list_db` | `True` : le gestionnaire de bases est accessible |
| `logfile`, `log_level` | Journalisation |
| `limit_time_real` | Durée maximale d'une requête (1200 s) |

Après toute modification, redémarrez Odoo (ou le service).

### Options POSIX absentes — et c'est normal

`workers`, `gevent_workers`, `limit_time_cpu`, `limit_memory_soft`,
`limit_memory_hard` et `limit_request` sont déclarées comme `PosixOnlyOption`
dans [`odoo/tools/config.py`](odoo/tools/config.py#L453-L494). Sous Windows,
Odoo les **ignore silencieusement**. Les ajouter au fichier ne produirait aucun
effet ; elles en sont donc volontairement absentes.

### Ouvrir l'accès au réseau local

Réinstallez avec `-ListenOnAllInterfaces`, ou remplacez dans `odoo.conf` :

```ini
http_interface = 0.0.0.0
```

puis autorisez le port dans le pare-feu :

```powershell
New-NetFirewallRule -DisplayName "Odoo 8069" -Direction Inbound `
    -Protocol TCP -LocalPort 8069 -Action Allow
```

N'exposez pas un serveur ainsi ouvert à Internet sans reverse proxy HTTPS et
sans passer `list_db` à `False`.

---

## 8. Particularités d'Odoo sous Windows

**Mode multi-thread uniquement.** `workers` valant toujours 0, Odoo utilise
`ThreadedServer` ([`server.py`](odoo/service/server.py#L1738)) et non le mode
prefork multi-processus disponible sous Linux. Conséquence pratique : les
requêtes concurrentes se partagent un seul processus Python, donc un seul cœur
pour le code Python. C'est parfaitement adapté au développement et à un usage à
quelques utilisateurs ; pour une production chargée, préférez Linux (ou WSL 2).

**Pas de `gevent`.** `requirements.txt` exclut `gevent` et `greenlet` sous
Windows (marqueur `sys_platform != 'win32'`). Le bus temps réel (discussion,
notifications, live chat) fonctionne, servi par le serveur multi-thread, mais
chaque connexion longue mobilise un thread.

**Python 3.12 imposé.** Odoo exige Python ≥ 3.12
([`release.py`](odoo/release.py)). Le script verrouille la série 3.12 plutôt
qu'une version plus récente pour une raison concrète : sous Windows,
`requirements.txt` épingle `rl-renderPM==4.0.3`, qui ne publie aucune roue
cp313+ et n'a aucun repli en Python pur. En 3.13, son installation exigerait
Visual Studio Build Tools. En 3.12, tous les paquets s'installent sans
compilateur : `ofxparse`, `vobject` et `rjsmin` sont bien fournis en archive
source, mais les deux premiers sont en Python pur et `rjsmin` bascule
automatiquement sur son implémentation Python si le compilateur manque.

**Modules exclus sous Windows.** `python-ldap` (authentification LDAP) et
`python-magic` (détection de type MIME) ne sont pas installés : les
fonctionnalités correspondantes sont indisponibles.

**wkhtmltopdf.** Odoo attend la version **0.12.6** compilée avec un Qt modifié.
Les autres versions rendent mal les en-têtes et pieds de page. Sans
wkhtmltopdf, Odoo démarre mais rend les rapports en HTML.

**Antivirus.** Microsoft Defender analyse chaque fichier lu. Avec plus de
45 000 fichiers dans `addons\`, cela ralentit sensiblement le démarrage.
Exclure le dossier du projet et `.venv-win` accélère nettement les choses :

```powershell
Add-MpPreference -ExclusionPath "C:\chemin\vers\odoo saas"
```

---

## 9. Installation manuelle des logiciels tiers

Si `winget` est indisponible, installez ces trois logiciels puis relancez
`Install-Odoo.ps1` (il détectera ce qui est déjà présent) :

| Logiciel | Source | Remarque |
|---|---|---|
| Python 3.12 (64 bits) | <https://www.python.org/downloads/windows/> | Cocher « Add python.exe to PATH » |
| PostgreSQL 16+ | <https://www.postgresql.org/download/windows/> | Noter le mot de passe `postgres` |
| wkhtmltopdf 0.12.6 | <https://wkhtmltopdf.org/downloads.html> | Version « with patched qt » |

Puis :

```powershell
.\windows\Install-Odoo.ps1 -PostgresSuperPassword 'le-mot-de-passe-choisi'
```

---

## 10. Dépannage

### « Impossible de charger le fichier … Install-Odoo.ps1 »

La stratégie d'exécution PowerShell bloque les scripts. Les fichiers `.bat`
fournis contournent le problème (`-ExecutionPolicy Bypass`). En ligne de
commande :

```powershell
powershell -ExecutionPolicy Bypass -File .\windows\Install-Odoo.ps1
```

### « python n'est pas reconnu » après l'installation de Python

`winget` modifie le `PATH` du système, pas celui des consoles déjà ouvertes.
Fermez puis rouvrez PowerShell et relancez le script.

### « Microsoft Visual C++ 14.0 or greater is required »

Un Python autre que 3.12 est utilisé. Vérifiez :

```powershell
.\.venv-win\Scripts\python.exe --version
```

Si ce n'est pas une 3.12, recréez l'environnement : `.\windows\Install-Odoo.ps1 -Force`.

### `ImportError: DLL load failed while importing win32api`

Les DLL de `pywin32` ne sont pas enregistrées. Odoo en a besoin sous Windows
([`server.py`](odoo/service/server.py#L651-L653)). Le script tente la réparation
automatiquement ; manuellement :

```powershell
.\.venv-win\Scripts\python.exe -m pip install --force-reinstall pywin32
.\.venv-win\Scripts\python.exe .\.venv-win\Scripts\pywin32_postinstall.py -install
```

### `psql: FATAL: password authentication failed for user "postgres"`

Le mot de passe superutilisateur fourni est incorrect. Il a été défini lors de
l'installation de PostgreSQL. En cas d'oubli, réinitialisez-le en passant
temporairement `pg_hba.conf` à la méthode `trust`
(`C:\Program Files\PostgreSQL\<version>\data\pg_hba.conf`), puis redémarrez le
service PostgreSQL.

### `FATAL: database "odoo_saas19" does not exist`

La base n'est pas encore créée. Ouvrez `http://localhost:8069/web/database/manager`
et créez-la avec le mot de passe maître.

### Le port 8069 est déjà utilisé

```powershell
Get-NetTCPConnection -LocalPort 8069 | Select-Object OwningProcess
Get-Process -Id <PID>
```

Arrêtez le processus concerné, ou changez `http_port` dans `odoo.conf`.

### Fichier introuvable pendant l'installation, chemin très long

La limite `MAX_PATH` de 260 caractères est atteinte. Le script active le support
des chemins longs quand la marge est insuffisante, mais cela ne prend effet que
pour les processus lancés ensuite : redémarrez Windows et relancez. Sinon,
déplacez le projet vers un chemin court, par exemple `C:\odoo`.

### Le service ne démarre pas

```powershell
Get-Content windows\logs\service-stderr.log -Tail 50
```

Vérifiez d'abord qu'Odoo démarre en console (`.\windows\Start-Odoo.ps1`) : le
service ne fera pas mieux.

### Les rapports PDF sortent en HTML

`wkhtmltopdf` est introuvable dans le `PATH`. Vérifiez avec `wkhtmltopdf --version`,
puis relancez `.\windows\Install-Odoo.ps1` ou installez-le manuellement.

---

## 11. Sécurité

- **`odoo.conf` contient le mot de passe de la base et le mot de passe maître en
  clair.** Odoo l'exige. Le script restreint l'accès du fichier à votre compte,
  aux administrateurs et à `SYSTEM`. Le fichier est déjà couvert par
  `.gitignore` : ne le versionnez pas.
- `http_interface` vaut `127.0.0.1` par défaut : le serveur n'est joignable que
  depuis ce PC.
- En production, passez `list_db = False` pour masquer le gestionnaire de bases,
  et placez un reverse proxy HTTPS devant Odoo.
- Les mots de passe générés font 24 caractères alphanumériques. Notez-les à la
  fin de l'installation : ils ne sont plus réaffichés ensuite.

---

## 12. Désinstallation

```powershell
# 1. Supprimer le service, s'il a été installé
.\windows\Install-Service.ps1 -Remove

# 2. Supprimer l'environnement virtuel, les données et la configuration
Remove-Item .venv-win, .odoo_local_data, odoo.conf, windows\logs, windows\tools -Recurse -Force

# 3. Supprimer la base et le rôle (adapter la version de PostgreSQL)
& "$env:ProgramFiles\PostgreSQL\17\bin\psql.exe" -U postgres -c "DROP DATABASE IF EXISTS odoo_saas19;"
& "$env:ProgramFiles\PostgreSQL\17\bin\psql.exe" -U postgres -c "DROP ROLE IF EXISTS odoo;"

# 4. Désinstaller les logiciels tiers, si vous n'en avez plus l'usage
winget uninstall --id PostgreSQL.PostgreSQL.17
winget uninstall --id wkhtmltopdf.wkhtmltopdf
winget uninstall --id Python.Python.3.12
```
