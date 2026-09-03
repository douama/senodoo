{
    'name': "Page d'accueil SENACE",
    'version': '1.2.0',
    'category': 'Website',
    'sequence': 200,
    'summary': "Landing page premium des quatre pôles SENACE",
    'description': """
Page d'accueil SENACE
======================

Remplace la page d'accueil par defaut d'Odoo (« Home | My Website ») par une
landing page presentant les quatre poles SENACE : formation professionnelle,
coaching, services aux entreprises et services au tourisme a Dakar.

La page reste dans un bloc `oe_structure` : elle demeure entierement
modifiable depuis l'editeur de site d'Odoo, sans toucher au code.

Les appels a l'action pointent vers /contactus. `website_crm` etant installe,
chaque formulaire envoye cree une piste dans le CRM.

Toutes les coordonnees affichees proviennent de la fiche societe
(`res.company`) : changer l'adresse ou le telephone dans Odoo met la page a
jour, il n'y a rien a coder en dur.
""",
    'author': "Senodoo",
    'license': 'LGPL-3',
    'depends': ['website', 'website_crm'],
    'data': [
        'data/website_data.xml',
        'data/ir_asset.xml',
        'views/landing_templates.xml',
        'views/branding_templates.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'senodoo_website_landing/static/src/scss/landing.scss',
        ],
    },
    'installable': True,
    'application': False,
}
