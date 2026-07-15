import math
import re

from odoo import _, models, fields, api
from odoo.exceptions import UserError

class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    mrwo_id = fields.Many2one('mrp.routing.workcenter.operation', string='Operation LAB')
    operation_type = fields.Selection(related='mrwo_id.operation_type')
    roll_ids = fields.One2many('mrp.workorder.roll', 'workorder_id', string='Weaving Rolls')
    batch_ids = fields.Many2many('mrp.workorder.batch', string='Batchs')
    equipment_ids = fields.Many2many('maintenance.equipment', string='Equipments')
    option_ids = fields.One2many('mrp.workorder.option', 'workorder_id', string='Options')

    # --- Estimación de tiempo de tejido (TEJIDO CRUDO) ---
    estimated_rate_kg_h = fields.Float(
        'Producción Estimada (kg/h)', compute='_compute_weaving_aggregate',
        digits=(16, 2),
        help="Suma de la producción estimada de todas las máquinas de las opciones (corren en paralelo).")
    estimated_roll_count = fields.Integer(
        'Rollos Estimados', compute='_compute_weaving_aggregate',
        help="Cantidad de rollos = techo(kg a producir / peso por rollo de la configuración).")
    weaving_estimate_warning = fields.Char(
        'Aviso de Estimación', compute='_compute_weaving_aggregate',
        help="Motivo por el que no se pudo estimar la duración (datos faltantes).")

    # ------------------------------------------------------------------
    # Cálculo de tiempo de tejido de punto en máquinas circulares.
    # Producción por CONSUMO DE HILO (no necesita pasadas/cm ni gramaje):
    #   tex_fibra = cabos * 590.5 / Ne   (título Ne del maestro de hilados)
    #   g/vuelta  = N(agujas) * F(alimentadores) * Σ_fibras(long_malla_mm * tex / 1e6)
    #   kg/h (1 máq) = RPM * eficiencia * g/vuelta * 60 / 1000
    #   tiempo(min)  = kg_totales / Σ(kg/h de cada máquina) * 60
    # long_malla viene de la ficha técnica (analysis.fiber.length, mm); el
    # título/cabos del hilo viene del producto de hilo (fiber.product_template_id,
    # campos thread_titulo_id/thread_cabos_id de idtx_thread_codigo).
    # weave_type (tubular/open) NO afecta el peso tejido por vuelta.
    # Nota: se asume sistema Ne (algodón); hilos filamento (denier) no se cubren.
    # ------------------------------------------------------------------
    def _get_weaving_analysis(self):
        """Ficha técnica (product.analysis) del producto de la OT, o recordset
        vacío. Acceso defensivo: no rompe si idtx_product_development no está."""
        self.ensure_one()
        if 'product.analysis' not in self.env:
            return None
        Analysis = self.env['product.analysis']
        tmpl = self.product_id.product_tmpl_id
        if tmpl and 'analysis_id' in tmpl._fields and tmpl.analysis_id:
            return tmpl.analysis_id
        return Analysis.browse()

    @api.model
    def _first_int(self, value):
        """Primer entero contenido en un texto ('030'->30, '30/1'->30)."""
        if value is None:
            return 0
        m = re.search(r'\d+', str(value))
        return int(m.group()) if m else 0

    def _fiber_tex(self, fiber):
        """Densidad lineal del hilo de la fibra en tex (g/1000 m).
        Título (Ne, algodón) y cabos desde el producto de hilo: tex = cabos*590.5/Ne."""
        tmpl = fiber.product_template_id
        if not tmpl or 'thread_titulo_id' not in tmpl._fields:
            return 0.0
        titulo = tmpl.thread_titulo_id
        ne = self._first_int(titulo.code or titulo.name) if titulo else 0
        if ne <= 0:
            return 0.0
        plies = self._first_int(tmpl.thread_cabos_id.code) if tmpl.thread_cabos_id else 0
        return (plies or 1) * 590.5 / ne

    def _weaving_g_per_revolution(self, analysis):
        """Gramos de tela tejidos por una vuelta completa de la máquina."""
        if not analysis:
            return 0.0
        N = analysis.needles or 0
        F = analysis.feeders or 0
        if not (N and F):
            return 0.0
        wdata = analysis.weaving_data_ids[:1]
        if not wdata:
            return 0.0
        g_per_loop = 0.0
        for fiber in wdata.fiber_ids:
            sl_mm = fiber.length or 0.0
            tex = self._fiber_tex(fiber)
            if sl_mm > 0 and tex > 0:
                g_per_loop += sl_mm * tex / 1.0e6
        return N * F * g_per_loop

    @api.depends('operation_type', 'qty_production',
                 'option_ids', 'option_ids.estimated_rate_kg_h',
                 'option_ids.weaving_estimate_warning',
                 'company_id.weaving_weight_per_roll')
    def _compute_weaving_aggregate(self):
        for wo in self:
            wo.estimated_rate_kg_h = 0.0
            wo.estimated_roll_count = 0
            wo.weaving_estimate_warning = False
            if wo.operation_type != 'weaving':
                continue
            wo.estimated_rate_kg_h = sum(wo.option_ids.mapped('estimated_rate_kg_h'))
            company = wo.company_id or self.env.company
            per_roll = company.weaving_weight_per_roll or 0.0
            qty = wo.qty_production or 0.0
            if per_roll > 0 and qty > 0:
                wo.estimated_roll_count = int(math.ceil(qty / per_roll))
            warnings = [w for w in wo.option_ids.mapped('weaving_estimate_warning') if w]
            if not wo.option_ids:
                wo.weaving_estimate_warning = _("Crea una opción con máquinas para estimar el tiempo.")
            elif warnings:
                wo.weaving_estimate_warning = warnings[0]

    @api.depends('operation_id', 'workcenter_id', 'qty_producing', 'qty_production',
                 'operation_type', 'option_ids', 'option_ids.estimated_rate_kg_h')
    def _compute_duration_expected(self):
        # Comportamiento estándar para todas (capacidad de la operación, etc.).
        super()._compute_duration_expected()
        # Para tejido, sobreescribimos con la estimación por producción cuando
        # hay un ritmo calculable; si no, queda el valor estándar.
        for wo in self.filtered(lambda w: w.operation_type == 'weaving' and w.state not in ('done', 'cancel')):
            rate = sum(wo.option_ids.mapped('estimated_rate_kg_h'))
            qty = wo.qty_production or 0.0
            if rate > 0 and qty > 0:
                wo.duration_expected = qty / rate * 60.0

    @api.onchange('mrwo_id')
    def _onchange_mrwo_id(self):
        for rec in self:
            rec.workcenter_id = rec.mrwo_id.workcenter_id
            rec.name = rec.mrwo_id.name

    # Operaciones que procesan PARTIDAS (no rollos sueltos): su cantidad
    # producida es el peso de los rollos de sus partidas que pertenecen a
    # la propia OF (las partidas pueden combinar rollos de varias OFs).
    BATCH_OPERATION_TYPES = ('dyeing', 'finishing', 'printing', 'quality')

    def _get_textile_produced_qty(self):
        self.ensure_one()
        if self.operation_type == 'weaving':
            if getattr(self, 'weave_type', False) == 'rect':
                return float(sum(self.roll_ids.mapped('quantity')))
            total_weight = float(sum(self.roll_ids.mapped('gross_weight')))
            return total_weight or float(sum(self.roll_ids.mapped('quantity')))
        if self.operation_type in self.BATCH_OPERATION_TYPES:
            batch_rolls = self.batch_ids.wo_roll_ids.filtered(
                lambda roll: roll.workorder_id and roll.workorder_id.production_id == self.production_id
            )
            total_weight = float(sum(batch_rolls.mapped('gross_weight')))
            if total_weight > 0:
                return total_weight
            return float(sum(batch_rolls.mapped('quantity')))
        return 0.0

    def _sync_textile_qty_produced(self):
        for workorder in self.filtered(lambda wo: wo.operation_type in (('weaving',) + wo.BATCH_OPERATION_TYPES) and wo.state not in ('done', 'cancel')):
            workorder.qty_produced = workorder._get_textile_produced_qty()

    def write(self, vals):
        if 'state' in vals and vals['state'] in ('progress', 'done') and self.filtered(lambda wo: wo.operation_type in (('weaving',) + wo.BATCH_OPERATION_TYPES)):
            result = True
            for workorder in self:
                current_vals = dict(vals)
                produced_qty = workorder._get_textile_produced_qty()
                if vals['state'] == 'done' and produced_qty > 0:
                    current_vals['qty_produced'] = produced_qty
                elif 'qty_produced' not in current_vals and produced_qty > 0:
                    current_vals['qty_produced'] = produced_qty
                result = super(MrpWorkorder, workorder).write(current_vals) and result
            return result
        return super().write(vals)

    def unlink(self):
        for rec in self:
            if rec.state in ('done','progress'):
                raise UserError(_('You can\'t delete a workorder in state %s') % dict(rec._fields['state'].selection).get(rec.state, rec.state))
        return super().unlink()
    
    def button_reopen(self):
        self.ensure_one()
        self.leave_id.unlink()
        self.write({
            'state': 'progress',
            'date_finished': False,
        })
        return True
    
    def button_start(self, raise_on_invalid_state=False):
        for wo in self:
            if wo.workcenter_id.operation_type == 'weaving':
                if not wo.option_ids:
                    raise UserError(_('Please create at least one option before starting the workorder.'))
                invalid_options = wo.option_ids.filtered(lambda opt: not opt.employee_ids or not opt.equipment_ids)
                if invalid_options:
                    raise UserError(_('All options must have assigned employees and equipments before starting.'))
        return super().button_start(raise_on_invalid_state=raise_on_invalid_state)

