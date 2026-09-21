{
    'name': "Identité SEN ACE",
    'version': '1.0.0',
    'category': 'Website',
    'sequence': 201,
    'summary': "Retire la marque Odoo de toutes les surfaces visibles",
    'description': """
Identité SEN ACE
================

Le serveur est un Odoo Community : la marque de l'éditeur apparaît par défaut
à une quinzaine d'endroits vus par un visiteur ou un utilisateur. Ce module les
reprend un par un, sans toucher au code du cœur — chaque modification est une
héritance de vue ou une surcharge d'asset, donc réversible en désinstallant.

Ce qui est repris :

* onglet du navigateur, favicon et nom de l'application installable (PWA) ;
* mention « Powered by Odoo » : page de connexion, portail client, pied de
  page des e-mails sortants, enquêtes ;
* page publique /website/info, qui affichait la version d'Odoo et un lien
  vers odoo.com ;
* balise <meta name="generator"> de toutes les pages du site ;
* menu utilisateur : « My Odoo.com Account » et « Help » (liens odoo.com) ;
* titre des rapports PDF ;
* page hors ligne et info-bulle du bouton Applications.

La licence LGPL-3 d'Odoo autorise explicitement ce retrait de marque.
""",
    'author': "SEN ACE",
    'license': 'LGPL-3',
    'depends': ['web', 'mail', 'portal', 'website'],
    'data': [
        'data/branding_data.xml',
        'views/web_templates.xml',
        'views/mail_templates.xml',
        'views/portal_templates.xml',
        'views/website_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'senace_branding/static/src/js/branding.js',
        ],
    },
    'installable': True,
    'application': False,
}
