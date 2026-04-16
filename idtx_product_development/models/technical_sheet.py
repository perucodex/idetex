from odoo import models, fields, api, _
from odoo.fields import Command
from odoo.exceptions import UserError
# from .covatex import MySQLConnector
import logging

_logger = logging.getLogger(__name__)

class TechnicalSheet(models.Model):
    _name = 'technical.sheet'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Technical Sheet'

    name = fields.Char('Name', required=True, copy=False, readonly=False, default=lambda self: _('New'))
    technical_date = fields.Date('Technical Date', required=True, default=lambda self: fields.Date.context_today(self))
    analysis_id = fields.Many2one('product.analysis', string='Product Analysis', ondelete='restrict')
    product_code = fields.Char('Product Code', readonly=True, copy=False)
    partner_id = fields.Many2one('res.partner', string='Customer', ondelete='restrict')
    # Tejido
    stylo = fields.Char('Stylo')
    program = fields.Char('Program')
    fabric_composition = fields.Text('Fabric Composition')
    atx = fields.Char('ATX')
    density = fields.Integer('Density')
    width = fields.Float('Width')
    gauge_id = fields.Many2one('product.gauge', string='Gauge')
    first_wash_shrinkage = fields.Char('First Wash Shrinkage')
    first_wash_twist = fields.Char('First Wash Twist')
    yield_meter = fields.Float('Yield', compute='_compute_yield_meter')
    scrap = fields.Float('Weaving Scrap', default=0.01)
    prod_scrap = fields.Float('Production Scrap', compute='_compute_prod_scrap')
    weave_type = fields.Selection(related='analysis_id.weave_type', store=True)
    mesh_length = fields.Float('Mesh Length')
    # Datos de crudo
    raw_width = fields.Float('Raw Width')
    raw_density = fields.Float('Raw Density')
    raw_widening = fields.Float('Widening')
    # Datos de acabado
    finish_width = fields.Float('Finish Width')
    finish_density = fields.Float('Finish Density')
    finish_yield = fields.Float('Finish Yield')
    notes = fields.Text('Notes')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
        required=True
    )
    product_id = fields.Many2one('product.template', string='Product')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done'),
        ('prod', 'Production'),
    ], string='State', default='draft')
    # Manejo de producto por estado
    production_state = fields.Char(string='Production State')
    user_id = fields.Many2one('res.users','Prepared by',default=lambda self: self.env.user)
    size_chart_ids = fields.One2many('technical.size.line', 'technical_id', string='Size Chart')
    route_line_ids = fields.One2many('technical.route.line', 'technical_id', string='Route Line')
    bom_id = fields.Many2one('mrp.bom', string='LdM')
    mrp_base_process_id = fields.Many2one(related='analysis_id.mrp_base_process_id')

    @staticmethod
    def _extract_tolerance_ids_from_commands(commands):
        tolerance_ids = set()
        for cmd in commands or []:
            if not isinstance(cmd, (list, tuple)) or len(cmd) < 1:
                continue
            operation = cmd[0]
            if operation == Command.CREATE and len(cmd) > 2 and isinstance(cmd[2], dict):
                tol_id = cmd[2].get('tolerance_id')
                if tol_id:
                    tolerance_ids.add(tol_id)
            elif operation == Command.LINK and len(cmd) > 1 and cmd[1]:
                tolerance_ids.add(cmd[1])
            elif operation == Command.SET and len(cmd) > 2 and isinstance(cmd[2], (list, tuple)):
                tolerance_ids.update([tol_id for tol_id in cmd[2] if tol_id])
        return tolerance_ids

    def _compute_prod_scrap(self):
        for rec in self:
            rec.prod_scrap = 0.09

    @api.depends('density','width')
    def _compute_yield_meter(self):
        for rec in self:
            rec.yield_meter = 1000 / (rec.density * (rec.width / 100)) if (rec.density and rec.width) else 1

    #=== CRUD METHODS ===#

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _("New")) == _("New"):
                seq_date = fields.Datetime.context_timestamp(
                    self, fields.Datetime.to_datetime(vals['technical_date'])
                ) if 'technical_date' in vals else None
                vals['name'] = self.env['ir.sequence'].with_company(vals.get('company_id')).next_by_code(
                    'technical.sheet', sequence_date=seq_date) or _("New")
        return super().create(vals_list)
    
    def action_done(self):
        self.state = 'done'
        analysis_line = self.analysis_id.weaving_data_ids.filtered(lambda w: w.technical_sheet_id == self)
        bom_id = self.env['mrp.bom'].create({
            'product_tmpl_id': self.product_id.id,
            'product_uom_id': self.product_id.uom_id.id,
            'code': analysis_line.stylo,
            'technical_sheet_id': self.id,
            'operation_ids': [Command.create({
                'name': route.operation_id.name,
                'operation_id': route.operation_id.id,
                'workcenter_id': route.workcenter_id.id,
            }) for route in self.route_line_ids.sorted(key=lambda r: r.sequence)],
            'bom_line_ids': [Command.create({'product_id': f.product_template_id.product_variant_id.id, 'product_qty': f.percentage}) for f in analysis_line.fiber_ids if f.product_template_id and f.percentage],
        })
        # Consumir el hilo en tejeduria
        # Solo si existe un producto de hilado
        if any(p.is_thread for p in analysis_line.fiber_ids.product_template_id.product_variant_id):
            weaving_operation = bom_id.operation_ids.filtered(lambda o: o.operation_id.operation_type == 'weaving')
            if weaving_operation:
                for l in bom_id.bom_line_ids:
                    l.operation_id = weaving_operation
            else:
                # Si hay productos para tejer y no se encontró un proceso de tejido
                if bom_id.bom_line_ids:
                    raise UserError(_('There is no weaving operation in bom. Please check your product routing!'))
        self.product_id.bom_ids += bom_id
        self.bom_id = bom_id

    def action_return(self):
        self.state = 'done' if self.state == 'prod' else 'draft'

class TechnicalSizeLine(models.Model):
    _name = 'technical.size.line'
    _description = 'Technical Size Line'
    _rec_name = 'size'

    technical_id = fields.Many2one('technical.sheet', string='Technical Sheet')
    sequence = fields.Integer('Sequence')
    size = fields.Char('Size')
    length = fields.Float('Length')
    width = fields.Float('Width')
    needles = fields.Integer('Needles')
    ne = fields.Char('NE')
    plies = fields.Integer('Plies')
    tubular = fields.Float('Tubular')
    body = fields.Float('Body')

class TechnicalRouteLine(models.Model):
    _name = 'technical.route.line'
    _description = 'Technical Route Line'

    technical_id = fields.Many2one('technical.sheet', string='Technical Sheet')
    sequence = fields.Integer('Sequence')
    operation_id = fields.Many2one('mrp.routing.workcenter.operation', string='Operation Name', ondelete='restrict')
    workcenter_id = fields.Many2one(related='operation_id.workcenter_id')
    line_parameter_ids = fields.One2many('route.line.parameter', 'technical_route_id', string='Line Parameter')
    
    @api.onchange('operation_id')
    def _onchange_operation_id(self):
        for rec in self:
            rec.line_parameter_ids.unlink()
            rec.line_parameter_ids = [Command.create({'name': param.name}) for param in rec.operation_id.parameter_ids]

class RouteLineParameter(models.Model):
    _name = 'route.line.parameter' 
    _description = 'Route Line Parameter'

    technical_route_id = fields.Many2one('technical.route.line', string='Technical Routing Line')
    name = fields.Char('Parameter')
    value = fields.Text('Value')
    is_observation = fields.Boolean('Observación?')
