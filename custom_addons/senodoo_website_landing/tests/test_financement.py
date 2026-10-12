"""Page « Financer sa formation » : publiee, dans le menu, reliee au CRM."""
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestFinancement(HttpCase):

    def test_page_publique(self):
        reponse = self.url_open('/financer-sa-formation')
        self.assertEqual(reponse.status_code, 200)
        self.assertIn("Financer sa formation", reponse.text)
        # L'objet pre-rempli devient le titre de la piste dans le CRM.
        self.assertIn('/contactus?subject=Financement de formation', reponse.text)

    def test_entree_du_menu_principal(self):
        website = self.env.ref('website.default_website')
        menu = self.env['website.menu'].search([
            ('url', '=', '/financer-sa-formation'),
            ('website_id', '=', website.id),
        ])
        self.assertEqual(len(menu), 1)
        self.assertEqual(menu.parent_id, website.menu_id)

    def test_doublon_cree_depuis_l_editeur(self):
        """Cas de la production : une page non publiee, propre au site, sur la
        meme URL passait devant celle du module et renvoyait une 404."""
        website = self.env.ref('website.default_website')
        resultat = website.with_context(website_id=website.id).new_page(name="Brouillon financement")
        brouillon = self.env['website.page'].browse(resultat['page_id'])
        brouillon.write({'url': '/financer-sa-formation', 'is_published': False})
        self.env.registry.clear_cache('templates')
        self.assertEqual(self.url_open('/financer-sa-formation').status_code, 404)

        self.env['senodoo.website.branding'].release_page_url(
            'senodoo_website_landing.financer_formation_page')

        self.assertEqual(brouillon.url, '/financer-sa-formation-brouillon')
        self.assertEqual(self.url_open('/financer-sa-formation').status_code, 200)
