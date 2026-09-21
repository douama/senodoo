"""Pose l'identite SENACE et l'URL publique sur le site."""
import base64
import logging
import os

from odoo import api, models
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

LOGO = 'senodoo_website_landing/static/src/img/senace-logo.png'
BASE_URL_ENV = 'ODOO_BASE_URL'


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

    @api.model
    def apply_base_url(self):
        """Aligne l'URL publique d'Odoo sur le domaine reellement servi.

        Pilote par la variable d'environnement ODOO_BASE_URL plutot que par
        une valeur ecrite en dur : la meme image sert le poste de
        developpement, la preproduction et la production. Variable absente,
        rien n'est touche -- un poste local garde son http://localhost:8069.

        `web.base.url.freeze` n'est pas un detail. Sans lui, Odoo reecrit
        `web.base.url` avec l'hote de la prochaine connexion d'un
        administrateur : une seule visite par l'URL Render suffirait a
        renvoyer vers onrender.com tous les liens des e-mails sortants.

        `website.domain` est un champ distinct, qui sert les URL absolues du
        site public : plan du site, balises canoniques et apercus de partage.
        """
        base_url = (os.environ.get(BASE_URL_ENV) or '').strip().rstrip('/')
        if not base_url:
            _logger.info(
                "senace: %s non definie, URL publique laissee en l'etat",
                BASE_URL_ENV)
            return False
        if not base_url.startswith(('http://', 'https://')):
            _logger.warning(
                "senace: %s ignoree, schema absent dans %r "
                "(attendu sous la forme https://exemple.sn)",
                BASE_URL_ENV, base_url)
            return False

        parametres = self.env['ir.config_parameter'].sudo()
        parametres.set_str('web.base.url', base_url)
        parametres.set_bool('web.base.url.freeze', True)

        site = self.env.ref('website.default_website', raise_if_not_found=False)
        if site:
            site.domain = base_url
        _logger.info("senace: URL publique fixee sur %s", base_url)
        return True
