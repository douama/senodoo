"""Document : un fichier televerse ou un lien externe, dans un espace.

Le binaire est stocke via `ir.attachment` (comportement natif d'un champ
Binary) : les fichiers suivent le filestore et les sauvegardes existantes,
sans mecanisme parallele a maintenir.
"""
import mimetypes
import os

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

TYPES = [
    ('file', "Fichier"),
    ('url', "Lien externe"),
]


class SenodooDocument(models.Model):
    _name = 'senodoo.document'
    _description = "Document"
    _inherit = ['mail.thread']
    _order = 'create_date desc, name'

    name = fields.Char("Nom", required=True, tracking=True)
    description = fields.Text("Description")
    active = fields.Boolean(default=True)

    type = fields.Selection(TYPES, string="Type", required=True, default='file')
    datas = fields.Binary("Fichier", attachment=True)
    file_name = fields.Char("Nom du fichier")
    url = fields.Char("Lien")

    folder_id = fields.Many2one(
        'senodoo.document.folder', string="Espace de travail",
        required=True, ondelete='restrict', index=True, tracking=True,
    )
    tag_ids = fields.Many2many('senodoo.document.tag', string="Etiquettes")
    owner_id = fields.Many2one(
        'res.users', string="Proprietaire", required=True, index=True,
        default=lambda self: self.env.user, ondelete='restrict', tracking=True,
    )
    partner_id = fields.Many2one('res.partner', string="Contact lie")

    # Stockes pour rester triables et interrogeables : une GED ou l'on ne peut
    # pas filtrer par taille ou par type rend service a personne.
    file_size = fields.Integer("Taille", compute='_compute_file_info', store=True)
    mimetype = fields.Char("Type MIME", compute='_compute_file_info', store=True)
    extension = fields.Char("Extension", compute='_compute_extension', store=True)
    file_size_human = fields.Char("Taille", compute='_compute_file_size_human')

    @api.depends('datas', 'file_name')
    def _compute_file_info(self):
        Attachment = self.env['ir.attachment'].sudo()
        saved = self.filtered(lambda doc: isinstance(doc.id, int))
        by_res = {}
        if saved:
            attachments = Attachment.search([
                ('res_model', '=', self._name),
                ('res_id', 'in', saved.ids),
                ('res_field', '=', 'datas'),
            ])
            by_res = {attachment.res_id: attachment for attachment in attachments}
        for document in self:
            attachment = by_res.get(document.id if isinstance(document.id, int) else None)
            if attachment:
                document.file_size = attachment.file_size
                document.mimetype = attachment.mimetype
            else:
                document.file_size = 0
                # Sur un enregistrement pas encore sauvegarde, l'attachement
                # n'existe pas : on devine le type depuis le nom du fichier
                # pour que l'icone soit correcte des la saisie.
                guessed = mimetypes.guess_type(document.file_name)[0] if document.file_name else False
                document.mimetype = guessed or False

    @api.depends('file_name', 'url', 'type')
    def _compute_extension(self):
        for document in self:
            source = document.file_name if document.type == 'file' else (document.url or '')
            extension = os.path.splitext(source or '')[1].lstrip('.').lower()
            document.extension = extension[:16] or False

    @api.depends('file_size')
    def _compute_file_size_human(self):
        for document in self:
            size = document.file_size or 0
            if not size:
                document.file_size_human = "—"
                continue
            for unit in ("o", "Ko", "Mo", "Go"):
                if size < 1024 or unit == "Go":
                    document.file_size_human = f"{size:.0f} {unit}" if unit == "o" else f"{size:.1f} {unit}"
                    break
                size /= 1024.0

    @api.constrains('type', 'url')
    def _check_url(self):
        for document in self:
            if document.type == 'url' and not document.url:
                raise ValidationError(_("Un lien externe doit porter une adresse."))

    @api.onchange('file_name')
    def _onchange_file_name(self):
        # Un document sans nom explicite prend celui du fichier : eviter une
        # liste de « Nouveau document » indistinguables.
        if self.file_name and (not self.name or self.name == _("Nouveau document")):
            self.name = os.path.splitext(self.file_name)[0]

    def action_open_url(self):
        self.ensure_one()
        if self.type != 'url' or not self.url:
            raise ValidationError(_("Ce document n'est pas un lien externe."))
        return {'type': 'ir.actions.act_url', 'url': self.url, 'target': 'new'}
