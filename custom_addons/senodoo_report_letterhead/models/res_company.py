from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    # Bornes en pixels : un A4 a 300 dpi fait 2480 px de large. Au-dela, le
    # fichier alourdit chaque PDF sans gain visible a l'impression.
    letterhead_header_image = fields.Image(
        "Image d'en-tête", max_width=2480, max_height=1200,
        help="Bandeau affiché en haut de chaque page, à la place du logo et de l'adresse.",
    )
    letterhead_footer_image = fields.Image(
        "Image de pied de page", max_width=2480, max_height=1200,
        help="Bandeau affiché en bas de chaque page, sous le texte du pied de page.",
    )
