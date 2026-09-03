"""Table de correspondance « application Enterprise -> equivalents Community ».

Les correspondances sont des DONNEES (data/senodoo_app_substitute_data.xml),
pas du code : un administrateur peut en ajouter depuis l'interface sans
redeploiement, et la table reste vraie quand l'addons_path change.
"""
import logging

from odoo import fields, models
from odoo.modules.module import Manifest

_logger = logging.getLogger(__name__)


class SenodooAppSubstitute(models.Model):
    _name = 'senodoo.app.substitute'
    _description = "Equivalent open source d'une application Enterprise"
    _order = 'name'

    name = fields.Char(
        string="Module Enterprise",
        required=True,
        index=True,
        help="Nom technique de la fiche `ir.module.module` marquee to_buy "
             "(ex. « helpdesk »). C'est la cle de correspondance.",
    )
    # Volontairement un champ texte et non un Many2many : les modules cites
    # peuvent etre absents de l'addons_path de CETTE installation. Une
    # reference XML dure ferait echouer le chargement du module ; une
    # resolution a l'execution degrade proprement.
    substitute_names = fields.Char(
        string="Modules de remplacement",
        help="Noms techniques Community separes par des virgules, par ordre "
             "de pertinence. Laisser vide s'il n'existe aucun equivalent.",
    )
    coverage = fields.Selection(
        [
            ('full', "Complete"),
            ('partial', "Partielle"),
            ('none', "Aucune"),
        ],
        string="Couverture fonctionnelle",
        required=True,
        default='none',
        help="Honnetete affichee a l'utilisateur : « partielle » signifie que "
             "l'equivalent couvre une partie du perimetre seulement.",
    )
    note = fields.Text(
        string="Explication",
        translate=True,
        help="Texte montre a l'administrateur : ce qui est couvert, ce qui "
             "ne l'est pas, et pourquoi.",
    )
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        'UNIQUE(name)',
        "Une seule correspondance par module Enterprise.",
    )

    def _substitute_name_list(self):
        """Noms techniques declares, nettoyes et dedupliques (ordre conserve)."""
        self.ensure_one()
        seen, result = set(), []
        for raw in (self.substitute_names or '').split(','):
            candidate = raw.strip()
            if candidate and candidate not in seen:
                seen.add(candidate)
                result.append(candidate)
        return result

    def _resolve_modules(self):
        """Modules de remplacement dont le code est REELLEMENT sur l'addons_path.

        Un nom declare mais introuvable est ignore (et journalise) : la table
        de correspondance decrit une intention, l'addons_path decrit la
        realite, et c'est la realite qui gagne.
        """
        Module = self.env['ir.module.module']
        if not self:
            return Module.browse()

        names = []
        for record in self:
            names.extend(record._substitute_name_list())
        if not names:
            return Module.browse()

        on_disk = [n for n in names if Manifest.for_addon(n, display_warning=False)]
        missing = set(names) - set(on_disk)
        if missing:
            _logger.info(
                "senodoo: equivalents declares mais absents de l'addons_path: %s",
                ', '.join(sorted(missing)),
            )
        if not on_disk:
            return Module.browse()

        found = Module.sudo().search([('name', 'in', on_disk)])
        # Preserver l'ordre de pertinence declare dans substitute_names.
        by_name = {m.name: m for m in found}
        ordered = Module.browse()
        for name in on_disk:
            if name in by_name:
                ordered |= by_name[name]
        return ordered
