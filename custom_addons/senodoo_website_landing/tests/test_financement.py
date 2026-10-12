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
