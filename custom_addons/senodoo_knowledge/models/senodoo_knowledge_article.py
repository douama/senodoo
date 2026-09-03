"""Article de la base de connaissances.

Modele hierarchique volontairement simple : un article est un noeud d'arbre
porteur d'un corps HTML. La profondeur n'est pas limitee, la boucle parentale
est interdite par `_parent_store` + la contrainte de recursion d'Odoo.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

PERMISSIONS = [
    ('none', "Prive"),
    ('read', "Interne : lecture"),
    ('write', "Interne : edition"),
]


class SenodooKnowledgeTag(models.Model):
    _name = 'senodoo.knowledge.tag'
    _description = "Etiquette d'article"
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    color = fields.Integer("Couleur")

    _name_uniq = models.Constraint('UNIQUE(name)', "Cette etiquette existe deja.")


class SenodooKnowledgeArticle(models.Model):
    _name = 'senodoo.knowledge.article'
    _description = "Article de connaissance"
    _inherit = ['mail.thread']
    _parent_store = True
    _parent_name = 'parent_id'
    _order = 'sequence, name'

    name = fields.Char("Titre", required=True, tracking=True, default="Nouvel article")
    icon = fields.Char("Icone", default="📄", help="Un emoji affiche devant le titre.")
    body = fields.Html("Contenu", sanitize=True, prefetch=False)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    parent_id = fields.Many2one(
        'senodoo.knowledge.article', string="Article parent",
        ondelete='cascade', index=True,
    )
    child_ids = fields.One2many(
        'senodoo.knowledge.article', 'parent_id', string="Sous-articles",
    )
    parent_path = fields.Char(index=True, unaccent=False)
    # `_parent_store` maintient parent_path ; ce champ n'est la que pour
    # afficher le fil d'Ariane sans requete supplementaire.
    full_path = fields.Char("Chemin", compute='_compute_full_path', recursive=True)
    child_count = fields.Integer("Sous-articles", compute='_compute_child_count')

    tag_ids = fields.Many2many('senodoo.knowledge.tag', string="Etiquettes")
    internal_permission = fields.Selection(
        PERMISSIONS, string="Partage interne", required=True, default='write',
        help="Prive : seul l'auteur y accede. Les regles d'enregistrement "
             "appliquent ce choix cote serveur, pas seulement dans l'interface.",
    )
    author_id = fields.Many2one(
        'res.users', string="Auteur", required=True, index=True,
        default=lambda self: self.env.user, ondelete='restrict',
    )
    favorite_user_ids = fields.Many2many(
        'res.users', 'senodoo_knowledge_favorite_rel', 'article_id', 'user_id',
        string="En favori pour",
    )
    is_favorite = fields.Boolean(
        "Favori", compute='_compute_is_favorite', inverse='_inverse_is_favorite',
        search='_search_is_favorite',
    )

    @api.depends('name', 'parent_id.full_path')
    def _compute_full_path(self):
        for article in self:
            parent = article.parent_id
            article.full_path = f"{parent.full_path} / {article.name}" if parent else article.name

    @api.depends('child_ids')
    def _compute_child_count(self):
        counts = dict(self.env['senodoo.knowledge.article']._read_group(
            [('parent_id', 'in', self.ids)], ['parent_id'], ['__count'],
        ))
        for article in self:
            article.child_count = counts.get(article, 0)

    @api.depends_context('uid')
    @api.depends('favorite_user_ids')
    def _compute_is_favorite(self):
        for article in self:
            article.is_favorite = self.env.user in article.favorite_user_ids

    def _inverse_is_favorite(self):
        for article in self:
            command = (4, self.env.uid) if article.is_favorite else (3, self.env.uid)
            article.sudo().favorite_user_ids = [command]

    def _search_is_favorite(self, operator, value):
        if operator not in ('=', '!=') or not isinstance(value, bool):
            raise UserError(_("Filtre « favori » non supporte."))
        positive = (operator == '=') == value
        return [('favorite_user_ids', 'in' if positive else 'not in', self.env.uid)]

    @api.constrains('parent_id')
    def _check_no_recursion(self):
        if self._has_cycle():
            raise ValidationError(_("Un article ne peut pas etre son propre parent."))

    def action_toggle_favorite(self):
        for article in self:
            article.is_favorite = not article.is_favorite
        return True

    def action_create_child(self):
        """Cree un sous-article et l'ouvre : le geste le plus courant."""
        self.ensure_one()
        child = self.create({'name': _("Nouvel article"), 'parent_id': self.id})
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': child.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_archive_tree(self):
        """Archive l'article ET sa descendance : pas d'orphelin visible."""
        tree = self.search([('id', 'child_of', self.ids)])
        tree.action_archive()
        return True
