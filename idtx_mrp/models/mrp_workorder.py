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

    @api.onchange('mrwo_id')
    def _onchange_mrwo_id(self):
        for rec in self:
            rec.workcenter_id = rec.mrwo_id.workcenter_id
            rec.name = rec.mrwo_id.name

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