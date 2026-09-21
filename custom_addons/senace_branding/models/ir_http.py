"""Retire de la charge utile de session l'URL de support d'Odoo."""
from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        """`support_url` pointe sur odoo.com/buy.

        L'entree « Help » du menu utilisateur, seule consommatrice de cette
        valeur, est retiree du registre par static/src/js/branding.js. La
        laisser ici ne ferait que republier l'adresse dans le source de chaque
        page du client web, ou n'importe qui peut la lire.
        """
        info = super().session_info()
        info.pop('support_url', None)
        return info
