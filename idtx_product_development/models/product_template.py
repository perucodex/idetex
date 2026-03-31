from odoo import fields, models, api, _
from odoo.exceptions import UserError

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_weaving = fields.Boolean('is_weaving', compute='_compute_product_category', store=True)
    is_thread = fields.Boolean('is_thread', compute='_compute_product_category', store=True)
    analysis_id = fields.Many2one('product.analysis', string='Analysis')
    technical_sheet_count = fields.Integer(string="Technical Sheet Count", compute='_get_technical_sheets')

    @api.onchange('categ_id')
    def _onchange_categ_id(self):
        for rec in self:
            if rec.categ_id and rec.categ_id in self.env.company.weaving_category_ids and not rec.analysis_id:
                raise UserError(_("Products in the weaving category must have an analysis. Please set one before changing the category."))
    
    @api.depends('analysis_id')
    def _get_technical_sheets(self):
        for rec in self:
            rec.technical_sheet_count = len(rec.analysis_id.technical_sheet_ids)

    @api.depends('categ_id')
    def _compute_product_category(self):
        weaving_categories = set(self.env.company.weaving_category_ids)
        thread_categories = set(self.env.company.thread_category_ids)
        for rec in self:
            category = rec.categ_id
            is_weaving = False
            is_thread = False
            while category and not (is_weaving and is_thread):
                if category in weaving_categories:
                    is_weaving = True
                if category in thread_categories:
                    is_thread = True
                category = category.parent_id
            rec.is_weaving = is_weaving
            rec.is_thread = is_thread

    def open_analysis(self):
        return self.analysis_id.technical_sheet_ids._get_records_action(name=_("Technical Sheets"))
        
class ProductProduct(models.Model):
    _inherit = 'product.product'

    def open_analysis(self):
        return self.product_tmpl_id.open_analysis()