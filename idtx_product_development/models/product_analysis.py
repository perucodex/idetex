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
    ficha = fields.Char('Ficha')
    codpro = fields.Char('CodigoProductoBD')
    gauge_id = fields.Many2one('product.gauge', string='Gauge')
    needles = fields.Integer('Needles')
    diameter = fields.Integer('Diameter')
    feeders = fields.Integer('Feeders')
    weave_type = fields.Selection([
        ('open', 'Open'),
        ('tubu', 'Tubular'),
        ('rect', 'Rectilinear'),
        ('othe', 'Other'),
    ], string='Weave Type')
    column_qty = fields.Integer('Column Qty')
    width = fields.Float('Analysis Width', compute='_compute_width')
    standard_width = fields.Float('Standard Width')
    density = fields.Integer('Analysis Density')
    product_appearance_id = fields.Many2one('product.appearance', string='Appearance', ondelete='restrict')
    product_family_id = fields.Many2one('product.family', string='Family', ondelete='restrict')
    product_fiber_id = fields.Many2one('product.fiber', string='Fiber', ondelete='restrict')
    product_title_id = fields.Many2one('product.title', string='Title', ondelete='restrict')
    product_code = fields.Char('Product Code', readonly=True, copy=False)
    product_id = fields.Many2one('product.template', string='Product')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
        required=True
    )
    notes = fields.Text('Notes')
    # fiber_ids = fields.One2many('analysis.fiber', 'analysis_id', string='Fibers')
    weaving_data_ids = fields.One2many('analysis.weaving.data', 'analysis_id', string='Weaving Data')
    routing_ids = fields.One2many('analysis.routing.line', 'analysis_id', string='Lines')
    user_id = fields.Many2one('res.users','Prepared by',default=lambda self: self.env.user)
    state = fields.Selection([
        ('test', 'Test'),
        ('prod', 'Product'),
    ], string='State', default='test')
    ligament_row = fields.Integer('Rows',default=0)
    ligament_column = fields.Integer('Columns',default=0)
    ligament_join_row_column = fields.Char('Union')
    grid_data = fields.Text(string='Data Widget')
    # technical_sheet_id = fields.Many2one('technical.sheet', string='Technical Sheet')
    technical_sheet_count = fields.Integer(string='Technical Sheet Count', compute='_get_technical_sheets')
    technical_sheet_ids = fields.One2many('technical.sheet', 'analysis_id', string='Technical Sheet')
    mrp_base_process_id = fields.Many2one('mrp.base.process', string='Base Process')
    # Precio de tejido por producto
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.ref('base.USD'))
    weaving_price = fields.Monetary('Weaving Price')
    # Manejo de producto por estado
    production_state = fields.Char(string='Production State')
    # Tolerancia de tela
    width_tolerance = fields.Float('Width Tolerance')
    density_tolerance = fields.Float('Density Tolerance')
    width_wash_shrinkage_tolerance_from = fields.Float('Width Wash Shrinkage Tolerance From')
    width_wash_shrinkage_tolerance_to = fields.Float('Width Wash Shrinkage Tolerance To')
    lenght_wash_shrinkage_tolerance_from = fields.Float('Length Wash Shrinkage Tolerance From')
    lenght_wash_shrinkage_tolerance_to = fields.Float('Length Wash Shrinkage Tolerance To')
    density_stability_twisting_id = fields.Many2one('density.stability.twisting', string='Density Stability Twisting Data')

    _check_standard_width = models.Constraint(
        'CHECK(standard_width > 0)',
        'Standard width should be grather than zero.',
    )
    _check_density = models.Constraint(
        'CHECK(density > 0)',
        'Density should be grather than zero.',
    )
    _check_weaving_price = models.Constraint(
        'CHECK(weaving_price > 0)',
        'Weaving Price should be grather than zero.',
    )

    _product_code_unique = models.Constraint(
        'unique(product_code)',
        'Product code must be unique!',
    )

    @api.onchange('mrp_base_process_id')
    def _onchange_mrp_base_process_id(self):
        if not self.mrp_base_process_id:
            self.routing_ids = [Command.clear()]
            return
        commands = [Command.clear()]
        commands += [
            Command.create({
                'operation_id': line.operation_id.id,
            })
            for line in self.mrp_base_process_id.process_ids
        ]
        self.routing_ids = commands
    
    @api.depends('technical_sheet_ids')
    def _get_technical_sheets(self):
        for rec in self:
            rec.technical_sheet_count = len(rec.technical_sheet_ids)

    @api.depends('needles','column_qty')
    def _compute_width(self):
        for rec in self:
            if rec.column_qty and rec.needles:
                rec.width = rec.needles * 2.54 / rec.column_qty
            else:
                rec.width = 0

    @api.onchange('product_family_id','product_fiber_id','product_title_id','gauge_id','product_appearance_id','standard_width','density')
    def _onchange_product_code(self):
        for rec in self:
            rec.product_code = (rec.product_family_id.code or '00') + \
                    (rec.product_title_id.code or '00') + \
                    (rec.product_fiber_id.code or '0') + \
                    (rec.gauge_id.code or '00') + \
                    (rec.product_appearance_id.code or '00') + \
                    (str(int(rec.standard_width)) or '000').zfill(3) + \
                    (str(int(rec.density)) or '000').zfill(3)
            rec.product_id.default_code = rec.product_code
                
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
            if vals.get('name', _('New')) == _('New'):
                seq_date = fields.Datetime.context_timestamp(
                    self, fields.Datetime.to_datetime(vals['analysis_date'])
                ) if 'analysis_date' in vals else None
                vals['name'] = self.env['ir.sequence'].with_company(vals.get('company_id')).next_by_code(
                    'product.analysis', sequence_date=seq_date) or _('New')
            vals['density_stability_twisting_id'] = self.env['density.stability.twisting'].create({}).id
        return super().create(vals_list)
        
    def action_product(self):
        # Modificamos la línea porque los rectilíneos tambien se venden por kilo
        uom = self.env.ref('uom.product_uom_kgm') #if self.weave_type != 'rect' else self.env.ref('uom.product_uom_unit')
        self.product_id = self.env['product.template'].create({
            'name': self.product_description,
            'is_storable': True,
            'is_weaving': True,
            'tracking': 'lot',
            'default_code': self.product_code,
            'uom_id': uom.id,
            'categ_id': self.env.company.weaving_category_ids[0].id if self.env.company.weaving_category_ids else False,
            'route_ids': [Command.link(self.env.ref('mrp.route_warehouse0_manufacture').id)],
            'analysis_id': self.id,
        })
        self.state = 'prod'

    def action_create_technical_sheet(self):
        for rec in self.weaving_data_ids.filtered(lambda w: not w.technical_sheet_id):
            rec.technical_sheet_id = self.env['technical.sheet'].create({
                'analysis_id': self.id,
                'product_code': self.product_code,
                'product_id': self.product_id.id,
                'partner_id': rec.partner_id.id,
                'fabric_composition': '\n'.join([
                    f'{round(f.percentage * 100)}% {f.product_template_id.name}'
                    for f in rec.fiber_ids if f.product_template_id
                ]).strip(),
                'density': self.density,
                'width': self.standard_width,
                'gauge_id': self.gauge_id.id,
                'stylo': rec.stylo,
                'route_line_ids': [Command.create({
                    'operation_id': route.operation_id.id,
                    'line_parameter_ids': [Command.create({'name': param.name}) for param in route.operation_id.parameter_ids],
                }) for route in self.routing_ids.sorted(key=lambda r: r.sequence)],
            })
            self.technical_sheet_ids += rec.technical_sheet_id
            # bom_id = self.env['mrp.bom'].create({
            #     'product_tmpl_id': self.product_id.id,
            #     'product_uom_id': self.product_id.uom_id.id,
            #     'code': rec.stylo,
            #     'technical_sheet_id': rec.technical_sheet_id.id,
            #     'operation_ids': [Command.create({
            #         'name': route.operation_id.name,
            #         'operation_id': route.operation_id.id,
            #         'workcenter_id': route.workcenter_id.id,
            #     }) for route in self.routing_ids.sorted(key=lambda r: r.sequence)],
            #     'bom_line_ids': [Command.create({'product_id': p.id}) for p in rec.fiber_ids.product_template_id.product_variant_id],
            # })
            # # Consumir el hilo en tejeduria
            # # Solo si existe un producto de hilado
            # if any(p.is_thread for p in rec.fiber_ids.product_template_id.product_variant_id):
            #     weaving_operation = bom_id.operation_ids.filtered(lambda o: o.operation_id.workcenter_id.operation_type == 'weaving')
            #     if weaving_operation:
            #         for l in bom_id.bom_line_ids:
            #             l.operation_id = weaving_operation
            #     else:
            #         # Si hay productos para tejer y no se encontró un proceso de tejido
            #         if bom_id.bom_line_ids:
            #             raise UserError(_('There is no weaving operation in bom. Please check your product routing!'))
            # self.product_id.bom_ids += bom_id

    def action_done(self):
        self.state = 'done'

    def action_return(self):
        self.product_id.bom_ids.unlink()
        self.product_id.unlink()
        self.technical_sheet_ids.unlink()
        self.state = 'test'

    def open_tech(self):
        return self.technical_sheet_ids._get_records_action(name=_('Technical Sheet'))
    
    def open_product(self):
        return self.product_id._get_records_action(name=_('Product'))
    
    def action_generate(self):
        row = self.ligament_row
        column = self.ligament_column
        if not row or row <= 0:
            raise UserError('Row number must be greater than 0')
        if not column or column <= 0:
            raise UserError('Column number must be greater than 0')
        self.ligament_join_row_column = '%s, %s'%(row,column)
        self.grid_data = ''

    def get_svg_grid(self):
        self.ensure_one()
        try:
            raw = json.loads(self.grid_data or '{}')
        except Exception:
            raw = {}

        # Traemos todos los SVGs de golpe
        svg_ids = set(raw.values())
        svg_map = {
            rec.id: (rec.svg_content or '')
            for rec in self.env['configurate.svg.example'].browse(svg_ids)
        }

        grid = []
        for r in range(self.ligament_row or 0):
            row = []
            for c in range(self.ligament_column or 0):
                key0 = f'{r}_0_{c}'
                key1 = f'{r}_1_{c}'
                map0 = svg_map.get(raw.get(key0), '')
                map1 = svg_map.get(raw.get(key1), '')
                if map0 or map1:
                    row.append({
                        'svg0': map0,#svg_map.get(raw.get(key0), ''),
                        'svg1': map1,#svg_map.get(raw.get(key1), ''),
                    })
            if row:
                grid.append(row)
        return grid
        
    # Funcion escondida para actualizar los registros de densidad y estabilidad de torsión, para pruebas y desarrollo solamente
    def action_update(self):
        analysis = self.env['product.analysis'].search([])
        for rec in analysis:
            rec.density_stability_twisting_id = self.env['density.stability.twisting'].create({
                'density': 0.2,
                'width': 0.2,
                'width_shrinkage_from': 0.2,
                'width_shrinkage_to': 0.2,
                'length_shrinkage_from': 0.2,
                'length_shrinkage_to': 0.2,
                'twist': 0.2,
            })

