"""Publication et lignes de publication (une par compte cible).

La publication est decomposee en lignes pour qu'un echec sur un reseau
n'empeche ni n'annule les autres : chaque ligne porte son propre etat, son
URL publiee et son erreur.
"""
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from odoo import _, api, fields, models, modules
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

STATES = [
    ('draft', "Brouillon"),
    ('scheduled', "Planifiee"),
    ('posted', "Publiee"),
    ('failed', "Echec"),
]


class SenodooSocialPost(models.Model):
    _name = 'senodoo.social.post'
    _description = "Publication sur les reseaux sociaux"
    _inherit = ['mail.thread']
    _order = 'scheduled_date desc, id desc'

    name = fields.Char("Titre interne", compute='_compute_name', store=True)
    message = fields.Text("Message", required=True, tracking=True)
    image = fields.Image("Visuel", max_width=1920, max_height=1920)
    link_url = fields.Char("Lien a partager")

    account_ids = fields.Many2many(
        'senodoo.social.account', string="Comptes cibles", required=True,
    )
    line_ids = fields.One2many(
        'senodoo.social.post.line', 'post_id', string="Resultats par compte",
    )

    scheduled_date = fields.Datetime(
        "Publier le",
        help="Laisser vide pour publier immediatement via le bouton.",
    )
    state = fields.Selection(STATES, string="Etat", default='draft',
                             required=True, tracking=True, copy=False)
    error_message = fields.Text("Dernier echec", readonly=True, copy=False)

    posted_count = fields.Integer("Publiees", compute='_compute_counts')
    failed_count = fields.Integer("En echec", compute='_compute_counts')
    over_limit_warning = fields.Char("Depassement", compute='_compute_over_limit')

    @api.depends('message')
    def _compute_name(self):
        for post in self:
            text = (post.message or '').strip().replace('\n', ' ')
            post.name = (text[:60] + '…') if len(text) > 60 else (text or _("Publication"))

    @api.depends('line_ids.state')
    def _compute_counts(self):
        for post in self:
            post.posted_count = len(post.line_ids.filtered(lambda line: line.state == 'posted'))
            post.failed_count = len(post.line_ids.filtered(lambda line: line.state == 'failed'))

    @api.depends('message', 'account_ids.char_limit')
    def _compute_over_limit(self):
        for post in self:
            length = len(post.message or '')
            over = post.account_ids.filtered(
                lambda a: a.char_limit and length > a.char_limit,
            )
            post.over_limit_warning = _(
                "%(count)s caracteres : trop long pour %(accounts)s.",
                count=length,
                accounts=', '.join(f"{a.name} ({a.char_limit})" for a in over),
            ) if over else False

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_schedule(self):
        for post in self:
            if not post.scheduled_date:
                raise UserError(_("Renseignez une date de publication."))
            post._ensure_publishable()
            post.write({'state': 'scheduled', 'error_message': False})
        return True

    def action_reset_draft(self):
        self.write({'state': 'draft', 'error_message': False})
        return True

    def action_publish_now(self):
        """Publie immediatement. Le resultat est reel, jamais simule."""
        for post in self:
            post._ensure_publishable()
            post._publish()
        return True

    def _ensure_publishable(self):
        self.ensure_one()
        if not self.account_ids:
            raise UserError(_("Choisissez au moins un compte cible."))
        if self.over_limit_warning:
            raise UserError(self.over_limit_warning)

    # ------------------------------------------------------------------
    # Publication
    # ------------------------------------------------------------------
    def _publish(self):
        """Publie sur chaque compte, independamment des autres.

        Un echec sur un reseau n'annule pas les autres : chaque ligne porte
        son propre etat. La publication globale n'est « posted » que si aucune
        ligne n'a echoue.
        """
        self.ensure_one()
        Line = self.env['senodoo.social.post.line']
        errors = []
        for account in self.account_ids:
            line = self.line_ids.filtered(lambda line: line.account_id == account)[:1]
            if not line:
                line = Line.create({'post_id': self.id, 'account_id': account.id})
            if line.state == 'posted':
                continue  # idempotence : ne jamais republier deux fois
            try:
                url = self._publish_on(account)
            except Exception as error:  # noqa: BLE001 - remontee integrale
                message = str(error)
                line.write({'state': 'failed', 'error_message': message, 'published_url': False})
                errors.append(f"{account.name} : {message}")
                _logger.warning("senodoo social: echec sur %s: %s", account.name, message)
            else:
                line.write({'state': 'posted', 'published_url': url, 'error_message': False})

        if errors:
            self.write({'state': 'failed', 'error_message': '\n'.join(errors)})
        else:
            self.write({'state': 'posted', 'error_message': False})
        return not errors

    def _publish_on(self, account):
        """Publie sur un compte et renvoie l'URL publiee.

        Leve une exception explicite si le compte n'est pas configure : on ne
        marque jamais « publie » ce qui n'est pas parti.
        """
        self.ensure_one()
        missing = account._missing_configuration()
        if missing:
            raise UserError(missing)
        handler = getattr(self, f'_publish_{account.platform}', None)
        if handler is None:
            raise UserError(_("Aucun connecteur pour %(platform)s.",
                              platform=account.platform))
        return handler(account)

    def _publish_mastodon(self, account):
        """API Mastodon : POST /api/v1/statuses avec un jeton porteur."""
        self.ensure_one()
        body = self.message or ''
        if self.link_url:
            body = f"{body}\n{self.link_url}"
        endpoint = account.base_url.rstrip('/') + '/api/v1/statuses'
        data = urllib.parse.urlencode({'status': body}).encode()
        request = urllib.request.Request(
            endpoint, data=data,
            headers={
                'Authorization': f'Bearer {account.sudo().access_token}',
                'Content-Type': 'application/x-www-form-urlencoded',
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read())
        except urllib.error.HTTPError as error:
            detail = error.read().decode('utf-8', 'replace')[:300]
            raise UserError(_(
                "Mastodon a refuse la publication (HTTP %(code)s) : %(detail)s",
                code=error.code, detail=detail,
            )) from error
        except urllib.error.URLError as error:
            raise UserError(_(
                "Instance Mastodon injoignable (%(url)s) : %(reason)s",
                url=account.base_url, reason=error.reason,
            )) from error
        return payload.get('url') or payload.get('uri') or ''

    # ------------------------------------------------------------------
    # Cron
    # ------------------------------------------------------------------
    @api.model
    def _cron_publish_scheduled(self):
        """Publie les messages planifies dont l'heure est passee."""
        due = self.search([
            ('state', '=', 'scheduled'),
            ('scheduled_date', '<=', fields.Datetime.now()),
        ])
        _logger.info("senodoo social: %s publication(s) a traiter", len(due))
        for post in due:
            try:
                post._publish()
            except Exception:  # noqa: BLE001 - un echec ne doit pas bloquer la file
                _logger.exception("senodoo social: publication %s en echec", post.id)
            # Chaque publication est validee separement : un plantage plus loin
            # dans la file ne doit pas annuler ce qui est deja parti sur les
            # reseaux -- on ne peut pas « depublier ».
            #
            # Odoo interdit commit() dans un test (le curseur deviendrait
            # inutilisable au rollback) ; le framework de test isole deja
            # chaque cas, la garantie n'y est donc pas necessaire.
            if not modules.module.current_test:
                self.env.cr.commit()
        return True


class SenodooSocialPostLine(models.Model):
    _name = 'senodoo.social.post.line'
    _description = "Resultat de publication par compte"
    _order = 'post_id, account_id'

    post_id = fields.Many2one('senodoo.social.post', required=True,
                              ondelete='cascade', index=True)
    account_id = fields.Many2one('senodoo.social.account', string="Compte",
                                 required=True, ondelete='cascade')
    state = fields.Selection(
        [('pending', "En attente"), ('posted', "Publiee"), ('failed', "Echec")],
        default='pending', required=True,
    )
    published_url = fields.Char("URL publiee")
    error_message = fields.Text("Erreur")

    _post_account_uniq = models.Constraint(
        'UNIQUE(post_id, account_id)',
        "Un compte ne peut apparaitre qu'une fois par publication.",
    )
