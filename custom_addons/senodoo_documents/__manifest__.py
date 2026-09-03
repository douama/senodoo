{
    'name': "Documents",
    'version': '1.0',
    'category': 'Productivity/Documents',
    'sequence': 85,
    'summary': "Centralisez, classez et partagez les fichiers de l'entreprise",
    'description': """
Documents
=========

Gestion electronique de documents : l'equivalent libre de l'application
Enterprise `documents`, absente de l'edition Community.

* espaces de travail imbriques sans limite de profondeur
* fichiers televerses ou simples liens externes, dans le meme classement
* etiquettes colorees et recherche portant sur le nom ET la description
* taille, type MIME et extension calcules et interrogeables
* restriction d'un espace de travail a des groupes precis, appliquee par des
  regles d'enregistrement -- donc cote serveur
* corbeille : un document supprime est archive, jamais perdu

Le stockage s'appuie sur `ir.attachment` : les fichiers suivent le filestore
et les sauvegardes existantes, sans mecanisme paralle.
""",
    'author': "Senodoo",
    'license': 'LGPL-3',
    'depends': ['base', 'mail'],
    'data': [
        'security/senodoo_documents_groups.xml',
        'security/ir.model.access.csv',
        'security/senodoo_documents_rules.xml',
        'views/senodoo_document_folder_views.xml',
        'views/senodoo_document_views.xml',
        'views/senodoo_documents_menus.xml',
    ],
    'installable': True,
    'application': True,
}
