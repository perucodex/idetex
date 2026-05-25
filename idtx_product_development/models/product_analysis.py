from odoo import models, fields, api, _, Command
from odoo.exceptions import UserError
import json
import logging
_logger = logging.getLogger(__name__)

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
    standard_width = fields.Integer('Standard Width')
    density = fields.Integer('Analysis Density')
    tilt = fields.Integer('Tilt')
    product_appearance_id = fields.Many2one('product.appearance', string='Appearance', ondelete='restrict')
    product_family_id = fields.Many2one('product.family', string='Family', ondelete='restrict')
    product_fiber_id = fields.Many2one('product.fiber', string='Fiber', ondelete='restrict')
    product_title_id = fields.Many2one('product.title', string='Title', ondelete='restrict')
    product_code = fields.Char('Product Code', readonly=True, copy=False)
    product_id = fields.Many2one('product.template', string='Product', copy=False)
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
    ], string='State', default='test', copy=False, tracking=True)
    ligament_row = fields.Integer('Rows',default=0)
    ligament_column = fields.Integer('Columns',default=0)
    ligament_join_row_column = fields.Char('Union')
    grid_data = fields.Text(string='Data Widget')
    # technical_sheet_id = fields.Many2one('technical.sheet', string='Technical Sheet')
    technical_sheet_count = fields.Integer(string='Technical Sheet Count', compute='_get_technical_sheets')
    technical_sheet_ids = fields.One2many('technical.sheet', 'analysis_id', string='Technical Sheet')
    mrp_base_process_id = fields.Many2one('mrp.base.process', string='Base Process', tracking=True)
    # Precio de tejido por producto
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.ref('base.USD'))
    weaving_price = fields.Monetary('Weaving Price')
    # Tolerancia de tela
    density_stability_twisting_id = fields.Many2one('density.stability.twisting', string='Density Stability Twisting Data', copy=False)
    yield_meter = fields.Float('Yield', compute='_compute_yield_meter')

    _check_standard_width = models.Constraint(
        'CHECK(standard_width > 0)',
        'Standard width should be grather than zero.',
    )
    _check_density = models.Constraint(
        'CHECK(density > 0)',
        'Density should be grather than zero.',
    )
    _check_weaving_price = models.Constraint(
        'CHECK(weaving_price >= 0)',
        'Weaving Price cannot be negative.',
    )

    _product_code_unique = models.Constraint(
        'unique(product_code)',
        'Product code must be unique!',
    )

    @api.depends('density','standard_width')
    def _compute_yield_meter(self):
        for rec in self:
            rec.yield_meter = 1000 / (rec.density * (rec.standard_width / 100)) if (rec.density and rec.standard_width) else 1

    @api.onchange('mrp_base_process_id')
    def _onchange_mrp_base_process_id(self):
        # UI-only feedback: refresh the routing lines as the user changes
        # the base process. The full propagation to technical sheets and
        # BoMs happens in write() so it also fires for programmatic writes.
        if not self.mrp_base_process_id:
            self.routing_ids = [Command.clear()]
            return
        commands = [Command.clear()]
        commands += [
            Command.create({
                'operation_id': line.operation_id.id,
                'sequence': line.sequence,
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
            rec.technical_sheet_ids.write({'product_code': rec.product_code})
                
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

    def write(self, vals):
        # Propagate base process changes to technical sheets and their BoMs.
        # Captured BEFORE super() so we can compare old vs new value.
        if 'mrp_base_process_id' in vals:
            new_bp_id = vals.get('mrp_base_process_id') or False
            # Hard validation: every operation of the new base process MUST
            # have a general TEXPLUS machine assigned. Otherwise production
            # can't proceed downstream, so we block the write entirely.
            self._check_base_process_has_machines(new_bp_id)
            changed = [
                r for r in self
                if (r.mrp_base_process_id.id or False) != new_bp_id
            ]
        else:
            changed = []
        res = super().write(vals)
        for rec in changed:
            rec._propagate_base_process()
        return res

    @api.model
    def _check_base_process_has_machines(self, base_process_id):
        """Raise UserError unless every operation in the given base process
        has `general_machine_id` set. Called from write() so it aborts the
        whole save before any propagation runs. No-op when clearing the
        base process (None/False).
        """
        if not base_process_id:
            return
        base = self.env['mrp.base.process'].browse(base_process_id)
        missing = base.process_ids.filtered(
            lambda l: l.operation_id and not l.operation_id.general_machine_id
        )
        if missing:
            ops_text = '\n'.join(
                '- %s (fas_code=%s)' % (
                    line.operation_id.name or '?',
                    line.operation_id.fas_code or '-',
                )
                for line in missing
            )
            raise UserError(_(
                "No se puede asignar la ruta '%s' al analisis: las siguientes "
                "operaciones no tienen Maquina General (TEXPLUS) asignada. "
                "Sin maquina la fase no puede registrarse en produccion.\n\n%s\n\n"
                "Configura la maquina general en cada operacion antes de continuar."
            ) % (base.name, ops_text))

    def _propagate_base_process(self):
        """Refresh the routing lines, the technical sheets and the BoMs that
        depend on this analysis. Run when `mrp_base_process_id` is set,
        cleared, or replaced. Parameters configured by the operator on the
        technical route lines are intentionally reset — they were attached
        to operations that may not belong to the new base process.

        Per-line chatter from `technical.route.line` / `route.line.parameter`
        is suppressed via the `skip_route_line_chatter` context flag and
        replaced by a single summary message on each affected sheet.
        """
        self.ensure_one()
        base = self.mrp_base_process_id
        new_lines = list(base.process_ids.sorted(key=lambda p: p.sequence)) if base else []

        ctx_self = self.with_context(skip_route_line_chatter=True)

        # 1. Analysis routing lines.
        ctx_self.routing_ids.unlink()
        if new_lines:
            ctx_self.routing_ids = [
                Command.create({
                    'operation_id': p.operation_id.id,
                    'sequence': p.sequence,
                })
                for p in new_lines
            ]

        # 2. Each technical sheet's route_line_ids + BoM operations.
        for sheet in ctx_self.technical_sheet_ids:
            sheet.route_line_ids.unlink()
            if new_lines:
                sheet.route_line_ids = [
                    Command.create({
                        'sequence': p.sequence,
                        'operation_id': p.operation_id.id,
                        'line_parameter_ids': [
                            Command.create({'name': param.name})
                            for param in p.operation_id.parameter_ids
                        ],
                    })
                    for p in new_lines
                ]
            if sheet.bom_id:
                self._refresh_bom_operations(sheet)

            # Single summary message per sheet (chatter remains traceable).
            new_name = base.name if base else _('(sin ruta)')
            # Post on the user-facing record (without our suppress context).
            sheet.sudo().message_post(
                body=_("Ruta cambiada desde el análisis a: %s") % new_name
            )

    def _refresh_bom_operations(self, sheet):
        """Rebuild `operation_ids` of the BoM attached to a technical sheet.
        Bom lines that pointed at the old weaving operation are re-bound to
        the new weaving operation (if there is one) so the manufacturing
        consumption stays correct.
        """
        bom = sheet.bom_id
        if not bom:
            return
        # Snapshot bom_lines previously pinned to a weaving op.
        weaving_lines = bom.bom_line_ids.filtered(
            lambda l: l.operation_id
            and l.operation_id.operation_id
            and l.operation_id.operation_id.operation_type == 'weaving'
        )

        bom.operation_ids.unlink()
        ordered = sheet.route_line_ids.sorted(key=lambda r: r.sequence)
        bom.operation_ids = [
            Command.create({
                'name': r.operation_id.name,
                'operation_id': r.operation_id.id,
                'workcenter_id': r.workcenter_id.id,
            })
            for r in ordered
        ]

        new_weaving = bom.operation_ids.filtered(
            lambda o: o.operation_id and o.operation_id.operation_type == 'weaving'
        )
        if new_weaving and weaving_lines:
            weaving_lines.write({'operation_id': new_weaving[0].id})
        elif weaving_lines:
            # No weaving op in the new routing — clear the dangling reference
            # rather than letting it point to a deleted record.
            weaving_lines.write({'operation_id': False})
        
    def action_product(self):
        if not self.weaving_data_ids and not self.env.context.get('by_pass_error'):
            raise UserError(_('Please add at least one weaving data to generate the product!'))
        if not self.weaving_data_ids.mapped('fiber_ids') and not self.env.context.get('by_pass_error'):
            raise UserError(_('Please add at least one fiber to the weaving data to generate the product!'))
        if not all(fiber.weight > 0 for fiber in self.weaving_data_ids.mapped('fiber_ids')) and not self.env.context.get('by_pass_error'):
            raise UserError(_('All fibers of the weaving data must have weight greater than 0 to generate the product!'))
        if any(abs(sum(fiber.percentage for fiber in weaving_data.fiber_ids) - 1) > 1e-6 for weaving_data in self.weaving_data_ids) and not self.env.context.get('by_pass_error'):
            raise UserError(_('All fibers of the weaving data must sum 100% to generate the product!'))
        if not self.routing_ids:
            raise UserError(_('Please select a base process and the route to generate the product!'))
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
                # 'fabric_composition': '\n'.join([
                #     f'{round(f.percentage * 100)}% {f.product_template_id.name}'
                #     for f in rec.fiber_ids if f.product_template_id
                # ]).strip(),
                'density': self.density,
                'width': self.standard_width,
                'gauge_id': self.gauge_id.id,
                'stylo': rec.stylo,
                'notes': rec.notes,
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
        products = self.env['product.template'].search([('is_weaving', '=', True)])
        total = len(products)
        counter = 0
        for rec in products:
            _logger.info('[' + (rec.analysis_id.product_code if rec.analysis_id else 'N/A') + '] ' + str(counter) + ' / ' + str(total) + '  ' + str(int((counter / total)*100)) + '%')
            counter += 1
            if not rec.analysis_id:
                rec.analysis_id = self.env['product.analysis'].create({
                    # 'name': rec.name,
                    'product_description': rec.name,
                    'product_code': rec.default_code,
                    'state': 'prod',
                    'density_stability_twisting_id': [Command.create({
                        'density': 0.2,
                        'width': 0.2,
                        'width_shrinkage_from': 0.2,
                        'width_shrinkage_to': 0.2,
                        'length_shrinkage_from': 0.2,
                        'length_shrinkage_to': 0.2,
                        'twist': 0.2,
                    })]
                })
            else:
                width = int(rec.analysis_id.product_code[9:12])
                density = int(rec.analysis_id.product_code[12:15])
                rec.analysis_id.write({
                    'density': density,
                    'standard_width': width,
                })
                rec.analysis_id.mapped('technical_sheet_ids').write({
                    'product_code': rec.analysis_id.product_code,
                    'density': density,
                    'width': width,
                })

class AnalysisWeavingData(models.Model):
    _name = 'analysis.weaving.data'
    _description = 'Analysis Weaving Data'

    analysis_id = fields.Many2one('product.analysis', string='Product Analysis', ondelete='restrict')
    partner_id = fields.Many2one('res.partner', string='Customer', ondelete='restrict')
    stylo = fields.Char('Stylo')
    fiber_ids = fields.One2many('analysis.fiber', 'weaving_data_id', string='Fibers')
    technical_sheet_id = fields.Many2one('technical.sheet', string='Technical Sheet', copy=False)
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

    def _recompute_fiber_percentages(self):
        for rec in self:
            total_weight = sum(fiber.weight for fiber in rec.fiber_ids)
            for fiber in rec.fiber_ids:
                fiber.percentage = (fiber.weight / total_weight) if total_weight else 0

    @api.onchange('fiber_ids')
    def _onchange_fiber_ids_recompute_percentages(self):
        self._recompute_fiber_percentages()
    
    def action_duplicate(self):
        for rec in self:
            new_rec = rec.copy({
                'analysis_id': rec.analysis_id.id,
                'fiber_ids': [Command.create({
                    'sequence': fiber.sequence,
                    'system_type': fiber.system_type,
                    'weight': fiber.weight,
                    'thread_qty': fiber.thread_qty,
                    'product_template_id': fiber.product_template_id.id,
                    'ligament_id': fiber.ligament_id.id,
                }) for fiber in rec.fiber_ids],
            })
            new_rec._recompute_fiber_percentages()

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
    weight = fields.Float('Weight', digits=(12,6), default=False, required=True)
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

    @api.depends('weight', 'weaving_data_id.fiber_ids.weight')
    def _compute_percentage(self):
        for rec in self:
            total_weight = sum(rec.weaving_data_id.fiber_ids.mapped('weight'))
            rec.percentage = (rec.weight / total_weight) if rec.weight and total_weight else 0

    @api.constrains('weight')
    def _check_weight_positive(self):
        for rec in self:
            if rec.weight <= 0:
                raise UserError(_('Weight in fiber %s must be greater than 0.') % rec.product_template_id.display_name)

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
