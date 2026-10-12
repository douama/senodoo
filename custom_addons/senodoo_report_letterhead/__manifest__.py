{
    'name': "En-tête et pied de page des documents",
    'version': '1.0',
    'category': 'Productivity',
    'sequence': 210,
    'summary': "Papier à en-tête : une image d'en-tête et une image de pied de page sur les PDF",
    'description': """
En-tête et pied de page des documents
=====================================

Odoo ne laisse saisir, sur les documents générés, qu'un slogan et un pied de
page en texte. Une entreprise qui possède un papier à en-tête dessiné (bandeau
avec logo, coordonnées, NINEA, RC...) ne peut pas l'y reprendre.

Ce module ajoute une mise en page « Papier à en-tête » à l'assistant
*Paramètres > Configurer la mise en page*. Une fois choisie, deux images
apparaissent dans l'assistant, avec l'aperçu en direct :

* l'image d'en-tête remplace le logo et l'adresse en haut de chaque page ;
* l'image de pied de page s'affiche en bas de chaque page, sous le texte du
  pied de page et la numérotation, qui restent en place.

Sans image, la mise en page retombe sur le logo, l'adresse et le pied de page
texte : choisir la mise en page avant d'avoir les fichiers ne produit jamais
un document vide.

La règle vaut pour tous les documents qui utilisent la mise en page externe :
devis, factures, bons de commande, bons de livraison...

Les hauteurs sont bornées (38 mm en haut, 17 mm en bas) pour tenir dans les
marges du format A4 par défaut : une image trop haute est réduite, jamais
rognée ni posée sur le contenu.
""",
    'author': "SEN ACE",
    'license': 'LGPL-3',
    'depends': ['web'],
    'data': [
        'views/report_templates.xml',
        'data/report_layout_data.xml',
        'views/base_document_layout_views.xml',
    ],
    'assets': {
        'web.report_assets_common': [
            'senodoo_report_letterhead/static/src/scss/letterhead.scss',
        ],
    },
    'installable': True,
    'application': False,
}
