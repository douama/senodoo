{
    'name': "Marketing social",
    'version': '1.1',
    'category': 'Marketing/Social Marketing',
    'sequence': 95,
    'summary': "Gerez vos reseaux sociaux et les visiteurs de votre site web",
    'description': """
Marketing social
================

Equivalent libre de l'application Enterprise `social`, absente de l'edition
Community : redaction, planification et suivi des publications sur vos
comptes de reseaux sociaux.

Perimetre couvert
-----------------
* comptes par plateforme (Facebook, LinkedIn, X, Instagram, Mastodon)
* redaction avec compteur de caracteres par plateforme
* planification a date et heure, publication automatique par cron
* suivi par compte : publie / echec, URL publiee, message d'erreur
* tableau de bord : indicateurs cliquables, alertes, planning a sept jours
* vues calendrier, graphique et tableau croise pour l'analyse

Ce qui exige une configuration
------------------------------
La publication reelle appelle l'API de chaque plateforme et requiert donc un
jeton d'acces obtenu chez elle. Sans jeton, la publication echoue avec un
message explicite nommant le compte concerne -- jamais un faux succes.
Mastodon est fourni cle en main (API simple, jeton unique) ; les autres
plateformes exposent le point d'entree a completer avec vos identifiants.
""",
    'author': "Senodoo",
    'license': 'LGPL-3',
    'depends': ['base', 'mail'],
    'data': [
        'security/senodoo_social_groups.xml',
        'security/ir.model.access.csv',
        'data/senodoo_social_cron.xml',
        'views/senodoo_social_account_views.xml',
        'views/senodoo_social_post_views.xml',
        'views/senodoo_social_dashboard_views.xml',
        'views/senodoo_social_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'senodoo_social/static/src/scss/dashboard.scss',
        ],
    },
    'installable': True,
    'application': True,
}
