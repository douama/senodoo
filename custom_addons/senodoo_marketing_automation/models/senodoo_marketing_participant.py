"""Participant et trace : le moteur d'execution de la campagne.

Une trace est le passage d'UN participant par UNE activite. Elle porte son
propre etat : rien ne s'execute deux fois, et un echec sur un participant
n'arrete pas les autres.
"""
import logging

from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)

PARTICIPANT_STATES = [
    ('running', "En cours"),
    ('completed', "Termine"),
    ('unlinked', "Sorti de la cible"),
]

TRACE_STATES = [
    ('scheduled', "Planifiee"),
    ('processed', "Traitee"),
    ('canceled', "Annulee"),
    ('rejected', "Rejetee"),
]


class SenodooMarketingParticipant(models.Model):
    _name = 'senodoo.marketing.participant'
    _description = "Participant a une campagne"
    _order = 'campaign_id, id'

    campaign_id = fields.Many2one(
        'senodoo.marketing.campaign', string="Campagne",
        required=True, ondelete='cascade', index=True,
    )
    model_name = fields.Char(related='campaign_id.model_name', store=True, readonly=True)
    res_id = fields.Many2oneReference(
        string="Enregistrement", model_field='model_name', required=True, index=True,
    )
    display_name = fields.Char(compute='_compute_display_name')
    state = fields.Selection(PARTICIPANT_STATES, default='running', required=True, index=True)
    trace_ids = fields.One2many('senodoo.marketing.trace', 'participant_id', string="Traces")

    _campaign_record_uniq = models.Constraint(
        'UNIQUE(campaign_id, res_id)',
        "Un enregistrement ne participe qu'une fois a une campagne.",
    )

    @api.depends('res_id', 'model_name')
    def _compute_display_name(self):
        by_model = {}
        for participant in self:
            by_model.setdefault(participant.model_name, []).append(participant.res_id)
        names = {}
        for model, ids in by_model.items():
            if not model or model not in self.env:
                continue
            records = self.env[model].browse(ids).exists()
            names[model] = {record.id: record.display_name for record in records}
        for participant in self:
            names_for_model = names.get(participant.model_name, {})
            participant.display_name = names_for_model.get(
                participant.res_id, _("Enregistrement supprime"),
            )

    def _record(self):
        """L'enregistrement cible, ou un recordset vide s'il a disparu."""
        self.ensure_one()
        if not self.model_name or self.model_name not in self.env:
            return self.env['res.partner'].browse()
        return self.env[self.model_name].browse(self.res_id).exists()

    def _schedule_begin_activities(self):
        """Programme les activites de depart pour ces participants."""
        Trace = self.env['senodoo.marketing.trace']
        values = []
        for participant in self:
            for activity in participant.campaign_id.activity_ids.filtered(
                lambda a: a.trigger_type == 'begin',
            ):
                values.append({
                    'participant_id': participant.id,
                    'activity_id': activity.id,
                    'schedule_date': fields.Datetime.add(
                        fields.Datetime.now(), **activity._delay()),
                })
        return Trace.create(values) if values else Trace.browse()

    def _refresh_completion(self):
        """Un participant sans trace planifiee a fini son parcours."""
        if not self:
            return
        pending = dict(self.env['senodoo.marketing.trace']._read_group(
            [('participant_id', 'in', self.ids), ('state', '=', 'scheduled')],
            ['participant_id'], ['__count'],
        ))
        for participant in self.filtered(lambda p: p.state == 'running'):
            if not pending.get(participant):
                participant.state = 'completed'


