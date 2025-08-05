from odoo import models, fields, api, _, Command
from odoo.exceptions import UserError
import json

class ProductAnalysis(models.Model):
    _name = 'product.analysis'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Product Analysis'

    name = fields.Char('Name', required=True, copy=False, readonly=False, default=lambda self: _('New'))
    analysis_date = fields.Date('Analysis Date', required=True, default=lambda self: fields.Date.context_today(self))
    partner_id = fields.Many2one('res.partner', string='Customer', ondelete='restrict')
    product_description = fields.Char('Product Description')
    # equipment_id = fields.Many2one('maintenance.equipment.type', string='Equipment', ondelete='restrict')
    gauge_id = fields.Many2one('product.gauge', string='Gauge')
    needles = fields.Integer('Needles')
    # gauge_id = fields.Many2one(related='gauge_id.gauge_id')
    diameter = fields.Integer('Diameter')
    feeders = fields.Integer('Feeders')
    column_qty = fields.Integer('Column Qty')
    width = fields.Float('Analysis Width', compute='_compute_width')
    density = fields.Integer('Analysis Density')
    product_appearance_id = fields.Many2one('product.appearance', string='Appearance', ondelete='restrict')
    product_family_id = fields.Many2one('product.family', string='Family', ondelete='restrict')
    product_fiber_id = fields.Many2one('product.fiber', string='Fiber', ondelete='restrict')
    product_title_id = fields.Many2one('product.title', string='Title', ondelete='restrict')
    product_code = fields.Char('Product Code', readonly=True, copy=False)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
        required=True
    )
    notes = fields.Text('Notes')
    fiber_ids = fields.One2many('analysis.fiber', 'analysis_id', string='Fibers')
    routing_ids = fields.One2many('analysis.routing.line', 'analysis_id', string='Lines')
    user_id = fields.Many2one('res.users','Prepared by',default=lambda self: self.env.user)
    state = fields.Selection([
        ('test', 'Test'),
        ('done', 'Done'),
        ('tech', 'Technical'),
    ], string='state', default='test')
    ligament_row = fields.Integer("Rows",default=0)
    ligament_column = fields.Integer("Columns",default=0)
    ligament_join_row_column = fields.Char("Union")
    grid_data = fields.Text(string="Data Widget")
    technical_sheet_id = fields.Many2one('technical.sheet', string='Technical Sheet')

    @api.depends('needles','column_qty')
    def _compute_width(self):
        for rec in self:
            if rec.column_qty and rec.needles:
                rec.width = rec.needles * 2.54 / rec.column_qty
            else:
                rec.width = 0

    @api.onchange('product_family_id','product_fiber_id','product_title_id','gauge_id','product_appearance_id','width','density')
    def _onchange_product_code(self):
        for rec in self:
            rec.product_code = (rec.product_family_id.code or '') + \
                    (rec.product_title_id.code or '') + \
                    (rec.product_fiber_id.code or '') + \
                    (rec.gauge_id.code or '') + \
                    (rec.product_appearance_id.code or '') + \
                    (str(int(rec.width)).replace('.','') or '') + \
                    (str(int(rec.density)).replace('.','') or '')
                
    @api.onchange('gauge_id')
    def _onchange_gauge_id(self):
        for rec in self:
            rec.needles = rec.gauge_id.needles
            rec.diameter = rec.gauge_id.diameter
            rec.feeders = rec.gauge_id.feeders

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
    
    def action_done(self):
        self.state = 'done'

    def action_create_technical_sheet(self):
        self.technical_sheet_id = self.env['technical.sheet'].create({
            'analysis_id': self.id,
            'fabric_composition': ' '.join([
                f'{round(f.percentage * 100)}% {f.product_template_id.name}'
                for f in self.fiber_ids if f.product_template_id
            ]),
            'density': self.density,
            'width': self.width,
            'gauge_id': self.gauge_id.id,
            'analysis_id': self.id,
            'route_line_ids': [Command.create({
                'operation_id': route.operation_id.id,
                'line_parameter_ids': [Command.create({'name': param.name}) for param in route.operation_id.parameter_ids],
            }) for route in self.routing_ids]
        })
        self.state = 'tech'

    # def action_product(self):
    #     self.product_id = self.env['product.template'].create({
    #         'name': self.product_description,
    #         'default_code': self.product_code,
    #         'uom_id': self.env.ref('uom.product_uom_kgm').id,
    #         'uom_po_id': self.env.ref('uom.product_uom_kgm').id,
    #         'categ_id': self.env.company.weaving_category_ids[0].id if self.env.company.weaving_category_ids else False,
    #         'route_ids': [Command.link(self.env.ref('mrp.route_warehouse0_manufacture').id)],
    #     })
    #     self.product_id.bom_ids.create({
    #         'product_tmpl_id': self.product_id.id,
    #         'product_uom_id': self.product_id.uom_id.id,
    #         'bom_line_ids': [Command.create({'product_id': p.id}) for p in self.fiber_ids.product_template_id],
    #         'operation_ids': [Command.create({
    #             'name': ar.operation_id.name,
    #             'operation_id': ar.operation_id.id,
    #             'workcenter_id': ar.workcenter_id.id
    #         }) for ar in self.routing_ids.sorted(key=lambda o: o.sequence)],
    #     })
    #     self.state = 'product'

    def action_return(self):
        self.state = 'done' if self.state == 'tech' else 'test'
    
    # def open_product(self):
    #     return self.product_id._get_records_action(name=_("Product"))

    def open_tech(self):
        return self.technical_sheet_id._get_records_action(name=_("Technical Sheet"))
    
    def action_generate(self):
        row = self.ligament_row
        column = self.ligament_column
        if not row or row <= 0:
            raise UserError("Row number must be greater than 0")
        if not column or column <= 0:
            raise UserError("Column number must be greater than 0")
        self.ligament_join_row_column = "%s, %s"%(row,column)
        self.grid_data = ''

    def get_svg_grid(self):
        """
        Devuelve una lista de filas, donde cada fila es una lista de celdas,
        y cada celda es un dict con 'svg0' y 'svg1' (contenido SVG o cadena vacía).
        Ejemplo de retorno:
        [
          [ {'svg0': '<svg...>', 'svg1': ''}, {...}, ... ],  # fila 0
          [ {...}, {...}, ... ],                             # fila 1
        ]
        """
        self.ensure_one()
        try:
            raw = json.loads(self.grid_data or "{}")
        except Exception:
            raw = {}

        # Traemos todos los SVGs de golpe
        svg_ids = set(raw.values())
        svg_map = {
            rec.id: (rec.svg_content or "")
            for rec in self.env['configurate.svg.example'].browse(svg_ids)
        }

        grid = []
        for r in range(self.ligament_row or 0):
            row = []
            for c in range(self.ligament_column or 0):
                key0 = f"{r}_0_{c}"
                key1 = f"{r}_1_{c}"
                row.append({
                    'svg0': svg_map.get(raw.get(key0), ""),
                    'svg1': svg_map.get(raw.get(key1), ""),
                })
            grid.append(row)
        return grid
    
