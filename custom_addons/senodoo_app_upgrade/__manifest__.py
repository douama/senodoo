{
    'name': "Activation des applications Senodoo",
    'version': '1.0',
    'category': 'Administration',
    'summary': "Rend le bouton « Mettre a niveau » fonctionnel : equivalents open source et diagnostic honnete",
    'description': """
Activation des applications marquees « Mettre a niveau »
=======================================================

En edition Community, 20 fiches `ir.module.module` sont livrees sans code
(`odoo/addons/base/data/ir_module_module.xml`) : `to_buy = True`,
`state = 'uninstallable'`, licence `OEEL-1`. La vue kanban des Apps affiche
pour elles un simple lien HTML vers `odoo.com/pricing` au lieu du bouton
`button_immediate_install`.

Ce module remplace ce lien mort par une vraie operation serveur :

* detection DYNAMIQUE des modules concernes (requete sur `to_buy`), sans
  liste codee en dur ;
* verification de la presence reelle du code sur l'`addons_path` ;
* si le code est present, delegation a `update_list()` puis au bouton
  « Activer » natif d'Odoo ;
* sinon, installation en un clic du meilleur equivalent Community
  reellement disponible, avec resolution complete des dependances ;
* si aucun equivalent n'existe, message d'erreur precis et persiste --
  jamais d'echec silencieux, jamais d'application faussement « activee ».

Aucun systeme parallele : les permissions (`assert_log_admin_access`), le
verrou anti-concurrence (`LOCK ir_module_module IN EXCLUSIVE MODE`), la
resolution de dependances et la persistance restent ceux d'Odoo.
""",
    'author': "Senodoo",
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'data/senodoo_app_substitute_data.xml',
        'views/senodoo_app_substitute_views.xml',
        'views/ir_module_module_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