class SenodooMarketingTrace(models.Model):
    _name = 'senodoo.marketing.trace'
    _description = "Passage d'un participant par une activite"
    _order = 'schedule_date, id'

    participant_id = fields.Many2one(
        'senodoo.marketing.participant', string="Participant",
        required=True, ondelete='cascade', index=True,
    )
    activity_id = fields.Many2one(
        'senodoo.marketing.activity', string="Activite",
        required=True, ondelete='cascade', index=True,
    )
    campaign_id = fields.Many2one(
        related='participant_id.campaign_id', string="Campagne",
        store=True, index=True, readonly=True,
    )
    schedule_date = fields.Datetime("Prevue le", required=True, index=True)
    state = fields.Selection(TRACE_STATES, default='scheduled', required=True, index=True)
    state_msg = fields.Char("Motif")
    mailing_trace_id = fields.Many2one(
        'mailing.trace', string="Trace d'envoi", ondelete='set null',
        help="Trace d'E-mail Marketing : c'est elle qui porte l'ouverture, "
             "le clic et la reponse reellement constates.",
    )

    # ------------------------------------------------------------------
    # Moteur
    # ------------------------------------------------------------------
    @api.model
    def _process_due(self, limit=500):
        """Traite les traces dont l'heure est venue."""
        due = self.search([
            ('state', '=', 'scheduled'),
            ('schedule_date', '<=', fields.Datetime.now()),
            ('campaign_id.state', '=', 'running'),
        ], order='schedule_date', limit=limit)
        _logger.info("senodoo marketing: %s trace(s) a traiter", len(due))
        for trace in due:
            trace._process_one()
        return due

    def _process_one(self):
        self.ensure_one()
        record = self.participant_id._record()
        if not record:
            self.write({'state': 'rejected',
                        'state_msg': _("L'enregistrement cible n'existe plus.")})
            return False

        allowed, reason = self._evaluate_trigger()
        if not allowed:
            self.write({'state': 'canceled', 'state_msg': reason})
            return False

        try:
            mailing_trace = self._execute(record)
        except Exception as error:  # noqa: BLE001 - un echec ne bloque pas la file
            self.write({'state': 'rejected', 'state_msg': str(error)[:500]})
            _logger.warning("senodoo marketing: activite %s en echec sur %s: %s",
                            self.activity_id.name, record, error)
            return False

        self.write({'state': 'processed', 'mailing_trace_id': mailing_trace.id if mailing_trace else False})
        self._schedule_children()
        return True

    def _evaluate_trigger(self):
        """Le declencheur comportemental est-il satisfait ?

        Renvoie (autorise, motif). Le motif explique l'annulation : une trace
        annulee sans raison lisible est indebogable.
        """
        self.ensure_one()
        trigger = self.activity_id.trigger_type
        if trigger in ('begin', 'activity'):
            return True, ''

        parent_trace = self.search([
            ('participant_id', '=', self.participant_id.id),
            ('activity_id', '=', self.activity_id.parent_id.id),
            ('state', '=', 'processed'),
        ], limit=1)
        mailing_trace = parent_trace.mailing_trace_id
        if not mailing_trace:
            return False, _("Le courriel parent n'a pas ete envoye.")

        observed = {
            'open': bool(mailing_trace.open_datetime),
            'click': bool(mailing_trace.links_click_datetime),
            'reply': bool(mailing_trace.reply_datetime),
        }
        # Un clic ou une reponse impliquent une ouverture, meme si le pixel de
        # suivi n'a pas ete charge : sans cela, « ouvert » serait sous-estime.
        observed['open'] = observed['open'] or observed['click'] or observed['reply']

        wanted = trigger.replace('mail_', '')
        negative = wanted.startswith('not_')
        key = wanted.removeprefix('not_')
        happened = observed[key]
        labels = {'open': _("ouvert"), 'click': _("clique"), 'reply': _("repondu")}
        if negative and happened:
            return False, _("Le courriel a ete %(what)s.", what=labels[key])
        if not negative and not happened:
            return False, _("Le courriel n'a pas ete %(what)s.", what=labels[key])
        return True, ''

    def _execute(self, record):
        """Realise l'activite. Renvoie la trace d'envoi si c'est un courriel."""
        self.ensure_one()
        activity = self.activity_id
        if activity.activity_type == 'action':
            activity.server_action_id.with_context(
                active_model=record._name, active_id=record.id, active_ids=record.ids,
            ).run()
            return self.env['mailing.trace'].browse()

        mailing = activity.mailing_id
        mailing.action_send_mail(res_ids=[record.id])
        # La trace la plus recente pour ce couple (mailing, enregistrement) :
        # c'est elle qui portera l'ouverture et le clic.
        return self.env['mailing.trace'].search([
            ('mass_mailing_id', '=', mailing.id),
            ('model', '=', record._name),
            ('res_id', '=', record.id),
        ], order='id desc', limit=1)

    def _schedule_children(self):
        """Programme les activites qui dependent de celle qui vient de passer."""
        self.ensure_one()
        values = []
        for child in self.activity_id.child_ids:
            values.append({
                'participant_id': self.participant_id.id,
                'activity_id': child.id,
                'schedule_date': fields.Datetime.add(
                    fields.Datetime.now(), **child._delay()),
            })
        return self.create(values) if values else self.browse()
