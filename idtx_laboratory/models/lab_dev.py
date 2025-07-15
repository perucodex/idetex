from odoo import models, fields, api, _

class LabDev(models.Model):
    _name = 'lab.dev'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Laboratory Development'

    # product_color_id = fields.Many2one('product.color', 'Product Color')
    name = fields.Char('Name', copy=False, default=lambda self: _('New'))
    lab_dev_date = fields.Date('Lab Dev Date', default=fields.Date.context_today)
    # sale_order_line_id = fields.Many2one('sale.order.line', string='Sale Order Line')
    # sale_order_id = fields.Many2one(related='sale_order_line_id.order_id')
    sale_order_id = fields.Many2one('sale.order', string='Sale Order')
    partner_id = fields.Many2one(related='sale_order_id.partner_id')
    product_id = fields.Many2one('product.template','Product')
    recipe_count = fields.Integer('Recipe Count', compute='_compute_recipe_count')
    volume = fields.Float('Volume')
    kilos = fields.Float('Kilos')
    lab_dev_line_ids = fields.One2many('lab.dev.line', 'lab_dev_id', string='Lab Dev Lines')
    color_recipe_ids = fields.One2many(related='lab_dev_line_ids.color_recipe_ids')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('dev', 'Development'),
        ('approved', 'Approved'),
    ], string='State')

    def open_recipes(self):
        return self.lab_dev_line_ids.color_recipe_ids._get_records_action(name=_("Recipes"), context={'group_by': 'product_color_id'})
    
    @api.depends('lab_dev_line_ids')
    def _compute_recipe_count(self):
        for rec in self:
            rec.recipe_count = len(rec.lab_dev_line_ids.color_recipe_ids)
    
    #=== CRUD METHODS ===#

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _("New")) == _("New"):
                seq_date = fields.Datetime.context_timestamp(
                    self, fields.Datetime.to_datetime(vals['lab_dev_date'])
                ) if 'lab_dev_date' in vals else None
                vals['name'] = self.env['ir.sequence'].with_company(vals.get('company_id')).next_by_code(
                    'lab.dev', sequence_date=seq_date) or _("New")

        return super().create(vals_list)
    
class LabDevLine(models.Model):
    _name = 'lab.dev.line'
    _description = 'Laboratory Development Line'

    lab_dev_id = fields.Many2one('lab.dev', string='Lab Dev')
    product_color_id = fields.Many2one('product.color', 'Product Color')
    color_recipe_ids = fields.One2many('color.recipe', 'lab_dev_line_id', string='Recipes')