class AnalysisFiber(models.Model):
    _name = 'analysis.fiber'
    _description = 'Analysis Fibers'

    analysis_id = fields.Many2one('product.analysis', string='Product Analysis', ondelete='restrict')
    sequence = fields.Integer('Sequence')
    system_type = fields.Selection([
        ('ne', 'Número inglés'),
        ('dn', 'Denier'),
        ('tex', 'Tex'),
        ('dtex', 'Decitex'),
        ('nm', 'Número métrico'),
    ], string='System Type', default='ne')
    length = fields.Float('Mesh Length', compute='_compute_length_average')
    weight = fields.Float('Weight', digits=(12,6))
    thread_qty = fields.Integer('Thread Quantity')
    thread_title = fields.Float('Thread Title', compute='_compute_thread_title')
    product_template_id = fields.Many2one('product.template', string='Thread', domain=lambda self: [('categ_id', 'in', self.env.company.thread_category_ids.ids)], ondelete='restrict')
    percentage = fields.Float('Percentage', compute='_compute_percentage')
    line_ids = fields.One2many('analysis.fiber.line', 'analysis_fiber_id', string='Lines')

    @api.depends('line_ids')
    def _compute_length_average(self):
        for rec in self:
            if rec.line_ids:
                rec.length = sum(rec.line_ids.mapped('length')) / len(rec.line_ids)
            else:
                rec.length = 0

    @api.depends('system_type','length','weight','thread_qty')
    def _compute_thread_title(self):
        for rec in self:
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
                rec.thread_title = (w * 1000) / l if l else 1
            elif rec.system_type == 'dtex':
                rec.thread_title = (w * 10000) / l if l else 1
            elif rec.system_type == 'dn':
                rec.thread_title = (w * 9000) / l if l else 1
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

    analysis_fiber_id = fields.Many2one('analysis.fiber', string='Analysis Fiber')
    length = fields.Float('Mesh Length')

class AnalysisRouteLine(models.Model):
    _name = 'analysis.routing.line'
    _description = 'Analysis Routing Line'

    sequence = fields.Integer('Sequence')
    analysis_id = fields.Many2one('product.analysis', string='Product Analysis')
    operation_id = fields.Many2one('mrp.routing.workcenter.operation', string='Operation Name', ondelete='restrict')
    workcenter_id = fields.Many2one(related='operation_id.workcenter_id')