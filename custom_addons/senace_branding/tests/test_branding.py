"""Garde-fou contre le retour de la marque Odoo sur les surfaces visibles.

Une montee de version d'Odoo peut deplacer un noeud et faire echouer
silencieusement un xpath : la vue heritee est alors ignoree et la mention
revient sans que rien ne le signale. Ces tests rendent la panne bruyante.
"""
import re

import odoo.tests
from odoo.tests import tagged

MARQUE_EDITEUR = re.compile(r'[Oo]doo')


@tagged('post_install', '-at_install')
class TestBrandingRendu(odoo.tests.TransactionCase):
    """Verifie la sortie des templates, pas leur structure.

    Le controle porte sur le HTML rendu et non sur l'arbre des vues : deux des
    mentions vivent dans des `t-set` qui restent dans l'arbre combine alors
    que plus rien ne les affiche.
    """

    def _rendu(self, xmlid, valeurs=None):
        return str(self.env['ir.qweb']._render(xmlid, valeurs or {}))

    def test_pied_de_page_portail(self):
        html = self._rendu('portal.portal_record_sidebar',
                           {'title': '', 'entries': '', 'classes': ''})
        self.assertNotRegex(html, MARQUE_EDITEUR)

    def test_mention_de_marque(self):
        for xmlid in ('web.brand_promotion', 'web.brand_promotion_message'):
            html = self._rendu(xmlid, {'_message': '', '_utm_medium': 'portal'})
            self.assertNotRegex(html, MARQUE_EDITEUR, xmlid)

    def test_pied_de_page_des_emails(self):
        commun = {
            'message': self.env['mail.message'],
            'company': self.env.company,
            'show_footer': True,
            'show_unfollow': True,
            'record_name': 'Test',
            'subtitles': [],
        }
        for xmlid in ('mail.mail_notification_layout', 'mail.mail_notification_light'):
            html = self._rendu(xmlid, dict(commun, is_discussion=True))
            self.assertNotRegex(html, MARQUE_EDITEUR, xmlid)

    def test_reglages_en_base(self):
        parametres = self.env['ir.config_parameter'].sudo()
        self.assertEqual(parametres.get_str('web.web_app_name'), "SEN ACE")
        robot = self.env.ref('base.partner_root')
        self.assertNotRegex(robot.name, MARQUE_EDITEUR)
        self.assertNotRegex(robot.email or '', MARQUE_EDITEUR)
        self.assertFalse(self.env.ref('website.show_website_info').active)


@tagged('post_install', '-at_install')
class TestBrandingClientWeb(odoo.tests.HttpCase):
    """Le client web est la seule surface qu'aucune heritance de vue n'atteint."""

    def test_menu_utilisateur_et_titre(self):
        self.browser_js(
            "/odoo",
            """
            const { registry } = odoo.loader.modules.get("@web/core/registry");
            const entrees = registry.category("user_menuitems").getEntries().map((e) => e[0]);
            for (const interdit of ["odoo_account", "support"]) {
                if (entrees.includes(interdit)) {
                    throw new Error(`entree « ${interdit} » toujours dans le menu utilisateur`);
                }
            }
            if (document.title.includes("Odoo")) {
                throw new Error(`titre de l'onglet : ${document.title}`);
            }
            const { session } = odoo.loader.modules.get("@web/session");
            if (session.support_url !== undefined) {
                throw new Error(`support_url toujours publiee : ${session.support_url}`);
            }
            console.log("test successful");
            """,
            ready="odoo.isReady",
            login="admin",
        )