class MrpWorkorderOption(models.Model):
    _name = 'mrp.workorder.option'
    _description = 'Workorder Option'

    name = fields.Char('Name')
    workorder_id = fields.Many2one('mrp.workorder', string='Workorder')
    workcenter_id = fields.Many2one(related='workorder_id.workcenter_id', string='Workcenter')
    notes = fields.Text('Notes')
    employee_ids = fields.Many2many('hr.employee', string='Employees')
    equipment_ids = fields.Many2many('maintenance.equipment', string='Equipments')
    option_line_ids = fields.One2many('mrp.workorder.option.line', 'option_id', string='Option Lines')
    available_thread_product_ids = fields.Many2many(
        'product.product',
        compute='_compute_available_thread_products',
        string='Available Thread Products'
    )

    # --- Estimación de tejido por opción ---
    estimated_rate_kg_h = fields.Float(
        'Producción Estimada (kg/h)', compute='_compute_weaving_estimate', digits=(16, 2),
        help="Producción estimada de esta opción (suma de sus máquinas).")
    weight_per_rev_g = fields.Float(
        'Peso por Vuelta (g)', compute='_compute_weaving_estimate', digits=(16, 4),
        help="Gramos de tela tejidos por una vuelta de la máquina, según la ficha técnica.")
    weaving_estimate_warning = fields.Char(
        'Aviso de Estimación', compute='_compute_weaving_estimate')

    # Nota: NO se puede depender de `...product_tmpl_id.analysis_id` porque
    # idtx_mrp carga antes que idtx_product_development (que define analysis_id).
    # El campo es no-almacenado: se recalcula al leerlo, así que basta con
    # depender del producto y de las máquinas/eficiencia.
    @api.depends('equipment_ids', 'equipment_ids.rpm', 'equipment_ids.efficiency',
                 'workorder_id.operation_type', 'workorder_id.product_id',
                 'workorder_id.company_id.weaving_default_efficiency')
    def _compute_weaving_estimate(self):
        for opt in self:
            opt.estimated_rate_kg_h = 0.0
            opt.weight_per_rev_g = 0.0
            opt.weaving_estimate_warning = False
            wo = opt.workorder_id
            if not wo or wo.operation_type != 'weaving':
                continue
            analysis = wo._get_weaving_analysis()
            if not analysis:
                opt.weaving_estimate_warning = _("Sin ficha técnica (análisis) en el producto.")
                continue
            g_rev = wo._weaving_g_per_revolution(analysis)
            if g_rev <= 0:
                opt.weaving_estimate_warning = _("Faltan agujas/alimentadores o datos de hilo en la ficha.")
                continue
            opt.weight_per_rev_g = g_rev
            company = wo.company_id or self.env.company
            default_eff = company.weaving_default_efficiency or 0.0
            rate = 0.0
            machine_without_rpm = False
            for eq in opt.equipment_ids:
                rpm = eq.rpm or 0.0
                if rpm <= 0:
                    machine_without_rpm = True
                    continue
                eff_pct = eq.efficiency if eq.efficiency > 0 else default_eff
                eff = (eff_pct or 0.0) / 100.0
                rate += rpm * eff * g_rev * 60.0 / 1000.0
            opt.estimated_rate_kg_h = rate
            if rate <= 0:
                opt.weaving_estimate_warning = (
                    _("Asigna máquinas con RPM configurado.") if opt.equipment_ids
                    else _("Sin máquinas asignadas."))
            elif machine_without_rpm:
                opt.weaving_estimate_warning = _("Alguna máquina no tiene RPM; no se cuenta en el cálculo.")

    @api.model
    def default_get(self, fields):
        """Cargar líneas con productos is_thread al abrir el formulario"""
        res = super().default_get(fields)
        
        # Si viene workorder_id del contexto o está en los valores por defecto
        workorder_id = res.get('workorder_id') or self.env.context.get('default_workorder_id')
        
        if workorder_id and 'option_line_ids' in fields:
            workorder = self.env['mrp.workorder'].browse(workorder_id)
            if workorder and workorder.production_id:
                production = workorder.production_id
                bom = production.bom_id
                
                if bom:
                    # Obtener componentes del BOM que sean is_thread
                    thread_components = bom.bom_line_ids.filtered(
                        lambda l: l.product_id.product_tmpl_id.is_thread
                    )
                    
                    # Preparar las líneas con formato de one2many (0, 0, {...})
                    lines = []
                    for bom_line in thread_components:
                        lines.append((0, 0, {
                            'product_id': bom_line.product_id.id,
                        }))
                    
                    if lines:
                        res['option_line_ids'] = lines
        
        return res

    @api.depends('workorder_id', 'workorder_id.production_id', 'workorder_id.production_id.bom_id')
    def _compute_available_thread_products(self):
        """Calcular productos is_thread disponibles del BOM de la producción"""
        for record in self:
            if record.workorder_id and record.workorder_id.production_id:
                production = record.workorder_id.production_id
                bom = production.bom_id
                
                if bom:
                    # Obtener componentes del BOM que sean is_thread
                    thread_components = bom.bom_line_ids.filtered(
                        lambda l: l.product_id.product_tmpl_id.is_thread
                    )
                    record.available_thread_product_ids = thread_components.product_id
                else:
                    record.available_thread_product_ids = False
            else:
                record.available_thread_product_ids = False

    def unlink(self):
        for rec in self:
            if any(roll.option_id == rec for roll in rec.workorder_id.roll_ids):
                raise UserError(_('You can\'t delete options of a workorder used in any roll'))
        return super().unlink()

    @api.constrains('option_line_ids', 'workorder_id')
    def _check_option_lines_complete_unique(self):
        for record in self:
            if not record.workorder_id:
                continue
            required_products = set(record.available_thread_product_ids.ids)
            line_products = set(record.option_line_ids.mapped('product_id').ids)
            if required_products and line_products != required_products:
                missing = required_products - line_products
                extra = line_products - required_products
                if missing:
                    missing_names = self.env['product.product'].browse(list(missing)).mapped('display_name')
                    raise UserError(_(
                        'Missing required thread products: %s'
                    ) % ', '.join(missing_names))
                if extra:
                    extra_names = self.env['product.product'].browse(list(extra)).mapped('display_name')
                    raise UserError(_(
                        'Extra products not allowed: %s'
                    ) % ', '.join(extra_names))

            # Ensure all lines have product and lot
            incomplete = record.option_line_ids.filtered(lambda l: not l.product_id or not l.lot_id)
            if incomplete:
                raise UserError(_('All option lines must have product and lot.'))

            # # Build combination set for this option
            # combo = frozenset((line.product_id.id, line.lot_id.id) for line in record.option_line_ids)

            # # Disallow duplicate combos within the same option
            # if len(combo) != len(record.option_line_ids):
            #     raise UserError(_('Duplicate product/lot pairs are not allowed in the same option.'))

            # # Disallow duplicate combos across options in the same workorder
            # other_options = record.workorder_id.option_ids - record
            # for other in other_options:
            #     other_lines = other.option_line_ids.filtered(lambda l: l.product_id and l.lot_id)
            #     other_combo = frozenset((l.product_id.id, l.lot_id.id) for l in other_lines)
            #     if combo and combo == other_combo:
            #         raise UserError(_('An option with the same product/lot combination already exists.'))
    
