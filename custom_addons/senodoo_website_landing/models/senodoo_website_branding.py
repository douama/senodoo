"""Pose le logo SENACE sur le site et sur la fiche societe."""
import base64
import logging

from odoo import api, models
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

LOGO = 'senodoo_website_landing/static/src/img/senace-logo.png'


class SenodooWebsiteBranding(models.AbstractModel):
    _name = 'senodoo.website.branding'
    _description = "Identite visuelle SENACE"

    @api.model
    def apply_logo(self):
        """Ecrit le logo aux deux endroits ou il est attendu.

        Pourquoi du code plutot qu'un simple <record> de donnees :
        `website.default_website` et `base.main_company` portent
        `noupdate = true` dans ir_model_data (pose par les modules website et
        base). Odoo refuse donc de les reecrire lors d'une mise a jour, et le
        logo du site serait reste le SVG par defaut. Une ecriture par l'ORM
        n'est pas soumise a ce verrou.

        Les deux champs sont distincts et servent a des choses differentes :
          website.logo     -> en-tete du site public
          res.company.logo -> devis, factures, rapports PDF, e-mails
        """
        try:
            with file_open(LOGO, 'rb') as fichier:
                image = base64.b64encode(fichier.read())
        except FileNotFoundError:
            _logger.warning("senace: logo introuvable (%s), rien n'est pose", LOGO)
            return False

        site = self.env.ref('website.default_website', raise_if_not_found=False)
        if site:
            site.logo = image
        societe = self.env.ref('base.main_company', raise_if_not_found=False)
        if societe:
            societe.logo = image
        _logger.info("senace: logo pose sur le site et la fiche societe")
        return True
