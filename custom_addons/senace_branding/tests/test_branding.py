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

    def test_courriels_dans_toutes_les_langues(self):
        """Ces champs sont traduisibles : une seule langue propre ne suffit pas.

        C'est le piege de cette reprise. Odoo stocke `subject` et `body_html`
        en jsonb, une entree par langue ; une ecriture faite en anglais laisse
        « Odoo » intact dans la version francaise, qui est justement celle que
        recoivent les destinataires.
        """
        langues = self.env['res.lang'].sudo().search([]).mapped('code')
        self.assertTrue(langues)
        for xmlid in ('auth_signup.set_password_email',
                      'auth_totp_mail.mail_template_totp_invite'):
            modele = self.env.ref(xmlid, raise_if_not_found=False)
            if not modele:
                continue
            for langue in langues:
                traduit = modele.with_context(lang=langue)
                for champ in ('subject', 'body_html'):
                    self.assertNotRegex(str(traduit[champ] or ''), MARQUE_EDITEUR,
                                        f"{xmlid}.{champ} en {langue}")

    def test_resume_periodique(self):
        """Les trois blocs de marque du resume sont retires de l'arbre."""
        arch = str(self.env.ref('digest.digest_mail_main')._get_combined_arch())
        for bloc in ('by_odoo', 'id="powered"', 'digest_section_mobile'):
            self.assertNotIn(bloc, arch, bloc)

    def test_fiches_de_modules_et_libelles(self):
        Modules = self.env['ir.module.module'].sudo()
        sales = Modules.search(['|', ('shortdesc', 'ilike', 'odoo'),
                                ('summary', 'ilike', 'odoo')])
        self.assertFalse(sales, sales.mapped('name'))
        champs = self.env['ir.model.fields'].sudo().search(
            [('field_description', 'ilike', 'odoo')])
        self.assertFalse(champs, champs.mapped('name'))


@tagged('post_install', '-at_install')
class TestBrandingManifeste(odoo.tests.HttpCase):
    """L'application installable : nom, couleurs et icone d'ecran d'accueil."""

    def test_manifeste_pwa(self):
        manifeste = self.url_open('/web/manifest.webmanifest').json()
        self.assertEqual(manifeste['name'], "SEN ACE")
        self.assertEqual(manifeste['theme_color'], '#0a4da3')
        self.assertEqual(manifeste['background_color'], '#0a4da3')
        for icone in manifeste['icons']:
            self.assertIn('senace_branding', icone['src'])
            self.assertEqual(self.url_open(icone['src']).status_code, 200)


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
