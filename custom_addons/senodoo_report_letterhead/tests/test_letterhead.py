"""Le papier a en-tete doit sortir dans le document, pas seulement en base.

Les controles portent sur le HTML rendu, et plus precisement sur les blocs
`div.header` et `div.footer` : ce sont eux que l'impression PDF detache du
corps et repete sur chaque page (ir.actions.report._prepare_html). Une image
posee ailleurs n'apparaitrait que sur la premiere page.
"""
import base64
import io

from lxml import html as lxml_html
from PIL import Image

from odoo.tests import TransactionCase, tagged

CLASSE = "//div[contains(concat(' ', normalize-space(@class), ' '), ' {} ')]"


def _png(couleur, taille=(600, 80)):
    tampon = io.BytesIO()
    Image.new('RGB', taille, couleur).save(tampon, format='PNG')
    return base64.b64encode(tampon.getvalue())


@tagged('post_install', '-at_install')
class TestPapierAEnTete(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.mise_en_page = cls.env.ref('senodoo_report_letterhead.report_layout_letterhead')
        cls.company.write({
            'external_report_layout_id': cls.mise_en_page.view_id.id,
            'logo': _png('green', (120, 120)),
        })

    def _blocs(self):
        html, _ = self.env['ir.actions.report']._render_qweb_html(
            'web.action_report_layout_preview', self.company.ids)
        racine = lxml_html.fromstring(html)
        entete, = racine.xpath(CLASSE.format('header'))
        pied, = racine.xpath(CLASSE.format('footer'))
        return entete, pied

    @staticmethod
    def _sources(bloc, classe):
        return [img.get('src') for img in bloc.xpath(f".//img[contains(@class, '{classe}')]")]

    def test_images_dans_entete_et_pied_de_page(self):
        self.company.write({
            'letterhead_header_image': _png('red'),
            'letterhead_footer_image': _png('blue'),
        })
        entete, pied = self._blocs()

        self.assertEqual(self._sources(entete, 'o_letterhead_header_image'), [
            'data:image/png;base64,' + self.company.letterhead_header_image.decode(),
        ])
        self.assertEqual(self._sources(pied, 'o_letterhead_footer_image'), [
            'data:image/png;base64,' + self.company.letterhead_footer_image.decode(),
        ])
        # L'image d'en-tete remplace le logo ; le texte et la numerotation du
        # pied de page restent, l'image s'y ajoute.
        self.assertFalse(self._sources(entete, 'o_company_logo_big'))
        self.assertTrue(pied.xpath(CLASSE.format('o_footer_content')))
        self.assertIn('o_letterhead_has_image', pied.get('class'))

    def test_sans_image_le_logo_reste(self):
        self.company.write({'letterhead_header_image': False, 'letterhead_footer_image': False})
        entete, pied = self._blocs()

        self.assertTrue(self._sources(entete, 'o_company_logo_big'))
        self.assertTrue(entete.xpath(".//ul[@name='company_address_list']"))
        self.assertFalse(self._sources(entete, 'o_letterhead_image'))
        self.assertFalse(self._sources(pied, 'o_letterhead_image'))
        self.assertNotIn('o_letterhead_has_image', pied.get('class'))

    def test_assistant_de_mise_en_page(self):
        assistant = self.env['base.document.layout'].create({'company_id': self.company.id})

        assistant.report_layout_id = self.env.ref('web.report_layout_standard')
        self.assertFalse(assistant.is_letterhead_layout)

        assistant.write({
            'report_layout_id': self.mise_en_page.id,
            'external_report_layout_id': self.mise_en_page.view_id.id,
            'letterhead_header_image': _png('red'),
            'letterhead_footer_image': _png('blue'),
        })
        self.assertTrue(assistant.is_letterhead_layout)
        # L'apercu suit les images sans enregistrement intermediaire.
        self.assertIn('o_letterhead_header_image', assistant.preview)
        self.assertIn('o_letterhead_footer_image', assistant.preview)
        # Les champs de l'assistant sont ceux de la societe : imprimer apres
        # « Continuer » reprend exactement ce que l'apercu montrait.
        self.assertEqual(self.company.letterhead_header_image, assistant.letterhead_header_image)
