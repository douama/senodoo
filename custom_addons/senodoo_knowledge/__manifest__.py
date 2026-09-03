{
    'name': "Connaissances",
    'version': '1.0',
    'category': 'Productivity/Knowledge',
    'sequence': 90,
    'summary': "Centralisez, gerez, partagez et developpez votre bibliotheque de connaissances",
    'description': """
Connaissances
=============

Base d'articles hierarchique, versionnee et partagee : l'equivalent libre de
l'application Enterprise `knowledge`, absente de l'edition Community.

* arborescence d'articles imbriques sans limite de profondeur
* corps riche (HTML), pieces jointes, couverture et icone
* favoris par utilisateur
* etiquettes et recherche plein texte sur le titre ET le contenu
* trois niveaux de partage : prive, interne (lecture), interne (edition)
* corbeille : un article supprime est archive, jamais perdu
""",
    'author': "Senodoo",
    'license': 'LGPL-3',
    'depends': ['base', 'mail'],
    'data': [
        'security/senodoo_knowledge_groups.xml',
        'security/ir.model.access.csv',
        'security/senodoo_knowledge_rules.xml',
        'views/senodoo_knowledge_article_views.xml',
        'views/senodoo_knowledge_menus.xml',
    ],
    'installable': True,
    'application': True,
}
