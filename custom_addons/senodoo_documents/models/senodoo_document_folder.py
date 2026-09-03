"""Espace de travail : le classement des documents.

Un espace peut etre restreint a des groupes. La restriction est appliquee par
une regle d'enregistrement sur les documents (senodoo_documents_rules.xml),
donc cote serveur : masquer un menu ne protegerait rien.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class SenodooDocumentFolder(models.Model):
    _name = 'senodoo.document.folder'
    _description = "Espace de travail"
    _parent_store = True
    _parent_name = 'parent_id'
    _order = 'sequence, name'

    name = fields.Char("Nom", required=True, translate=True)
    description = fields.Text("Description")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer("Couleur")

    parent_id = fields.Many2one(
        'senodoo.document.folder', string="Espace parent",
        ondelete='cascade', index=True,
    )
    child_ids = fields.One2many(
        'senodoo.document.folder', 'parent_id', string="Sous-espaces",
    )
    parent_path = fields.Char(index=True, unaccent=False)
    full_path = fields.Char("Chemin", compute='_compute_full_path', recursive=True)

    group_ids = fields.Many2many(
        'res.groups', 'senodoo_document_folder_group_rel', 'folder_id', 'group_id',
        string="Groupes autorises",
        help="Laisser vide pour ouvrir l'espace a tous les utilisateurs internes. "
             "Sinon, seuls les membres de ces groupes y accedent.",
    )

    document_count = fields.Integer("Documents", compute='_compute_document_count')

    @api.depends('name', 'parent_id.full_path')
    def _compute_full_path(self):
        for folder in self:
            parent = folder.parent_id
            folder.full_path = f"{parent.full_path} / {folder.name}" if parent else folder.name

    def _compute_document_count(self):
        counts = dict(self.env['senodoo.document']._read_group(
            [('folder_id', 'in', self.ids)], ['folder_id'], ['__count'],
        ))
        for folder in self:
            folder.document_count = counts.get(folder, 0)

    @api.constrains('parent_id')
    def _check_no_recursion(self):
        if self._has_cycle():
            raise ValidationError(_("Un espace ne peut pas etre son propre parent."))

    def action_open_documents(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'senodoo.document',
            'view_mode': 'kanban,list,form',
            # `child_of` : ouvrir un espace montre aussi ses sous-espaces,
            # sinon un classement profond obligerait a cliquer partout.
            'domain': [('folder_id', 'child_of', self.id)],
            'context': {'default_folder_id': self.id},
        }

    def action_archive_tree(self):
        """Archive l'espace, sa descendance et les documents qu'ils portent."""
        folders = self.search([('id', 'child_of', self.ids)])
        self.env['senodoo.document'].search([('folder_id', 'in', folders.ids)]).action_archive()
        folders.action_archive()
        return True


class SenodooDocumentTag(models.Model):
    _name = 'senodoo.document.tag'
    _description = "Etiquette de document"
    _order = 'name'

    name = fields.Char("Nom", required=True, translate=True)
    color = fields.Integer("Couleur")

    _name_uniq = models.Constraint('UNIQUE(name)', "Cette etiquette existe deja.")

    @api.ondelete(at_uninstall=False)
    def _unlink_except_used(self):
        used = self.env['senodoo.document'].search_count([('tag_ids', 'in', self.ids)])
        if used:
            raise UserError(_(
                "Cette etiquette est utilisee par %(count)s document(s). "
                "Retirez-la d'abord ou archivez ces documents.", count=used,
            ))
