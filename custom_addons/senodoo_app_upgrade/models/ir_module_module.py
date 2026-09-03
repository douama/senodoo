"""Workflow d'activation reel pour les applications marquees « Mettre a niveau ».

Rappel du mecanisme natif (odoo/addons/base/) :

* `data/ir_module_module.xml` cree 20 fiches SANS code, `to_buy = True`,
  `state = 'uninstallable'` (defaut du champ, models/ir_module.py).
* `views/ir_module_views.xml` : si `to_buy`, la carte affiche un `<a>` vers
  odoo.com/pricing ; sinon un bouton `button_immediate_install`.
* `update_list()` promeut automatiquement une fiche `uninstallable` en
  `uninstalled` des que son manifeste apparait sur l'addons_path.

Ce module n'ecrit aucun etat d'installation lui-meme : il valide, choisit
la cible, puis delegue a `button_immediate_install()`. Le verrou
anti-concurrence, la resolution des dependances, la persistance et le
rechargement du registre restent ceux d'Odoo.
"""
import logging

from odoo import _, api, fields, models, modules
from odoo.exceptions import UserError
from odoo.modules.module import Manifest

from odoo.addons.base.models.ir_module import assert_log_admin_access

_logger = logging.getLogger(__name__)

# Etats natifs signalant une operation de module deja en cours.
TRANSIENT_STATES = ('to install', 'to upgrade', 'to remove')


