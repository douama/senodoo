"""Sous-pages du menu principal, creees depuis l'editeur de site.

Le tour joue le parcours reel dans « Modifier le menu » : creation d'un
element range sous un parent avec « Sous-menu de », verification de la liste
deroulante sur le site, puis retour au premier niveau. Le test verifie ensuite
ce qui a ete enregistre en base.
"""
from odoo.tests import HttpCase, tagged


@tagged('post_install', '-at_install')
class TestSousMenus(HttpCase):
    # En 1366 px (taille par defaut des tours), le menu principal deborde :
    # Odoo replie les derniers elements sous « + », dont le parent cree par
    # le test. Le tour verifie les sous-menus, pas la largeur de l'en-tete.
    browser_size = '1920x1080'

    def test_sous_menu_depuis_la_fenetre(self):
        website = self.env.ref('website.default_website')
        Menu = self.env['website.menu']
        Menu.create({'name': "Parent test", 'url': '/#parent-test',
                     'parent_id': website.menu_id.id, 'website_id': website.id})

        self.start_tour(website.get_client_action_url('/'), 'senace_menu_parent', login='admin')

        sous_page = Menu.search([('name', '=', "Sous-page test"), ('website_id', '=', website.id)])
        self.assertEqual(len(sous_page), 1)
        self.assertEqual(sous_page.url, '/#sous-page-test')
        self.assertEqual(sous_page.parent_id, website.menu_id)
