"""Vue d'ensemble du marketing social.

Modele transitoire : aucune donnee n'est stockee, tout est recalcule a
l'ouverture. C'est le motif Odoo classique pour un ecran de synthese, et il
evite d'avoir a maintenir des compteurs denormalises qui divergeraient.
"""
from odoo import _, api, fields, models

# Fenetre du planning affiche sur l'accueil. Au-dela, le calendrier prend le
# relais : un tableau de bord qui liste 200 publications n'aide personne.
UPCOMING_DAYS = 7
UPCOMING_LIMIT = 8


class SenodooSocialDashboard(models.TransientModel):
    _name = 'senodoo.social.dashboard'
    _description = "Vue d'ensemble du marketing social"

    # --- indicateurs ---------------------------------------------------
    posted_count = fields.Integer("Publiees", compute='_compute_counters')
    scheduled_count = fields.Integer("Planifiees", compute='_compute_counters')
    draft_count = fields.Integer("Brouillons", compute='_compute_counters')
    failed_count = fields.Integer("En echec", compute='_compute_counters')
    success_rate = fields.Integer("Taux de reussite", compute='_compute_counters')
    account_count = fields.Integer("Comptes", compute='_compute_counters')
    ready_account_count = fields.Integer("Comptes prets", compute='_compute_counters')

    # --- alertes -------------------------------------------------------
    has_failures = fields.Boolean(compute='_compute_counters')
    has_unconfigured = fields.Boolean(compute='_compute_counters')
    unconfigured_names = fields.Char(compute='_compute_counters')

    # --- listes --------------------------------------------------------
    upcoming_ids = fields.Many2many(
        'senodoo.social.post', 'senodoo_dashboard_upcoming_rel',
        string="A venir", compute='_compute_lists',
    )
    failed_ids = fields.Many2many(
        'senodoo.social.post', 'senodoo_dashboard_failed_rel',
        string="A traiter", compute='_compute_lists',
    )
    account_ids = fields.Many2many(
        'senodoo.social.account', 'senodoo_dashboard_account_rel',
        string="Comptes", compute='_compute_lists',
    )

    @api.depends_context('uid')
    def _compute_counters(self):
        Post = self.env['senodoo.social.post']
        Account = self.env['senodoo.social.account']
        # Un seul _read_group plutot qu'un search_count par etat.
        by_state = dict(Post._read_group([], ['state'], ['__count']))
        accounts = Account.search([])
        for board in self:
            board.posted_count = by_state.get('posted', 0)
            board.scheduled_count = by_state.get('scheduled', 0)
            board.draft_count = by_state.get('draft', 0)
            board.failed_count = by_state.get('failed', 0)

            attempted = board.posted_count + board.failed_count
            # Sans tentative, afficher 0 % laisserait croire a un probleme :
            # on affiche 100 % d'un historique vide, l'absence d'echec.
            board.success_rate = round(100 * board.posted_count / attempted) if attempted else 100

            ready = accounts.filtered(lambda account: account.is_configured)
            board.account_count = len(accounts)
            board.ready_account_count = len(ready)

            board.has_failures = bool(board.failed_count)
            not_ready = accounts - ready
            board.has_unconfigured = bool(not_ready)
            board.unconfigured_names = ', '.join(not_ready.mapped('name'))

    @api.depends_context('uid')
    def _compute_lists(self):
        Post = self.env['senodoo.social.post']
        now = fields.Datetime.now()
        horizon = fields.Datetime.add(now, days=UPCOMING_DAYS)
        upcoming = Post.search(
            [('state', '=', 'scheduled'), ('scheduled_date', '<=', horizon)],
            order='scheduled_date', limit=UPCOMING_LIMIT,
        )
        failed = Post.search([('state', '=', 'failed')], order='write_date desc', limit=5)
        accounts = self.env['senodoo.social.account'].search([])
        for board in self:
            board.upcoming_ids = upcoming
            board.failed_ids = failed
            board.account_ids = accounts

    # --- navigation ----------------------------------------------------
    def _open_posts(self, name, domain, context=None):
        return {
            'type': 'ir.actions.act_window',
            'name': name,
            'res_model': 'senodoo.social.post',
            'view_mode': 'list,calendar,form',
            'domain': domain,
            'context': context or {},
        }

    def action_open_posted(self):
        return self._open_posts(_("Publications publiees"), [('state', '=', 'posted')])

    def action_open_scheduled(self):
        return self._open_posts(_("Publications planifiees"), [('state', '=', 'scheduled')])

    def action_open_draft(self):
        return self._open_posts(_("Brouillons"), [('state', '=', 'draft')])

    def action_open_failed(self):
        return self._open_posts(_("Publications en echec"), [('state', '=', 'failed')])

    def action_open_accounts(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _("Comptes"),
            'res_model': 'senodoo.social.account',
            'view_mode': 'list,form',
        }

    def action_new_post(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _("Nouvelle publication"),
            'res_model': 'senodoo.social.post',
            'view_mode': 'form',
            'target': 'current',
        }