class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    # Persiste le dernier echec. Ecrit sur un curseur separe pour survivre
    # au rollback de la transaction fautive (cf. _senodoo_record_error).
    senodoo_upgrade_error = fields.Text(
        string="Dernier echec de mise a niveau",
        readonly=True,
        copy=False,
    )
    senodoo_status = fields.Selection(
        [
            ('available', "Disponible"),
            ('installed', "Installe"),
            ('active', "Active"),
            ('inactive', "Inactif"),
            ('upgrade_required', "Mise a niveau requise"),
            ('upgrading', "Mise a niveau en cours"),
            ('upgrade_failed', "Echec de mise a niveau"),
        ],
        string="Statut Senodoo",
        compute='_compute_senodoo_status',
        help="Vue unifiee du statut, derivee de `state` et `to_buy`. "
             "Odoo ne connait qu'un seul etat installe : il est expose ici "
             "sous « active », « installed » restant accepte comme alias "
             "pour les appels externes.",
    )
    senodoo_substitute_id = fields.Many2one(
        'senodoo.app.substitute',
        string="Correspondance open source",
        compute='_compute_senodoo_substitute',
    )
    senodoo_substitute_module_ids = fields.Many2many(
        'ir.module.module',
        string="Equivalents disponibles",
        compute='_compute_senodoo_substitute',
        help="Modules de remplacement dont le code est reellement present "
             "sur l'addons_path de cette installation.",
    )
    senodoo_can_upgrade = fields.Boolean(
        string="Mise a niveau possible",
        compute='_compute_senodoo_substitute',
        help="Faux lorsqu'aucun code installable n'existe : le bouton le dit "
             "au lieu de promettre une activation impossible.",
    )
    senodoo_substitute_installed = fields.Boolean(
        string="Equivalent deja actif",
        compute='_compute_senodoo_substitute',
        help="Vrai quand tous les equivalents disponibles sont installes : "
             "il n'y a plus rien a activer pour cette application.",
    )
    senodoo_menu_hint = fields.Char(
        string="Ou la trouver",
        compute='_compute_senodoo_menu_hint',
        help="Menus du sidebar apportes par les modules installes. Le module "
             "de remplacement arrive sous SON nom, pas sous celui de "
             "l'application Enterprise : sans cette indication, l'utilisateur "
             "ne sait pas ou cliquer apres une activation.",
    )
    senodoo_upgrade_label = fields.Char(
        string="Libelle du bouton",
        compute='_compute_senodoo_status',
    )

    # ------------------------------------------------------------------
    # Detection du code reellement present
    # ------------------------------------------------------------------
    @api.model
    def _senodoo_code_present(self, module_name):
        """Le manifeste du module est-il presente sur l'addons_path ?"""
        return bool(Manifest.for_addon(module_name, display_warning=False))

    # ------------------------------------------------------------------
    # Champs calcules
    # ------------------------------------------------------------------
    # `depends` ne peut pas exprimer « depend de l'etat d'AUTRES fiches
    # ir.module.module ». Ces champs sont donc volontairement non stockes :
    # ils sont recalcules a chaque requete, et une installation se termine
    # toujours par un rechargement de page (button_immediate_install renvoie
    # une action `reload`). La carte est donc a jour des son reaffichage.
    @api.depends('name')
    def _compute_senodoo_substitute(self):
        Substitute = self.env['senodoo.app.substitute'].sudo()
        mapping = {
            record.name: record
            for record in Substitute.search([('name', 'in', self.mapped('name'))])
        }
        for module in self:
            substitute = mapping.get(module.name)
            module.senodoo_substitute_id = substitute or False
            available = substitute._resolve_modules() if substitute else self.browse()
            module.senodoo_substitute_module_ids = available
            remaining = available.filtered(lambda m: m.state == 'uninstalled')
            module.senodoo_substitute_installed = bool(available) and not remaining
            module.senodoo_can_upgrade = bool(
                self._senodoo_code_present(module.name) or remaining,
            )

    @api.depends('state', 'to_buy', 'senodoo_upgrade_error',
                 'senodoo_substitute_installed', 'senodoo_can_upgrade',
                 'senodoo_substitute_module_ids')
    def _compute_senodoo_status(self):
        for module in self:
            state = module.state
            substituted = module.to_buy and module.senodoo_substitute_installed
            if state in ('to install', 'to upgrade'):
                status = 'upgrading'
            elif state == 'installed':
                status = 'active'
            elif state == 'to remove':
                status = 'inactive'
            elif module.to_buy and state in ('uninstallable', 'uninstalled'):
                # Plus rien a activer : l'equivalent disponible tourne deja.
                if substituted:
                    status = 'active'
                elif module.senodoo_upgrade_error:
                    status = 'upgrade_failed'
                else:
                    status = 'upgrade_required'
            elif state == 'uninstalled':
                status = 'available'
            else:
                status = 'inactive'
            module.senodoo_status = status

            # Le libelle doit dire si le clic fera quelque chose. « Mettre a
            # niveau » partout etait indistinguable de l'ancien lien mort :
            # rien ne separait les cartes qui installent vraiment un module de
            # celles qui ne peuvent rien faire.
            if status == 'upgrading':
                module.senodoo_upgrade_label = _("Mise a niveau…")
            elif status == 'upgrade_failed':
                module.senodoo_upgrade_label = _("Reessayer")
            elif substituted:
                # Dire « Activee » serait faux : c'est l'equivalent libre qui
                # tourne, pas l'application Enterprise elle-meme.
                module.senodoo_upgrade_label = _("Equivalent active")
            elif status == 'active':
                module.senodoo_upgrade_label = _("Activee")
            elif not module.to_buy:
                module.senodoo_upgrade_label = _("Mettre a niveau")
            elif not module.senodoo_can_upgrade:
                # Le clic reste actif : il explique precisement pourquoi.
                module.senodoo_upgrade_label = _("Non disponible")
            elif module.senodoo_substitute_module_ids:
                module.senodoo_upgrade_label = _("Activer l'equivalent")
            else:
                # Le code du module lui-meme est sur l'addons_path.
                module.senodoo_upgrade_label = _("Activer")

    @api.depends('senodoo_substitute_module_ids')
    def _compute_senodoo_menu_hint(self):
        Menu = self.env['ir.ui.menu'].sudo()
        Data = self.env['ir.model.data'].sudo()
        for module in self:
            installed = module.senodoo_substitute_module_ids.filtered(
                lambda m: m.state == 'installed',
            )
            names = []
            if installed:
                data = Data.search([
                    ('module', 'in', installed.mapped('name')),
                    ('model', '=', 'ir.ui.menu'),
                ])
                # Seules les racines interessent : ce sont elles qui
                # apparaissent dans le menu principal.
                roots = Menu.browse(data.mapped('res_id')).exists().filtered(
                    lambda menu: not menu.parent_id,
                )
                names = roots.mapped('name')
            module.senodoo_menu_hint = ', '.join(names)

    # ------------------------------------------------------------------
    # Persistance des erreurs (survit au rollback)
    # ------------------------------------------------------------------
    def _senodoo_record_error(self, message):
        """Ecrit l'echec sur un curseur dedie.

        La transaction courante est rollbackee quand l'installation echoue :
        un `write()` ordinaire disparaitrait avec elle et l'utilisateur
        verrait un echec sans trace. Un curseur separe garantit que le
        statut `upgrade_failed` est bien persiste en base.
        """
        self.ensure_one()
        if modules.module.current_test:
            # Sous test, un curseur separe committerait hors de la transaction
            # de test et casserait l'isolation. Odoo pose la meme garde dans
            # _button_immediate_function.
            self.sudo().senodoo_upgrade_error = message
            return
        try:
            with self.pool.cursor() as cr:
                cr.execute(
                    "UPDATE ir_module_module SET senodoo_upgrade_error = %s WHERE id = %s",
                    (message, self.id),
                )
        except Exception:  # noqa: BLE001 - la trace ne doit jamais masquer l'echec initial
            _logger.exception("senodoo: impossible de persister l'echec pour %s", self.name)

    def _senodoo_clear_error(self):
        self.ensure_one()
        if self.senodoo_upgrade_error:
            self.sudo().senodoo_upgrade_error = False

    # ------------------------------------------------------------------
    # Synchronisation dynamique du catalogue
    # ------------------------------------------------------------------
    @assert_log_admin_access
    @api.model
    def senodoo_refresh_catalog(self):
        """Reconcilie les fiches `to_buy` avec le contenu reel de l'addons_path.

        Aucune liste codee en dur : on interroge `to_buy`, puis on delegue a
        `update_list()`, qui promeut nativement toute fiche `uninstallable`
        dont le manifeste est desormais present (models/ir_module.py).
        """
        before = self.sudo().search([('to_buy', '=', True)])
        before_names = set(before.mapped('name'))

        self.update_list()

        still = self.sudo().search([('name', 'in', list(before_names)), ('to_buy', '=', True)])
        promoted = sorted(before_names - set(still.mapped('name')))
        if promoted:
            _logger.info("senodoo: modules devenus installables: %s", ', '.join(promoted))
        return {
            'checked': sorted(before_names),
            'promoted': promoted,
            'still_unavailable': sorted(still.mapped('name')),
        }

    @api.model
    def action_senodoo_refresh_catalog_ui(self):
        """Version interactive de la resynchronisation (action serveur)."""
        result = self.senodoo_refresh_catalog()
        if result['promoted']:
            return self._senodoo_notify(
                'success',
                _("%(count)s application(s) sont devenues installables : %(names)s",
                  count=len(result['promoted']), names=', '.join(result['promoted'])),
            )
        return self._senodoo_notify(
            'info',
            _("Catalogue a jour. %(count)s application(s) restent sans code "
              "sur l'addons_path : %(names)s",
              count=len(result['still_unavailable']),
              names=', '.join(result['still_unavailable']) or _("aucune")),
        )

    # ------------------------------------------------------------------
    # Workflow d'activation
    # ------------------------------------------------------------------
    @assert_log_admin_access
    def action_senodoo_upgrade(self):
        """Point d'entree du bouton « Mettre a niveau ».

        Ordre : permissions (decorateur) -> anti-double-clic -> idempotence
        -> existence du code -> cible -> installation Odoo -> notification.
        """
        self.ensure_one()

        # Anti-double-clic. Odoo pose ensuite un verrou exclusif sur
        # ir_module_module dans _button_immediate_function ; ce test rend
        # simplement le refus lisible au lieu d'un timeout SQL.
        if self.state in TRANSIENT_STATES:
            raise UserError(_(
                "Une operation est deja en cours sur « %(app)s ». "
                "Attendez la fin du traitement avant de recommencer.",
                app=self.shortdesc,
            ))

        # Idempotence : rejouer sur une application deja active ne casse rien.
        if self.state == 'installed':
            self._senodoo_clear_error()
            return self._senodoo_notify(
                'info',
                _("« %(app)s » est deja activee.", app=self.shortdesc),
            )

        # Le code du module lui-meme est-il apparu sur l'addons_path ?
        # (cas d'un ajout d'addons_path : Odoo sait alors tout faire seul)
        if self._senodoo_code_present(self.name):
            self.senodoo_refresh_catalog()
            self.invalidate_recordset()
            if self.state == 'uninstalled':
                return self._senodoo_install(self, self.shortdesc)

        # Equivalent deja en place : c'est un succes idempotent, pas un echec.
        if self.senodoo_substitute_installed:
            self._senodoo_clear_error()
            return self._senodoo_notify('info', self._senodoo_unavailable_message())

        targets = self.senodoo_substitute_module_ids.filtered(
            lambda module: module.state == 'uninstalled',
        )
        if not targets:
            message = self._senodoo_unavailable_message()
            self._senodoo_record_error(message)
            raise UserError(message)

        return self._senodoo_install(targets, self.shortdesc)

    def _senodoo_install(self, targets, app_label):
        """Delegue l'installation reelle a Odoo et traduit les echecs.

        `button_immediate_install()` fait tout le travail serieux : verrou
        exclusif, resolution recursive des dependances, ecriture de `state`
        en base, rechargement du registre, commit. On ne le double pas.
        """
        names = ', '.join(targets.mapped('shortdesc'))
        _logger.info(
            "senodoo: activation de « %s » via %s (uid=%s)",
            app_label, targets.mapped('name'), self.env.uid,
        )
        # Efface l'echec precedent AVANT le commit de l'installation, sinon
        # le statut resterait « upgrade_failed » apres un retry reussi.
        self._senodoo_clear_error()
        try:
            action = targets.button_immediate_install()
        except Exception as error:  # noqa: BLE001 - toute erreur doit etre remontee
            self._senodoo_abort_transaction()
            message = _(
                "Impossible de mettre a niveau %(app)s.\n\n"
                "Modules cibles : %(targets)s\n"
                "Cause : %(error)s\n\n"
                "Verifiez ses dependances ou les permissions necessaires.",
                app=app_label, targets=names, error=error,
            )
            self._senodoo_record_error(message)
            _logger.warning("senodoo: echec d'activation de %s: %s", app_label, error)
            raise UserError(message) from error

        success = _(
            "%(app)s a ete mise a niveau avec succes (%(targets)s).",
            app=app_label, targets=names,
        )
        # Odoo renvoie soit un assistant de configuration (`ir.actions.
        # act_window`), soit une simple navigation. Mesure faite sur une
        # installation reelle en saas~19.2, c'est le plus souvent
        # `{'type': 'ir.actions.act_url', 'url': '/odoo'}` -- jamais un
        # `reload`.
        #
        # Un assistant EST le retour visuel attendu : on le respecte tel quel,
        # l'ecraser casserait les modules qui exigent une configuration
        # post-installation. Une navigation nue, elle, ne dit rien a
        # l'utilisateur : on l'enchaine derriere le toast de succes.
        if isinstance(action, dict) and action.get('type') == 'ir.actions.act_window':
            return action
        return self._senodoo_notify('success', success, next_action=action or None)

    def _senodoo_abort_transaction(self):
        """Remet le curseur dans un etat utilisable apres un echec.

        PostgreSQL marque la transaction comme avortee des la premiere erreur
        SQL : sans ce rollback, construire le message d'erreur -- qui lit
        res.lang pour la traduction -- echouerait a son tour et masquerait la
        cause reelle.

        Sous test, `cr` est un TestCursor dont `rollback()` revient au
        savepoint du dernier commit, ce qui effacerait les donnees posees par
        setUpClass. Le framework de test annule deja la transaction lui-meme.
        """
        if not modules.module.current_test:
            self.env.cr.rollback()

    def _senodoo_unavailable_message(self):
        """Message d'echec precis : ce qui manque et pourquoi."""
        self.ensure_one()
        substitute = self.senodoo_substitute_id
        declared = substitute._substitute_name_list() if substitute else []
        already = self.senodoo_substitute_module_ids.filtered(
            lambda module: module.state == 'installed',
        )
        if already:
            return _(
                "« %(app)s » est une application Odoo Enterprise (licence "
                "OEEL-1) : son code n'est pas fourni en edition Community.\n\n"
                "Le meilleur equivalent disponible est deja installe : "
                "%(installed)s.",
                app=self.shortdesc, installed=', '.join(already.mapped('shortdesc')),
            )
        if declared:
            return _(
                "Impossible de mettre a niveau %(app)s.\n\n"
                "C'est une application Odoo Enterprise (licence OEEL-1) : son "
                "code n'est pas present sur l'addons_path. Les equivalents "
                "declares (%(declared)s) sont eux aussi introuvables.\n\n"
                "Ajoutez le module a l'addons_path, puis relancez.",
                app=self.shortdesc, declared=', '.join(declared),
            )
        note = substitute.note if substitute and substitute.note else _(
            "Aucun equivalent open source n'existe pour cette application "
            "dans cette version d'Odoo.",
        )
        return _(
            "Impossible de mettre a niveau %(app)s.\n\n"
            "C'est une application Odoo Enterprise (licence OEEL-1) : son code "
            "n'est pas fourni en edition Community et aucun equivalent libre "
            "n'est enregistre.\n\n%(note)s",
            app=self.shortdesc, note=note,
        )

    def _senodoo_notify(self, notification_type, message, next_action=None):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': notification_type,
                'title': _("Applications"),
                'message': message,
                'sticky': notification_type != 'success',
                'next': next_action or {'type': 'ir.actions.act_window_close'},
            },
        }
