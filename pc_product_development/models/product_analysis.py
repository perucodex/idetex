from odoo import models, fields, api, _

class ProductAnalysis(models.Model):
    _name = 'product.analysis'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Product Analysis'

    name = fields.Char('Name', required=True, copy=False, readonly=False, default=lambda self: _('New'))
    analysis_date = fields.Date('Analysis Date')
    partner_id = fields.Many2one('res.partner', string='Customer')
    weaving_type = fields.Selection([
        ('jsy', 'Jersey'),
        ('rib', 'Rib'),
        ('int', 'Interlock'),
    ], string='Weaving Type')
    product_description = fields.Char('Product Description')
    equipment_id = fields.Many2one('maintenance.equipment', string='Equipment')
    needles = fields.Integer('Needles', related='equipment_id.needles')
    column_number = fields.Integer('Column Number')
    width = fields.Float('Width', compute='_compute_width')
    density = fields.Float('Density')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
        required=True
    )
    fiber_ids = fields.One2many('analysis.fiber', 'analysis_id', string='Fibers')

    @api.depends('needles','column_number')
    def _compute_width(self):
        for rec in self:
            if rec.column_number and rec.needles:
                rec.width = rec.needles * 2.54 / rec.column_number
            else:
                rec.width = 0

    #=== CRUD METHODS ===#

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _("New")) == _("New"):
                seq_date = fields.Datetime.context_timestamp(
                    self, fields.Datetime.to_datetime(vals['analysis_date'])
                ) if 'analysis_date' in vals else None
                vals['name'] = self.env['ir.sequence'].with_company(vals.get('company_id')).next_by_code(
                    'product.analysis', sequence_date=seq_date) or _("New")

        return super().create(vals_list)
    
class AnalysisFiber(models.Model):
    _name = 'analysis.fiber'
    _description = 'Analysis Fibers'

    analysis_id = fields.Many2one('product.analysis', string='Analysis')
    system_type = fields.Selection([
        ('ne', 'Ne - Número inglés'),
        ('dn', 'Denier'),
        ('tex', 'Tex'),
        ('dtex', 'Decitex'),
        ('nm', 'Nm - Número métrico'),
    ], string='System Type')
    length = fields.Float('Mesh Length', compute='_compute_length_average')
    weight = fields.Float('Weight')
    thread_qty = fields.Integer('Thread Quantity')
    thread_title = fields.Float('Thread Title', compute='_compute_thread_title')
    comercial_thread_title = fields.Char('Comercial Thread Title')
    percentage = fields.Float('Percentage', compute='_compute_percentage')
    line_ids = fields.One2many('analysis.fiber.line', 'analysis_id', string='Lines')

    @api.depends('line_ids')
    def _compute_length_average(self):
        for rec in self:
            if rec.line_ids:
                rec.length = sum(rec.line_ids.mapped('length')) / len(rec.line_ids)
            else:
                rec.length

    @api.depends('system_type','length','weight')
    def _compute_thread_title(self):
        for rec in self:
            # if rec.length and rec.weight:
            #     rec.thread_title = (rec.length / rec.weight) * 0.59
            # else:
            #     rec.thread_title = 0
            if not rec.length or not rec.weight:
                rec.thread_title = 0.0
                continue

            l = (rec.length * rec.thread_qty) / 10
            w = rec.weight

            if rec.system_type == 'ne':
                rec.thread_title = (l / w) * 0.59
            elif rec.system_type == 'nm':
                rec.thread_title = l / w
            elif rec.system_type == 'tex':
                rec.thread_title = (w * 1000) / l
            elif rec.system_type == 'dtex':
                rec.thread_title = (w * 10000) / l
            elif rec.system_type == 'dn':
                rec.thread_title = (w * 9000) / l
            else:
                rec.thread_title = 0.0

    def _compute_percentage(self):
        for rec in self:
            if rec.weight:
                rec.percentage = rec.weight / sum(rec.analysis_id.fiber_ids.mapped('weight'))
            else:
                rec.percentage = 0

class AnalysisFiberLine(models.Model):
    _name = 'analysis.fiber.line'
    _description = 'Analysis Fiber Lines'

    analysis_id = fields.Many2one('analysis.fiber', string='Analysis Fiber')
    length = fields.Float('Mesh Length')
