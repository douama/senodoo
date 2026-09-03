# senodoo_app_upgrade

Rend fonctionnel le bouton turquoise **« Mettre à niveau »** de l'écran *Apps*.

## Le problème

En édition Community, `odoo/addons/base/data/ir_module_module.xml` crée
**20 fiches `ir.module.module` sans code** :

```xml
<record model="ir.module.module" id="base.module_helpdesk">
    <field name="name">helpdesk</field>
    <field name="license">OEEL-1</field>   <!-- Odoo Enterprise Edition License -->
    <field name="to_buy" eval="True"/>
</record>
```

Aucun répertoire `addons/helpdesk/` n'existe. La fiche hérite du défaut
`state = 'uninstallable'` (`odoo/addons/base/models/ir_module.py:307`), et la
vue kanban affiche pour elle **un lien HTML, pas un bouton** :

```xml
<!-- odoo/addons/base/views/ir_module_views.xml:186 -->
<a href="https://odoo.com/pricing?...">Upgrade</a>
```

Cliquer n'appelait donc aucun serveur : c'est un appel à souscrire un
abonnement Odoo Enterprise.

## Ce que fait ce module

Le lien mort devient un vrai bouton serveur `action_senodoo_upgrade` :

1. **Permissions** — décorateur `assert_log_admin_access` d'Odoo : refus et
   journalisation pour tout non-administrateur. Le frontend ne peut pas
   forcer l'état.
2. **Anti-double-clic** — refus explicite si `state` est déjà transitoire ;
   Odoo pose ensuite son propre `LOCK ir_module_module IN EXCLUSIVE MODE`.
3. **Idempotence** — une application déjà installée renvoie une notification,
   sans réinstallation.
4. **Détection dynamique** — le code du module est-il réellement sur
   l'`addons_path` (`Manifest.for_addon`) ? Si oui, `update_list()` promeut
   nativement la fiche en `uninstalled` et l'installation normale démarre.
5. **Équivalent open source** — sinon, installation du meilleur module
   Community disponible, via `button_immediate_install()` : résolution
   récursive des dépendances, écriture en base, rechargement du registre.
6. **Échec explicite** — aucun équivalent ? Message précis nommant la licence
   OEEL-1 et ce qui manque, persisté en base, jamais silencieux.

## Décisions de conception

**Aucun système parallèle.** Le module ne réimplémente ni verrou, ni
résolution de dépendances, ni persistance : tout cela existe déjà dans
`_button_immediate_function`. Il valide, choisit la cible, délègue.

**Aucune liste codée en dur.** Les applications concernées sont trouvées par
requête sur `to_buy`. La table de correspondance
(`senodoo.app.substitute`) est une **donnée** éditable dans
*Paramètres > Technique > Équivalents open source*, pas du code.

**Un nom déclaré mais absent de l'`addons_path` est ignoré**
(`_resolve_modules`) : la table décrit une intention, le disque décrit la
réalité, et la réalité gagne.

**Persistance des échecs sur un curseur dédié.** Quand une installation
échoue, la transaction est annulée — un `write()` ordinaire disparaîtrait
avec elle. `_senodoo_record_error` ouvre un curseur séparé pour que le statut
`upgrade_failed` survive.

**Statuts.** `senodoo_status` expose le vocabulaire demandé
(`available`, `active`, `inactive`, `upgrade_required`, `upgrading`,
`upgrade_failed`) en le dérivant de `state` et `to_buy`. Odoo ne connaît
**qu'un seul** état installé : il est exposé sous `active`, `installed`
restant accepté comme alias pour les appels externes. L'état `upgrading`
n'est pas un drapeau maison mais les états natifs `to install` / `to upgrade`,
que `button_reset_state()` sait déjà débloquer si un processus meurt.

## Libellés du bouton

Le bouton garde son apparence turquoise d'origine, mais son texte annonce ce
que le clic va faire — sans quoi une carte utile est indistinguable d'une
carte sans issue :

| Libellé | Signification |
|---|---|
| **Activer l'équivalent** | Un module Community va réellement s'installer |
| **Activer** | Le code du module lui-même est sur l'`addons_path` |
| **Non disponible** | Aucune cible installable ; le clic explique pourquoi |
| **Mise à niveau…** | Opération en cours (états natifs `to install` / `to upgrade`) |
| **Réessayer** | Échec précédent, persisté en base |
| **Équivalent activé** | Terminé. Pas « Activée » : c'est le module libre qui tourne |

## Ce que le module ne fait pas

Il **ne fournit pas** les applications Enterprise. Leur code est propriétaire
(licence OEEL-1) et absent du dépôt. Sur les 20 fiches :

- **7** ont un équivalent Community partiel réellement installable ;
- **13** n'en ont aucun — le module le dit précisément au lieu d'afficher une
  application faussement « activée ».

Si vous disposez d'un abonnement Enterprise, montez ses addons et pointez
`ODOO_EXTRA_ADDONS_PATH` dessus : `update_list()` bascule alors les 20 fiches
en « Activer » natif, sans rien changer à ce module.

## Tests

```bash
odoo-bin -d <base> --addons-path=addons,custom_addons \
         -i senodoo_app_upgrade --test-enable \
         --test-tags=/senodoo_app_upgrade --stop-after-init
```

Odoo **interdit les opérations de module réelles dans un test**
(`_button_immediate_function` lève `RuntimeError` si
`odoo.modules.module.current_test`). Les tests couvrent donc intégralement la
décision, les permissions, l'idempotence, les erreurs et la persistance, et
vérifient à la frontière que `button_immediate_install()` est appelé avec la
bonne cible. L'installation elle-même est celle d'Odoo, déjà couverte par sa
propre suite.
