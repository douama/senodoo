"""Tests du workflow d'activation des applications « Mettre a niveau ».

Contrainte du framework, assumee explicitement : Odoo interdit toute
operation de module reelle a l'interieur d'un test
(`_button_immediate_function` leve RuntimeError si
`odoo.modules.module.current_test` est vrai, ir_module.py). Les tests
couvrent donc integralement la logique de decision, de permission,
d'idempotence, d'erreur et de persistance, et verifient a la frontiere que
`button_immediate_install()` -- le mecanisme natif d'Odoo -- est appele avec
la bonne cible. L'installation elle-meme est celle d'Odoo, deja couverte en
amont par sa propre suite de tests.
"""
from unittest.mock import patch

from odoo.exceptions import AccessDenied, UserError
from odoo.modules.module import Manifest
from odoo.tests.common import TransactionCase, new_test_user

# Mesure sur une installation reelle : Odoo renvoie une redirection, pas
# un `reload`. Le mock doit dire la verite, sinon il valide du code mort.
INSTALL_ACTION = {'type': 'ir.actions.act_url', 'target': 'self', 'url': '/odoo'}
WIZARD_ACTION = {'type': 'ir.actions.act_window', 'res_model': 'res.config.settings'}


class TestSenodooAppUpgrade(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Module = cls.env['ir.module.module']
        # Applications Enterprise reelles, livrees sans code par
        # odoo/addons/base/data/ir_module_module.xml.
        cls.accountant = cls.env.ref('base.module_accountant')   # equivalent partiel
        cls.helpdesk = cls.env.ref('base.module_helpdesk')       # equivalent partiel
        cls.sign = cls.env.ref('base.module_sign')               # aucun equivalent

        # Determinisme : les assertions portent sur les equivalents encore
        # activables. Selon la base de test, `account` ou `project` peuvent
        # deja etre installes ; on repart d'un etat connu (annule par la
        # transaction de test).
        cls.env.ref('base.module_account').state = 'uninstalled'
        cls.env.ref('base.module_project').state = 'uninstalled'
        cls.env.ref('base.module_im_livechat').state = 'uninstalled'

    def _patched_install(self, side_effect=None, return_value=INSTALL_ACTION):
        """Intercepte le mecanisme natif a la frontiere."""
        return patch.object(
            type(self.Module),
            'button_immediate_install',
            autospec=True,
            side_effect=side_effect,
            **({} if side_effect else {'return_value': return_value}),
        )

    def _upgrade_failure_message(self, module):
        """Comme assertRaises, mais SANS le savepoint qu'Odoo pose autour.

        `BaseCase._raisesContext` (odoo/tests/common.py:519) ouvre un savepoint
        et l'annule des que l'exception attendue survient. Cela effacerait
        precisement l'ecriture dont ces tests doivent prouver la persistance.
        En production, `_senodoo_record_error` ecrit sur un curseur separe et
        survit de la meme facon au rollback reel.
        """
        try:
            module.action_senodoo_upgrade()
        except UserError as error:
            return str(error)
        self.fail(f"l'activation de {module.name} aurait du echouer")
        return ""

    # -- 1. detection dynamique ------------------------------------------
    def test_01_upgrade_required_detected_dynamically(self):
        """Les applications concernees sont trouvees par requete, pas par liste."""
        teasers = self.Module.search([('to_buy', '=', True)])
        self.assertTrue(teasers, "aucune fiche to_buy : le jeu de donnees a change")
        for module in teasers:
            self.assertFalse(
                Manifest.for_addon(module.name, display_warning=False),
                f"{module.name} a du code sur disque mais reste marque to_buy",
            )
            self.assertEqual(module.senodoo_status, 'upgrade_required')
            self.assertEqual(module.senodoo_upgrade_label, "Mettre a niveau")

    # -- 2. le clic declenche une vraie operation serveur -----------------
    def test_02_click_calls_native_install(self):
        with self._patched_install() as mocked:
            action = self.accountant.action_senodoo_upgrade()
        self.assertTrue(mocked.called, "aucun appel backend : le bouton serait decoratif")
        targets = mocked.call_args[0][0]
        self.assertEqual(targets.mapped('name'), ['account'])
        # Le succes doit etre annonce, puis la page rechargee.
        self.assertEqual(action['tag'], 'display_notification')
        self.assertEqual(action['params']['type'], 'success')
        self.assertEqual(action['params']['next'], INSTALL_ACTION,
                         "la navigation d'Odoo doit suivre le toast, pas etre perdue")

    # -- 3. etat de chargement -------------------------------------------
    def test_03_upgrading_status(self):
        self.accountant.sudo().state = 'to install'
        self.assertEqual(self.accountant.senodoo_status, 'upgrading')
        self.assertEqual(self.accountant.senodoo_upgrade_label, "Mise a niveau…")

    # -- 4/6/7. succes, statut final, effacement de l'echec ---------------
    def test_04_success_sets_active_and_clears_error(self):
        self.accountant.sudo().senodoo_upgrade_error = "echec precedent"
        self.assertEqual(self.accountant.senodoo_status, 'upgrade_failed')
        self.assertEqual(self.accountant.senodoo_upgrade_label, "Reessayer")

        def _succeed(records):
            records.sudo().state = 'installed'
            return INSTALL_ACTION

        with self._patched_install(side_effect=_succeed):
            self.accountant.action_senodoo_upgrade()

        self.assertFalse(self.accountant.senodoo_upgrade_error)
        self.assertEqual(self.env.ref('base.module_account').state, 'installed')

    # -- 8. persistance en base ------------------------------------------
    def test_05_error_is_persisted(self):
        self._upgrade_failure_message(self.sign)
        self.sign.invalidate_recordset()
        self.assertTrue(
            self.sign.senodoo_upgrade_error,
            "l'echec doit rester lisible apres coup, pas disparaitre",
        )
        self.assertEqual(self.sign.senodoo_status, 'upgrade_failed')

    # -- 9. echec backend -------------------------------------------------
    def test_06_backend_failure_restores_state(self):
        previous_state = self.accountant.state

        cause = "dependance manquante: account_edi"

        def _boom(records):
            raise ValueError(cause)

        with self._patched_install(side_effect=_boom):
            message = self._upgrade_failure_message(self.accountant)

        self.assertIn("Impossible de mettre a niveau", message)
        self.assertIn("dependance manquante", message, "la cause reelle doit etre remontee")
        self.accountant.invalidate_recordset()
        self.assertEqual(self.accountant.state, previous_state,
                         "l'application ne doit pas paraitre activee apres un echec")
        self.assertEqual(self.accountant.senodoo_status, 'upgrade_failed')

    # -- 10. retry --------------------------------------------------------
    def test_07_retry_after_failure_succeeds(self):
        self.accountant.sudo().senodoo_upgrade_error = "echec precedent"
        with self._patched_install() as mocked:
            self.accountant.action_senodoo_upgrade()
        self.assertTrue(mocked.called, "un echec ne doit pas bloquer les tentatives suivantes")
        self.assertFalse(self.accountant.senodoo_upgrade_error)

    # -- 11. double clic --------------------------------------------------
    def test_08_double_click_is_rejected(self):
        self.accountant.sudo().state = 'to install'
        with self._patched_install() as mocked:
            with self.assertRaises(UserError) as error:
                self.accountant.action_senodoo_upgrade()
        self.assertFalse(mocked.called, "une seconde operation ne doit pas demarrer")
        self.assertIn("deja en cours", str(error.exception))

    # -- 12. utilisateur sans permission ----------------------------------
    def test_09_non_admin_is_denied(self):
        user = new_test_user(self.env, login='senodoo_basic', groups='base.group_user')
        with self._patched_install() as mocked:
            with self.assertRaises(AccessDenied):
                self.accountant.with_user(user).action_senodoo_upgrade()
        self.assertFalse(mocked.called, "le frontend ne doit pas pouvoir forcer l'etat")

    # -- 13. dependance/equivalent manquant -------------------------------
    def test_10_missing_substitute_reports_precisely(self):
        message = self._upgrade_failure_message(self.sign)
        self.assertIn("OEEL-1", message, "la cause reelle -- licence Enterprise -- doit etre dite")
        self.assertIn(self.sign.shortdesc, message)

    # -- 14. application deja active --------------------------------------
    def test_11_already_installed_is_idempotent(self):
        self.accountant.sudo().state = 'installed'
        with self._patched_install() as mocked:
            action = self.accountant.action_senodoo_upgrade()
        self.assertFalse(mocked.called, "aucune reinstallation sur une app deja active")
        self.assertEqual(action['tag'], 'display_notification')
        self.assertEqual(action['params']['type'], 'info')
        self.assertEqual(self.accountant.senodoo_status, 'active')

    # -- 15. activations simultanees --------------------------------------
    def test_12_several_apps_resolve_independently(self):
        resolved = {
            module.name: module.senodoo_substitute_module_ids.mapped('name')
            for module in (self.accountant | self.helpdesk | self.sign)
        }
        self.assertEqual(resolved['accountant'], ['account'])
        self.assertEqual(resolved['helpdesk'], ['project', 'im_livechat'])
        self.assertEqual(resolved['sign'], [])

    # -- integrite des donnees de correspondance ---------------------------
    def test_13_declared_substitutes_exist_on_disk(self):
        for substitute in self.env['senodoo.app.substitute'].search([]):
            self.assertTrue(
                self.Module.search_count([('name', '=', substitute.name)]),
                f"{substitute.name} ne correspond a aucune fiche ir.module.module",
            )
            for name in substitute._substitute_name_list():
                self.assertTrue(
                    Manifest.for_addon(name, display_warning=False),
                    f"{substitute.name}: equivalent declare « {name} » absent de l'addons_path",
                )

    # -- le code present bascule sur le mecanisme natif --------------------
    def test_14_present_code_uses_native_update_list(self):
        """Si le module existe sur disque, on delegue a update_list + Activer."""
        with patch.object(type(self.Module), '_senodoo_code_present', return_value=True), \
             patch.object(type(self.Module), 'senodoo_refresh_catalog') as refresh, \
             self._patched_install() as mocked:
            self.accountant.sudo().state = 'uninstalled'
            self.accountant.action_senodoo_upgrade()
        self.assertTrue(refresh.called, "le catalogue doit etre resynchronise")
        self.assertEqual(mocked.call_args[0][0], self.accountant,
                         "c'est le module lui-meme qui doit etre installe, pas un equivalent")

    def test_17_configuration_wizard_is_not_swallowed(self):
        """Un module qui exige une configuration doit pouvoir l'afficher."""
        with self._patched_install(return_value=WIZARD_ACTION):
            action = self.accountant.action_senodoo_upgrade()
        self.assertEqual(action, WIZARD_ACTION,
                         "l'assistant est le retour attendu, ne pas le remplacer")

    # -- la carte reflete l'equivalent installe ----------------------------
    def test_16_installed_substitute_updates_the_card(self):
        """Une fois l'equivalent actif, la carte ne doit plus proposer d'agir."""
        self.env.ref('base.module_account').state = 'installed'
        self.env.invalidate_all()

        self.assertTrue(self.accountant.senodoo_substitute_installed)
        self.assertEqual(self.accountant.senodoo_status, 'active')
        self.assertFalse(self.accountant.senodoo_can_upgrade)
        # « Activee » serait mensonger : c'est account qui tourne, pas accountant.
        self.assertEqual(self.accountant.senodoo_upgrade_label, "Equivalent active")

        with self._patched_install() as mocked:
            action = self.accountant.action_senodoo_upgrade()
        self.assertFalse(mocked.called, "rien a reinstaller")
        self.assertEqual(action['params']['type'], 'info',
                         "un equivalent deja actif est un succes, pas une erreur")

    # -- non-regression sur les applications deja fonctionnelles -----------
    def test_15_existing_activate_button_is_untouched(self):
        arch = self.Module.get_view(
            view_id=self.env.ref('base.module_view_kanban').id, view_type='kanban',
        )['arch']
        self.assertIn('button_immediate_install', arch,
                      "le bouton « Activer » natif doit rester intact")
        self.assertIn('action_senodoo_upgrade', arch)
        self.assertNotIn('odoo.com/pricing', arch, "le lien mort doit avoir disparu")

        mrp = self.env.ref('base.module_mrp')
        self.assertFalse(mrp.to_buy)
        self.assertEqual(mrp.senodoo_status, 'available' if mrp.state == 'uninstalled' else 'active')
