{
    'name': "Identité SEN ACE",
    'version': '1.5.1',
    'category': 'Website',
    'sequence': 201,
    'summary': "Retire la marque de l'editeur de toutes les surfaces visibles",
    'description': """
Identité SEN ACE
================

La marque de l'éditeur du serveur apparaît par défaut à une trentaine
d'endroits vus par un visiteur, un client ou un collaborateur. Ce module les
reprend un par un, sans toucher au code du cœur : chaque modification est une
héritance de vue, une surcharge d'asset ou une écriture de donnée, donc
réversible.

Pages publiques et interface :

* onglet du navigateur, favicon, icône d'écran d'accueil iOS, couleur de la
  barre d'adresse sur mobile, nom de l'application installable (PWA) ;
* mention « Powered by » de l'éditeur : page de connexion, portail client,
  enquêtes, page publique de discussion ;
* page /website/info, ouverte au public, qui affichait la version exacte du
  serveur et un lien vers le site de l'éditeur ;
* balise <meta name="generator"> de toutes les pages du site ;
* politique de cookies, écrans de réglages, titre des rapports PDF ;
* menu utilisateur : les deux entrées qui ouvraient le site de l'éditeur.

Courriels sortants, qui partent chez de vraies personnes :

* invitation d'un nouvel utilisateur, entièrement réécrite — l'originale est
  une publicité pour l'éditeur ;
* invitation à la double authentification ;
* résumé périodique, ses astuces et son pied de page ;
* notifications comptables, qui portaient le logo de l'éditeur ;
* invitations d'agenda, qui nommaient le lien de visioconférence.

La licence LGPL-3 du serveur autorise explicitement ce retrait de marque.
""",
    'author': "SEN ACE",
    'license': 'LGPL-3',
    # `digest` et `base_setup` ne sont pas ajoutes ici par gout : ils sont deja
    # tires par `website` et `mail`, et les nommer permet d'heriter leurs vues
    # sans rien installer de plus.
    'depends': ['web', 'mail', 'portal', 'website', 'digest', 'base_setup'],
    'data': [
        'data/branding_data.xml',
        'views/web_templates.xml',
        'views/mail_templates.xml',
        'views/portal_templates.xml',
        'views/website_templates.xml',
        'views/digest_templates.xml',
        'views/misc_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'senace_branding/static/src/js/branding.js',
        ],
    },
    'installable': True,
    'application': False,
}
