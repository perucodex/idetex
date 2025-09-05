from odoo import fields, models, api, _

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_chemical = fields.Boolean('is_chemical', compute='_compute_is_chemical_weaving_thread', store=True)
    is_weaving = fields.Boolean('is_weaving', compute='_compute_is_chemical_weaving_thread', store=True)
    is_thread = fields.Boolean('is_thread', compute='_compute_is_chemical_weaving_thread', store=True)
    analysis_id = fields.Many2one('product.analysis', string='Analysis')

    @api.depends('categ_id')
    def _compute_is_chemical_weaving_thread(self):
        for rec in self:
            rec.is_chemical = True if rec.categ_id in self.env.company.chemical_category_ids else False
            rec.is_weaving = True if rec.categ_id in self.env.company.weaving_category_ids else False
            rec.is_thread = True if rec.categ_id in self.env.company.thread_category_ids else False

    def open_analysis(self):
        return self.analysis_id._get_records_action(name=_("Analysis"))
    
class ProductProduct(models.Model):
    _inherit = 'product.product'

    def open_analysis(self):
        return self.product_tmpl_id.analysis_id._get_records_action(name=_("Analysis"))