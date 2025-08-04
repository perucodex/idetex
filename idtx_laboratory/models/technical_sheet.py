from odoo import models, fields, api, _, Command

class TechnicalSheet(models.Model):
    _name = 'technical.sheet'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Technical Sheet'

    name = fields.Char('Name', required=True, copy=False, readonly=False, default=lambda self: _('New'))
    technical_date = fields.Date('Technical Date', required=True, default=lambda self: fields.Date.context_today(self))
    analysis_id = fields.Many2one('product.analysis', string='Product Analysis', ondelete='restrict')
    product_code = fields.Char('Product Code', readonly=True, copy=False)
    # Tejido
    program = fields.Char('Program')
    fabric_composition = fields.Char('Fabric Composition')
    atx = fields.Char('ATX')
    density = fields.Integer('Density')
    width = fields.Float('Width')
    gauge_id = fields.Many2one('product.gauge', string='Gauge')
    first_wash_shrinkage = fields.Char('First Wash Shrinkage')
    first_wash_twist = fields.Char('First Wash Twist')
    yield_meter = fields.Float('Yield')
    scrap = fields.Float('Scrap')
    weave_type = fields.Selection([
        ('open', 'Open'),
        ('tubular', 'Tubular'),
    ], string='Weave Type')
    batch = fields.Char('Batch')
    notes = fields.Text('Notes')
    # Acabado
    # Campos por agregar
    # Data
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
        required=True
    )
    product_id = fields.Many2one('product.template', string='Product')
    state = fields.Selection([
        ('test', 'Test'),
        ('done', 'Done'),
        ('prod', 'Product'),
    ], string='state', default='test')
    user_id = fields.Many2one('res.users','Prepared by',default=lambda self: self.env.user)
    route_line_ids = fields.One2many('technical.route.line', 'technical_id', string='Route Line')

    @api.onchange('gauge_id','width','density')
    def _onchange_product_code(self):
        for rec in self:
            rec.product_code = (rec.analysis_id.product_family_id.code or '') + \
                    (rec.analysis_id.product_title_id.code or '') + \
                    (rec.analysis_id.product_fiber_id.code or '') + \
                    (rec.gauge_id.code or '') + \
                    (rec.analysis_id.product_appearance_id.code or '') + \
                    (str(int(rec.width)).replace('.','') or '') + \
                    (str(int(rec.density)).replace('.','') or '')
                
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
    
    def action_product(self):
        self.product_id = self.env['product.template'].create({
            'name': self.analysis_id.product_description,
            'default_code': self.product_code,
            'uom_id': self.env.ref('uom.product_uom_kgm').id,
            'uom_po_id': self.env.ref('uom.product_uom_kgm').id,
            'categ_id': self.env.company.weaving_category_ids[0].id if self.env.company.weaving_category_ids else False,
            'route_ids': [Command.link(self.env.ref('mrp.route_warehouse0_manufacture').id)],
        })
        self.product_id.bom_ids.create({
            'product_tmpl_id': self.product_id.id,
            'product_uom_id': self.product_id.uom_id.id,
            'bom_line_ids': [Command.create({'product_id': p.id}) for p in self.analysis_id.fiber_ids.product_template_id],
            'operation_ids': [Command.create({
                'name': route.operation_id.name,
                'operation_id': route.operation_id.id,
                'workcenter_id': route.workcenter_id.id
            }) for route in self.analysis_id.routing_ids.sorted(key=lambda o: o.sequence)],
        })
        self.state = 'prod'

    def action_done(self):
        self.state = 'done'

    def action_return(self):
        self.state = 'done' if self.state == 'prod' else 'test'

    def open_product(self):
        return self.product_id._get_records_action(name=_("Product"))

class TechnicalRouteLine(models.Model):
    _name = 'technical.route.line'
    _description = 'Technical Route Line'

    sequence = fields.Integer('Sequence')
    technical_id = fields.Many2one('technical.sheet', string='Technical Sheet')
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
    value = fields.Char('Value')