{
    'name': "Marketing Automation",
    'version': '1.0',
    'category': 'Marketing/Marketing Automation',
    'sequence': 100,
    'summary': "Construisez des campagnes de mailing automatisees",
    'description': """
Marketing Automation
====================

Equivalent libre de l'application Enterprise `marketing_automation`, absente
de l'edition Community : des campagnes qui reagissent au comportement des
destinataires, la ou E-mail Marketing n'envoie qu'un message a une liste.

Fonctionnement
--------------
Une campagne cible un modele (contacts, pistes, contacts de liste...) via un
filtre. Les enregistrements correspondants deviennent des *participants*.

Chaque campagne porte un arbre d'*activites*. Une activite s'execute apres un
delai, a partir d'un declencheur :

* au debut de la campagne ;
* un delai apres l'activite parente ;
* si le courriel parent a ete ouvert -- ou ne l'a PAS ete ;
* s'il a ete clique -- ou non ;
* s'il a recu une reponse -- ou non.

Les declencheurs comportementaux s'appuient sur `mailing.trace`, alimente par
E-mail Marketing : ouvertures, clics et reponses sont ceux reellement
constates, pas une simulation.

Une activite envoie un mailing existant ou execute une action serveur.

Chaque passage laisse une *trace* : planifiee, traitee, annulee ou rejetee,
avec le motif. Rien ne s'execute deux fois.
""",
    'author': "Senodoo",
    'license': 'LGPL-3',
    'depends': ['mass_mailing'],
    'data': [
        'security/senodoo_marketing_groups.xml',
        'security/ir.model.access.csv',
        'data/senodoo_marketing_cron.xml',
        'views/senodoo_marketing_activity_views.xml',
        'views/senodoo_marketing_participant_views.xml',
        'views/senodoo_marketing_campaign_views.xml',
        'views/senodoo_marketing_menus.xml',
    ],
    'installable': True,
    'application': True,
}
