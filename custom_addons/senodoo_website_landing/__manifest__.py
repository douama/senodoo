{
    'name': "Page d'accueil SENACE",
    'version': '1.9.0',
    'category': 'Website',
    'sequence': 200,
    'summary': "Landing page premium des quatre pôles SENACE",
    'description': """
Page d'accueil SENACE
======================

Remplace la page d'accueil par defaut (« Home | My Website ») par une
landing page presentant les quatre poles SENACE : formation professionnelle,
coaching, services aux entreprises et eco tourisme durable a Dakar.

La page reste dans un bloc `oe_structure` : elle demeure entierement
modifiable depuis l'editeur de site, sans toucher au code.

Les appels a l'action pointent vers /contactus. `website_crm` etant installe,
chaque formulaire envoye cree une piste dans le CRM.

Les coordonnees publiques sont reprises de l'en-tete et du pied de page afin
de proposer un parcours de contact coherent sur l'ensemble du site.

Sous-pages dans le menu principal : la fenetre d'un element de menu propose
« Sous-menu de », en plus du glisser-deposer natif d'Odoo, et les listes
deroulantes reprennent les couleurs de l'en-tete.
""",
    'author': "SEN ACE",
    'license': 'LGPL-3',
    'depends': ['website', 'website_crm'],
    'data': [
        'data/website_data.xml',
        'data/logo_data.xml',
        'data/base_url_data.xml',
        'data/ir_asset.xml',
        'views/landing_templates.xml',
        'views/branding_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'senodoo_website_landing/static/src/scss/landing.scss',
            'senodoo_website_landing/static/src/scss/header_logo.scss',
            'senodoo_website_landing/static/src/scss/header_menu.scss',
        ],
        'website.assets_editor': [
            'senodoo_website_landing/static/src/js/edit_menu_parent.js',
            'senodoo_website_landing/static/src/js/edit_menu_parent.xml',
        ],
        'web.assets_tests': [
            'senodoo_website_landing/static/tests/tours/menu_parent.js',
        ],
    },
    'installable': True,
    'application': False,
}
