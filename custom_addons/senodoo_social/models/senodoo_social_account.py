"""Compte de reseau social.

Le jeton d'acces est un secret : il n'est lisible que par le groupe
administrateur (`groups` sur le champ) et n'est jamais renvoye au client
pour un utilisateur ordinaire.
"""
from odoo import _, api, fields, models

# Limites publiees par chaque plateforme. Servent au compteur de caracteres
# et au controle avant envoi : mieux vaut refuser localement que consommer
# un appel d'API pour se faire rejeter.
PLATFORMS = [
    ('mastodon', "Mastodon"),
    ('x', "X (Twitter)"),
    ('linkedin', "LinkedIn"),
    ('facebook', "Facebook"),
    ('instagram', "Instagram"),
]

CHAR_LIMITS = {
    'mastodon': 500,
    'x': 280,
    'linkedin': 3000,
    'facebook': 63206,
    'instagram': 2200,
}

# Plateformes dont la publication est implementee de bout en bout.
IMPLEMENTED = ('mastodon',)


class SenodooSocialAccount(models.Model):
    _name = 'senodoo.social.account'
    _description = "Compte de reseau social"
    _order = 'platform, name'

    name = fields.Char("Nom du compte", required=True)
    platform = fields.Selection(PLATFORMS, string="Plateforme", required=True)
    handle = fields.Char("Identifiant public", help="Par exemple @masociete.")
    active = fields.Boolean(default=True)

    base_url = fields.Char(
        "URL de l'instance",
        help="Uniquement pour Mastodon : l'adresse de votre instance, "
             "par exemple https://mastodon.social",
    )
    access_token = fields.Char(
        "Jeton d'acces",
        groups='senodoo_social.group_social_manager',
        help="Obtenu chez la plateforme. Sans lui, aucune publication ne part.",
    )

    char_limit = fields.Integer("Limite de caracteres", compute='_compute_char_limit')
    is_configured = fields.Boolean("Pret a publier", compute='_compute_is_configured')
    publishing_supported = fields.Boolean(
        "Publication implementee", compute='_compute_is_configured',
        help="Faux tant que le connecteur de cette plateforme n'est pas ecrit : "
             "la planification fonctionne, l'envoi echouera explicitement.",
    )
    post_count = fields.Integer("Publications", compute='_compute_post_count')

    @api.depends('platform')
    def _compute_char_limit(self):
        for account in self:
            account.char_limit = CHAR_LIMITS.get(account.platform, 0)

    @api.depends('platform', 'access_token', 'base_url')
    def _compute_is_configured(self):
        for account in self:
            supported = account.platform in IMPLEMENTED
            account.publishing_supported = supported
            token = account.sudo().access_token
            needs_url = account.platform == 'mastodon'
            account.is_configured = bool(
                supported and token and (account.base_url if needs_url else True),
            )

    def _compute_post_count(self):
        counts = dict(self.env['senodoo.social.post.line']._read_group(
            [('account_id', 'in', self.ids)], ['account_id'], ['__count'],
        ))
        for account in self:
            account.post_count = counts.get(account, 0)

    def _missing_configuration(self):
        """Raison precise pour laquelle ce compte ne peut pas publier, ou ''."""
        self.ensure_one()
        if self.platform not in IMPLEMENTED:
            return _(
                "Le connecteur %(platform)s n'est pas encore implemente. "
                "Mastodon fonctionne de bout en bout ; les autres plateformes "
                "demandent une inscription developpeur et un flux OAuth propre "
                "a chacune.",
                platform=dict(PLATFORMS).get(self.platform, self.platform),
            )
        if not self.sudo().access_token:
            return _("Aucun jeton d'acces enregistre sur le compte « %(name)s ».",
                     name=self.name)
        if self.platform == 'mastodon' and not self.base_url:
            return _("L'URL de l'instance Mastodon manque sur « %(name)s ».",
                     name=self.name)
        return ''

    def action_view_posts(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Publications de %(name)s", name=self.name),
            'res_model': 'senodoo.social.post',
            'view_mode': 'list,form',
            'domain': [('account_ids', 'in', self.id)],
        }
