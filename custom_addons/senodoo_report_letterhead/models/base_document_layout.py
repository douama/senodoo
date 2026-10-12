from odoo import api, fields, models


class BaseDocumentLayout(models.TransientModel):
    _inherit = 'base.document.layout'

    letterhead_header_image = fields.Image(related='company_id.letterhead_header_image', readonly=False)
    letterhead_footer_image = fields.Image(related='company_id.letterhead_footer_image', readonly=False)
    is_letterhead_layout = fields.Boolean(compute='_compute_is_letterhead_layout')

    @api.depends('report_layout_id')
    def _compute_is_letterhead_layout(self):
        letterhead = self.env.ref('senodoo_report_letterhead.report_layout_letterhead', raise_if_not_found=False)
        for wizard in self:
            wizard.is_letterhead_layout = bool(letterhead) and wizard.report_layout_id == letterhead

    # Les dependances s'ajoutent a celles du parent (resolve_mro) : l'apercu se
    # rafraichit des qu'une image change, comme pour le logo.
    @api.depends('letterhead_header_image', 'letterhead_footer_image')
    def _compute_preview(self):
        return super()._compute_preview()
