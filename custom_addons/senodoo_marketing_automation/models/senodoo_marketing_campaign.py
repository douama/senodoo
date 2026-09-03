"""Campagne : un modele cible, un filtre, et un arbre d'activites."""
import ast
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

STATES = [
    ('draft', "Brouillon"),
    ('running', "En cours"),
    ('stopped', "Arretee"),
]


class SenodooMarketingCampaign(models.Model):
    _name = 'senodoo.marketing.campaign'
    _description = "Campagne de marketing automatise"
    _inherit = ['mail.thread']
    _order = 'name'

    name = fields.Char("Nom", required=True, tracking=True)
    active = fields.Boolean(default=True)
    state = fields.Selection(STATES, string="Etat", default='draft',
                             required=True, tracking=True, copy=False)

    model_id = fields.Many2one(
        'ir.model', string="Cible", required=True, ondelete='cascade',
        domain=[('is_mail_thread', '=', True)],
        help="Le modele dont les enregistrements entrent dans la campagne.",
    )
    model_name = fields.Char(related='model_id.model', string="Modele", store=True, readonly=True)
    domain = fields.Char("Filtre", default='[]', required=True)

    activity_ids = fields.One2many(
        'senodoo.marketing.activity', 'campaign_id', string="Activites", copy=True,
    )
    participant_ids = fields.One2many(
        'senodoo.marketing.participant', 'campaign_id', string="Participants",
    )

    participant_count = fields.Integer("Participants", compute='_compute_counters')
    running_count = fields.Integer("En cours", compute='_compute_counters')
    completed_count = fields.Integer("Terminés", compute='_compute_counters')
    activity_count = fields.Integer("Activités", compute='_compute_counters')

    @api.depends('participant_ids.state', 'activity_ids')
    def _compute_counters(self):
        # Avec DEUX criteres de regroupement, _read_group renvoie des
        # triplets (campagne, etat, compte) : les envelopper dans dict()
        # echouerait.
        rows = self.env['senodoo.marketing.participant']._read_group(
            [('campaign_id', 'in', self.ids)], ['campaign_id', 'state'], ['__count'],
        ) if self.ids else []
        totals = {}
        for campaign, state, count in rows:
            totals.setdefault(campaign.id, {})[state] = count
        for campaign in self:
            counts = totals.get(campaign.id, {})
            campaign.running_count = counts.get('running', 0)
            campaign.completed_count = counts.get('completed', 0)
            campaign.participant_count = sum(counts.values())
            campaign.activity_count = len(campaign.activity_ids)

    @api.constrains('domain', 'model_id')
    def _check_domain(self):
        for campaign in self:
            try:
                parsed = ast.literal_eval(campaign.domain or '[]')
                campaign.env[campaign.model_name].search_count(parsed, limit=1)
            except Exception as error:  # noqa: BLE001 - message clair a l'auteur
                raise ValidationError(_(
                    "Filtre invalide pour %(campaign)s : %(error)s",
                    campaign=campaign.name, error=error,
                )) from error

    def _target_records(self):
        """Enregistrements correspondant au filtre, a l'instant present."""
        self.ensure_one()
        return self.env[self.model_name].search(ast.literal_eval(self.domain or '[]'))

    # ------------------------------------------------------------------
    # Cycle de vie
    # ------------------------------------------------------------------
    def action_start(self):
        for campaign in self:
            if not campaign.activity_ids:
                raise UserError(_(
                    "« %(name)s » n'a aucune activite : rien ne se passerait.",
                    name=campaign.name,
                ))
            campaign.state = 'running'
            campaign.action_sync_participants()
        return True

    def action_stop(self):
        """Arrete la campagne et annule ce qui n'est pas encore parti.

        On n'annule QUE les traces planifiees : ce qui est deja envoye ne peut
        pas etre repris, le pretendre serait mentir.
        """
        for campaign in self:
            campaign.state = 'stopped'
            self.env['senodoo.marketing.trace'].search([
                ('campaign_id', '=', campaign.id), ('state', '=', 'scheduled'),
            ]).write({'state': 'canceled', 'state_msg': _("Campagne arretee.")})
        return True

    def action_reset(self):
        self.write({'state': 'draft'})
        return True

    def action_sync_participants(self):
        """Fait entrer dans la campagne les enregistrements nouvellement eligibles."""
        Participant = self.env['senodoo.marketing.participant']
        created = Participant.browse()
        for campaign in self.filtered(lambda c: c.state == 'running'):
            records = campaign._target_records()
            known = set(campaign.participant_ids.mapped('res_id'))
            missing = [record.id for record in records if record.id not in known]
            if not missing:
                continue
            participants = Participant.create([
                {'campaign_id': campaign.id, 'res_id': res_id} for res_id in missing
            ])
            created |= participants
            participants._schedule_begin_activities()
            _logger.info("senodoo marketing: %s participant(s) ajoutes a « %s »",
                         len(participants), campaign.name)
        return created

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------
    def action_view_participants(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Participants de %(name)s", name=self.name),
            'res_model': 'senodoo.marketing.participant',
            'view_mode': 'list,form',
            'domain': [('campaign_id', '=', self.id)],
            'context': {'default_campaign_id': self.id},
        }

    # ------------------------------------------------------------------
    # Cron
    # ------------------------------------------------------------------
    @api.model
    def _cron_process(self):
        """Fait entrer les nouveaux eligibles, puis execute ce qui est du."""
        running = self.search([('state', '=', 'running')])
        running.action_sync_participants()
        self.env['senodoo.marketing.trace']._process_due()
        running.participant_ids._refresh_completion()
        return True