class AnalysisWeavingData(models.Model):
    _name = 'analysis.weaving.data'
    _description = 'Analysis Weaving Data'

    analysis_id = fields.Many2one('product.analysis', string='Product Analysis', ondelete='restrict')
    partner_id = fields.Many2one('res.partner', string='Customer', ondelete='restrict')
    stylo = fields.Char('Stylo')
    fiber_ids = fields.One2many('analysis.fiber', 'weaving_data_id', string='Fibers')
    technical_sheet_id = fields.Many2one('technical.sheet', string='Technical Sheet')
    notes = fields.Text('Weaving Notes')

    @api.onchange('analysis_id')
    def _onchange_analysis_id(self):
        if self.analysis_id and self.analysis_id.partner_id and not self.partner_id:
            self.partner_id = self.analysis_id.partner_id
    
    def open_tech(self):
        return self.technical_sheet_id._get_records_action(name=_('Technical Sheet'))
    
    def print_analysis_report(self):
        return self.env.ref('idtx_product_development.action_report_product_analysis').report_action(self)
    
    def unlink(self):
        self.technical_sheet_id.unlink()
        return super().unlink()
    
class AnalysisFiber(models.Model):
    _name = 'analysis.fiber'
    _description = 'Analysis Fibers'

    # analysis_id = fields.Many2one('product.analysis', string='Product Analysis', ondelete='restrict')
    weaving_data_id = fields.Many2one('analysis.weaving.data', string='Weaving Data Parent')
    sequence = fields.Integer('Sequence')
    system_type = fields.Selection([
        ('ne', 'English number (ne)'),
        ('dn', 'Denier (dn)'),
        ('tex', 'Tex (tex)'),
        ('dtex', 'Decitex (dtex)'),
        ('nm', 'Metric number (nm)'),
    ], string='System Type', default='ne')
    length = fields.Float('Mesh Length', compute='_compute_length_average')
    weight = fields.Float('Weight', digits=(12,6))
    thread_qty = fields.Integer('Thread Quantity')
    thread_title = fields.Float('Thread Title', compute='_compute_thread_title')
    product_template_id = fields.Many2one('product.template', string='Thread', domain=lambda self: [('categ_id', 'in', self.env.company.thread_category_ids.ids)], ondelete='restrict')
    ligament_id = fields.Many2one('ligament.type', string='Ligament')
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
                rec.percentage = rec.weight / sum(rec.weaving_data_id.fiber_ids.mapped('weight'))
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

    @api.constrains('analysis_id', 'operation_id')
    def _check_unique_weaving_per_analysis(self):
        for line in self:
            if not line.analysis_id or not line.operation_id:
                continue
            if line.operation_id.operation_type != 'weaving':
                continue

            other_weaving = line.analysis_id.routing_ids.filtered(lambda l: l.id != line.id and l.operation_id and l.operation_id.operation_type == 'weaving')
            if other_weaving:
                raise UserError(_('Only one weaving operation is allowed'))