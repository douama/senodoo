"""Activite : ce que la campagne fait, quand, et sous quelle condition."""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

ACTIVITY_TYPES = [
    ('email', "Envoyer un courriel"),
    ('action', "Executer une action serveur"),
]

# Declencheurs comportementaux : ils s'appuient sur `mailing.trace`, alimente
# par E-mail Marketing. Les statuts sont donc ceux reellement constates.
TRIGGERS = [
    ('begin', "Au debut de la campagne"),
    ('activity', "Apres l'activite parente"),
    ('mail_open', "Si le courriel parent est ouvert"),
    ('mail_not_open', "Si le courriel parent n'est pas ouvert"),
    ('mail_click', "Si un lien est clique"),
    ('mail_not_click', "Si aucun lien n'est clique"),
    ('mail_reply', "Si une reponse arrive"),
    ('mail_not_reply', "Si aucune reponse n'arrive"),
]

MAIL_TRIGGERS = {t[0] for t in TRIGGERS if t[0].startswith('mail_')}

INTERVALS = [
    ('hours', "Heures"),
    ('days', "Jours"),
    ('weeks', "Semaines"),
    ('months', "Mois"),
]


class SenodooMarketingActivity(models.Model):
    _name = 'senodoo.marketing.activity'
    _description = "Activite de campagne"
    _order = 'campaign_id, sequence, id'

    name = fields.Char("Nom", required=True)
    sequence = fields.Integer(default=10)
    campaign_id = fields.Many2one(
        'senodoo.marketing.campaign', string="Campagne",
        required=True, ondelete='cascade', index=True,
    )
    model_name = fields.Char(related='campaign_id.model_name', readonly=True)

    activity_type = fields.Selection(
        ACTIVITY_TYPES, string="Type", required=True, default='email',
    )
    mailing_id = fields.Many2one(
        'mailing.mailing', string="Courriel",
        domain="[('mailing_model_name', '=', model_name)]",
        ondelete='restrict',
        help="Un mailing existant d'E-mail Marketing. Il sera envoye au seul "
             "participant concerne, pas a toute sa liste.",
    )
    server_action_id = fields.Many2one(
        'ir.actions.server', string="Action serveur", ondelete='restrict',
        help="Executee avec le participant comme enregistrement courant.",
    )

    interval_number = fields.Integer("Delai", default=0, required=True)
    interval_type = fields.Selection(INTERVALS, string="Unite", default='hours', required=True)

    parent_id = fields.Many2one(
        'senodoo.marketing.activity', string="Activite parente",
        ondelete='cascade', index=True,
    )
    child_ids = fields.One2many(
        'senodoo.marketing.activity', 'parent_id', string="Activites suivantes",
    )
    trigger_type = fields.Selection(
        TRIGGERS, string="Declencheur", required=True, default='begin',
    )

    processed_count = fields.Integer("Traitees", compute='_compute_counters')
    canceled_count = fields.Integer("Annulees", compute='_compute_counters')
    rejected_count = fields.Integer("Rejetees", compute='_compute_counters')

    def _compute_counters(self):
        # Idem : deux criteres de regroupement -> des triplets.
        rows = self.env['senodoo.marketing.trace']._read_group(
            [('activity_id', 'in', self.ids)], ['activity_id', 'state'], ['__count'],
        ) if self.ids else []
        totals = {}
        for activity, state, count in rows:
            totals.setdefault(activity.id, {})[state] = count
        for activity in self:
            counts = totals.get(activity.id, {})
            activity.processed_count = counts.get('processed', 0)
            activity.canceled_count = counts.get('canceled', 0)
            activity.rejected_count = counts.get('rejected', 0)

    @api.constrains('trigger_type', 'parent_id')
    def _check_trigger_needs_parent(self):
        for activity in self:
            if activity.trigger_type == 'begin' and activity.parent_id:
                raise ValidationError(_(
                    "« %(name)s » demarre la campagne : elle ne peut pas avoir "
                    "d'activite parente.", name=activity.name,
                ))
            if activity.trigger_type != 'begin' and not activity.parent_id:
                raise ValidationError(_(
                    "« %(name)s » depend d'une activite parente : choisissez-la.",
                    name=activity.name,
                ))
            if activity.trigger_type in MAIL_TRIGGERS and activity.parent_id.activity_type != 'email':
                raise ValidationError(_(
                    "« %(name)s » reagit a un courriel : son activite parente "
                    "doit en envoyer un.", name=activity.name,
                ))

    @api.constrains('activity_type', 'mailing_id', 'server_action_id')
    def _check_activity_payload(self):
        for activity in self:
            if activity.activity_type == 'email' and not activity.mailing_id:
                raise ValidationError(_(
                    "« %(name)s » doit designer un courriel a envoyer.", name=activity.name,
                ))
            if activity.activity_type == 'action' and not activity.server_action_id:
                raise ValidationError(_(
                    "« %(name)s » doit designer une action serveur.", name=activity.name,
                ))

    @api.constrains('parent_id')
    def _check_no_recursion(self):
        if self._has_cycle('parent_id'):
            raise ValidationError(_("Les activites forment une boucle."))

    def _delay(self):
        """Delai de l'activite, sous forme d'arguments pour Datetime.add."""
        self.ensure_one()
        return {self.interval_type: max(self.interval_number, 0)}
