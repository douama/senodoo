"""Pose les reglages de marque qui ne passent pas par une vue.

Trois valeurs vivent en base et non dans un template : le nom de
l'application installable (PWA), le favicon du site et le nom du robot de
discussion. Aucune ne peut etre posee par un simple <record> : voir le detail
dans chaque methode.
"""
import base64
import logging

from odoo import api, models
from odoo.tools import file_open

_logger = logging.getLogger(__name__)

FAVICON = 'senace_branding/static/src/img/favicon.png'
BRAND = "SEN ACE"
BOT = "%s Bot" % BRAND

# Noms sous lesquels le robot a pu etre enregistre : celui d'origine, et ceux
# que des versions anterieures de ce module ont poses. Sert a ne rebaptiser
# qu'un robot encore au nom « d'usine », sans ecraser un choix fait a la main.
NOMS_CONNUS = {'OdooBot', "Assistant %s" % BRAND, BOT}


class SenaceBranding(models.AbstractModel):
    _name = 'senace.branding'
    _description = "Reglages de marque SEN ACE"

    @api.model
    def apply_app_name(self):
        """Nomme l'application installable et l'onglet du navigateur.

        `web/controllers/webmanifest.py` retombe sur la chaine 'Odoo' quand le
        parametre est absent. C'est ce nom que le telephone affiche sous
        l'icone apres un « Ajouter a l'ecran d'accueil », et celui que le menu
        utilisateur propose d'installer.
        """
        self.env['ir.config_parameter'].sudo().set_str('web.web_app_name', BRAND)
        _logger.info("senace: nom d'application fixe sur %s", BRAND)
        return True

    @api.model
    def apply_favicon(self):
        """Remplace le favicon Odoo par la marque SEN ACE.

        Le defaut du champ est `web/static/img/favicon.ico`, l'icone violette
        d'Odoo : sans cette ecriture elle reste dans l'onglet du navigateur de
        chaque visiteur, et dans les favoris.

        Comme pour le logo, un <record> ne suffirait pas : `website` pose
        `noupdate = true` sur `website.default_website`, et Odoo refuserait de
        reecrire le champ. Odoo redimensionne lui-meme l'image en 256x256 dans
        `website._handle_favicon`.
        """
        try:
            with file_open(FAVICON, 'rb') as fichier:
                image = base64.b64encode(fichier.read())
        except FileNotFoundError:
            _logger.warning("senace: favicon introuvable (%s), rien n'est pose", FAVICON)
            return False

        site = self.env.ref('website.default_website', raise_if_not_found=False)
        if site:
            site.favicon = image
            _logger.info("senace: favicon pose sur le site")
        return True

    @api.model
    def apply_bot_name(self):
        """Renomme le robot auteur des messages automatiques du chatter.

        Ce nom s'affiche dans le fil de discussion de chaque fiche et dans
        Discuss, a cote de l'avatar du robot. `mail/data/res_partner_data.xml`
        le cree sous `mail.partner_root` avec noupdate=true.

        Le renommage n'a lieu que si le nom courant est l'un de ceux que nous
        connaissons : celui d'origine, ou l'un de ceux que ce module a poses
        dans une version anterieure. Un nom choisi a la main depuis l'interface
        est donc respecte, et une base deja passee par « Assistant SEN ACE »
        bascule tout de meme sur le libelle courant.
        """
        robot = self.env.ref('base.partner_root', raise_if_not_found=False)
        if not robot:
            return False
        valeurs = {}
        if robot.name in NOMS_CONNUS and robot.name != BOT:
            valeurs['name'] = BOT
        # L'adresse sert d'expediteur aux messages automatiques du chatter et
        # s'affiche sur la fiche du robot. On reste sur example.com, domaine
        # reserve par la RFC 2606 qui n'accepte aucun courrier : une vraie
        # adresse senace.sn ferait atterrir les reponses automatiques quelque
        # part.
        if robot.email == 'odoobot@example.com':
            valeurs['email'] = 'assistant@example.com'
        if valeurs:
            robot.sudo().write(valeurs)
            _logger.info("senace: robot de discussion rebaptise")
        return True
