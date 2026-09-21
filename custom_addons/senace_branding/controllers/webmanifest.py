"""Icone et couleurs de l'application installable.

`/web/manifest.webmanifest` est produit par du Python, pas par un gabarit :
c'est le seul endroit de la chaine ou une heritance de vue ne peut rien. Le
manifeste d'origine sert les icones de l'editeur et son violet #714B67 -- ce
sont eux que le telephone affiche sur l'ecran d'accueil, et dont se teinte
l'ecran de lancement, apres un « Ajouter a l'ecran d'accueil ».

Le nom, lui, est deja repris ailleurs : le controleur d'origine lit le
parametre `web.web_app_name`, que senace.branding pose a l'installation.
"""
from odoo.addons.web.controllers.webmanifest import WebManifest

# Bleu de la charte, identique a $o-community-color dans
# senace_website_landing/static/src/scss/senace_variables.scss.
BLEU = '#0a4da3'
ICONES = '/senace_branding/static/src/img/icon-%s.png'


class SenaceWebManifest(WebManifest):

    def _get_webmanifest(self):
        manifeste = super()._get_webmanifest()
        manifeste['background_color'] = BLEU
        manifeste['theme_color'] = BLEU
        manifeste['icons'] = [{
            'src': ICONES % taille,
            'sizes': '%sx%s' % (taille, taille),
            'type': 'image/png',
        } for taille in (192, 512)]
        return manifeste