class MrpWorkorderOptionLine(models.Model):
    _name = 'mrp.workorder.option.line'
    _description = 'Workorder Option Line'

    option_id = fields.Many2one('mrp.workorder.option', string='Option')
    product_id = fields.Many2one('product.product', string='Product')
    lot_id = fields.Many2one('stock.lot', string='Lot')
    available_lot_ids = fields.Many2many(
        'stock.lot',
        compute='_compute_available_lots',
        string='Available Lots'
    )
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Limpiar lot_id cuando cambia el producto"""
        if self.product_id and self.lot_id:
            if self.lot_id.product_id != self.product_id:
                self.lot_id = False
    
    @api.constrains('product_id', 'lot_id')
    def _check_lot_product_match(self):
        """Validar que el lote corresponda al producto seleccionado"""
        for record in self:
            if record.lot_id and record.product_id:
                if record.lot_id.product_id != record.product_id:
                    raise UserError(
                        _("The selected lot '%s' does not match the product '%s'") 
                        % (record.lot_id.name, record.product_id.name)
                    )
    
    @api.depends(
        'product_id',
        'option_id.workorder_id',
        'option_id.workorder_id.production_id',
        'option_id.workorder_id.production_id.move_raw_ids.move_line_ids.lot_id'
    )
    def _compute_available_lots(self):
        """Lotes disponibles segun producto y produccion del workorder."""
        for record in self:
            if not record.product_id:
                record.available_lot_ids = False
                continue
            workorder = record.option_id.workorder_id
            if not workorder or not workorder.production_id:
                record.available_lot_ids = False
                continue
            production = workorder.production_id
            lots = production.move_raw_ids.filtered(
                lambda m: m.product_id == record.product_id
            ).move_line_ids.lot_id
            record.available_lot_ids = lots