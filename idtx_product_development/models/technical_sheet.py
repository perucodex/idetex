from odoo import models, fields, api, _
from odoo.fields import Command
from odoo.exceptions import UserError
from odoo.tools import html_escape
from markupsafe import Markup
# from .covatex import MySQLConnector
import logging

_logger = logging.getLogger(__name__)


def _html_bullet_list(lines):
    return Markup('<br/>').join(Markup(line) for line in lines)


def _html_change(label, old_value, new_value):
    return Markup('%s: %s -&gt; %s') % (
        html_escape(label),
        html_escape(old_value or '-'),
        html_escape(new_value or '-'),
    )

class TechnicalSheet(models.Model):
    _name = 'technical.sheet'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Technical Sheet'

    name = fields.Char('Name', required=True, copy=False, readonly=False, default=lambda self: _('New'))
    technical_date = fields.Date('Technical Date', required=True, default=lambda self: fields.Date.context_today(self))
    analysis_id = fields.Many2one('product.analysis', string='Product Analysis', ondelete='restrict')
    description = fields.Char('Description', related='analysis_id.product_description')
    product_code = fields.Char('Product Code', readonly=True, copy=False)
    partner_id = fields.Many2one('res.partner', string='Customer', ondelete='restrict')
    # Tejido
    stylo = fields.Char('Stylo')
    program = fields.Char('Program')
    fabric_composition = fields.Text('Fabric Composition')
    atx = fields.Char('ATX')
    density = fields.Integer('Density')
    width = fields.Integer('Width')
    gauge_id = fields.Many2one('product.gauge', string='Gauge')
    first_wash_shrinkage = fields.Char('First Wash Shrinkage')
    first_wash_twist = fields.Char('First Wash Twist')
    yield_meter = fields.Float('Yield', related='analysis_id.yield_meter')
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
    # Proceso base PROPIO de la ficha: nace del analisis (create) y el usuario
    # puede cambiarlo aqui sin tocar el analisis ni las fichas hermanas. Una
    # ficha "sigue" al analisis mientras su proceso base coincide con el de
    # este; si diverge, los cambios de ruta del analisis ya no la pisan y
    # pasa a seguir los cambios de lineas de su propio proceso base.
    mrp_base_process_id = fields.Many2one('mrp.base.process', string='Base Process')
    # Campos de busqueda del analisis
    analysis_product_family_id = fields.Many2one(related='analysis_id.product_family_id', store=True, readonly=True, index=True)
    analysis_product_fiber_id = fields.Many2one(related='analysis_id.product_fiber_id', store=True, readonly=True, index=True)
    analysis_product_title_id = fields.Many2one(related='analysis_id.product_title_id', store=True, readonly=True, index=True)

    def _compute_prod_scrap(self):
        for rec in self:
            rec.prod_scrap = 0.09

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
            # La ficha nace con el proceso base del analisis.
            if not vals.get('mrp_base_process_id') and vals.get('analysis_id'):
                vals['mrp_base_process_id'] = self.env['product.analysis'].browse(
                    vals['analysis_id']).mrp_base_process_id.id
        return super().create(vals_list)

    @api.onchange('analysis_id')
    def _onchange_analysis_id_base_process(self):
        if self.analysis_id and not self.mrp_base_process_id:
            self.mrp_base_process_id = self.analysis_id.mrp_base_process_id

    def _base_process_route_commands(self):
        """Comandos One2many para poblar route_line_ids desde el proceso base
        propio (fases en orden, con sus parametros)."""
        self.ensure_one()
        return [
            Command.create({
                'sequence': line.sequence,
                'operation_id': line.operation_id.id,
                'line_parameter_ids': [
                    Command.create({'name': param.name})
                    for param in line.operation_id.parameter_ids
                ],
            })
            for line in self.mrp_base_process_id.process_ids.sorted(key=lambda p: (p.sequence, p.id))
            if line.operation_id
        ]

    def _apply_base_process(self, rebuild=True, message=None):
        """Aplica el proceso base PROPIO de la ficha a su ruta y refresca su LdM.
        Solo toca ESTA ficha (ni el analisis ni las hermanas).

        rebuild=True: reconstruye route_line_ids desde el proceso base.
        rebuild=False: conserva las lineas que ya tiene el registro (p.ej. la
        vista previa del onchange que el cliente mando en el mismo guardado) y
        solo completa los parametros que falten.
        El chatter por linea se silencia y queda un unico resumen."""
        Analysis = self.env['product.analysis']
        for sheet in self:
            ctx = sheet.with_context(skip_route_line_chatter=True, skip_route_propagation=True)
            base = sheet.mrp_base_process_id
            if rebuild:
                ctx.route_line_ids.unlink()
                if base:
                    ctx.route_line_ids = ctx._base_process_route_commands()
            else:
                for line in ctx.route_line_ids:
                    if not line.line_parameter_ids and line.operation_id.parameter_ids:
                        line.line_parameter_ids = [
                            Command.create({'name': param.name})
                            for param in line.operation_id.parameter_ids
                        ]
            Analysis._refresh_bom_operations(sheet)
            body = message or _("Ruta base de la ficha cambiada a: %s") % (base.name if base else _('(sin ruta)'))
            sheet.sudo().message_post(body=body)

    @api.onchange('mrp_base_process_id')
    def _onchange_mrp_base_process_id(self):
        # Vista previa en el formulario (igual que en el analisis): al elegir
        # el Proceso base se muestran sus fases con sus parametros. Al guardar,
        # write() aplica el cambio SOLO a esta ficha (ruta + LdM).
        if not self.mrp_base_process_id:
            self.route_line_ids = [Command.clear()]
            return
        self.route_line_ids = [Command.clear()] + self._base_process_route_commands()

    def write(self, vals):
        target = self
        base_changed = self.browse()
        # skip_route_propagation: la escritura viene de la propagacion del
        # analisis (que ya reconstruye la ruta y la LdM) -> no reaplicar aqui.
        if 'mrp_base_process_id' in vals and not self.env.context.get('skip_route_propagation'):
            new_bp_id = vals.get('mrp_base_process_id') or False
            base_changed = self.filtered(lambda rec: (rec.mrp_base_process_id.id or False) != new_bp_id)
            if base_changed:
                # Las lineas de la vista previa (onchange) se crean en silencio
                # y sin refrescar la LdM linea a linea; _apply_base_process
                # refresca la LdM una vez y deja un unico resumen.
                target = self.with_context(skip_route_line_chatter=True, skip_route_propagation=True)
        res = super(TechnicalSheet, target).write(vals)
        if base_changed:
            # Si el cliente mando las lineas (vista previa del onchange, quiza
            # ya retocadas a mano) se respetan; si no, se reconstruyen.
            base_changed._apply_base_process(rebuild='route_line_ids' not in vals)
        # Sincroniza notes con la(s) línea(s) analysis.weaving.data enlazada(s)
        # (bidireccional con analysis.weaving.data.write). Flag anti-bucle.
        if 'notes' in vals and not self.env.context.get('_syncing_notes'):
            for rec in self:
                lines = rec.analysis_id.weaving_data_ids.filtered(
                    lambda w: w.technical_sheet_id == rec and w.notes != rec.notes)
                if lines:
                    lines.with_context(_syncing_notes=True).notes = rec.notes
        return res

    def action_done(self):
        self.state = 'done'
        analysis_line = self.analysis_id.weaving_data_ids.filtered(lambda w: w.technical_sheet_id == self)
        bom_id = self.env['mrp.bom'].sudo().create({
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
    # Largo/Alto en el codigo (no via .po): el msgid "Width" es compartido
    # con technical.sheet.width (Ancho) y no admite dos traducciones.
    length = fields.Float('Largo')
    width = fields.Float('Alto')
    # Tolerancias de medida (± cm): el Control de cuellos compara lo obtenido
    # contra Largo/Alto ± tolerancia y avisa si está fuera.
    length_tol = fields.Float('Tol. Largo (±)')
    width_tol = fields.Float('Tol. Alto (±)')
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

    def _refresh_sheet_boms(self, sheets):
        """Editar la ruta directamente en la ficha tambien debe reflejarse en
        su(s) LdM. `skip_route_propagation` evita el doble refresh cuando la
        reescritura proviene de `_propagate_base_process` /
        `_apply_routing_to_sheets` (alli el refresh de la LdM corre una sola
        vez al final)."""
        if self.env.context.get('skip_route_propagation'):
            return
        Analysis = self.env['product.analysis'].with_context(
            skip_route_line_chatter=True, skip_route_propagation=True)
        for sheet in sheets:
            Analysis._refresh_bom_operations(sheet)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._refresh_sheet_boms(records.mapped('technical_id'))
        if self.env.context.get('skip_route_line_chatter'):
            return records
        for record in records:
            if record.technical_id:
                record.technical_id.message_post(
                    body=Markup('Se agrego una linea de ruta: %s.') % html_escape(record.operation_id.name or '-')
                )
        return records

    def write(self, vals):
        if self.env.context.get('skip_route_line_chatter'):
            sheets = self.mapped('technical_id')
            result = super().write(vals)
            if {'operation_id', 'sequence', 'technical_id'}.intersection(vals):
                self._refresh_sheet_boms(sheets | self.mapped('technical_id'))
            return result
        tracked_fields = {'operation_id', 'technical_id'}
        before_by_id = {}
        if tracked_fields.intersection(vals):
            before_by_id = {
                record.id: {
                    'operation_name': record.operation_id.name,
                    'sheet': record.technical_id,
                }
                for record in self
            }

        result = super().write(vals)

        for record in self:
            before = before_by_id.get(record.id)
            if not before:
                continue

            target_sheet = record.technical_id or before['sheet']
            if not target_sheet:
                continue

            changes = []
            if before['operation_name'] != record.operation_id.name:
                changes.append(_html_change('Operacion', before['operation_name'], record.operation_id.name))

            if changes:
                target_sheet.message_post(
                    body=Markup('Se actualizo una linea de ruta:<br/>%s') % _html_bullet_list(changes)
                )

        if {'operation_id', 'sequence', 'technical_id'}.intersection(vals):
            before_sheets = self.env['technical.sheet'].browse()
            for before in before_by_id.values():
                if before['sheet']:
                    before_sheets |= before['sheet']
            self._refresh_sheet_boms(before_sheets | self.mapped('technical_id'))

        return result

    def unlink(self):
        sheets = self.mapped('technical_id')
        if self.env.context.get('skip_route_line_chatter'):
            result = super().unlink()
            self._refresh_sheet_boms(sheets.exists())
            return result
        messages = [
            (
                record.technical_id,
                Markup('Se elimino una linea de ruta: %s.') % html_escape(record.operation_id.name or '-'),
            )
            for record in self
            if record.technical_id
        ]

        result = super().unlink()

        for sheet, body in messages:
            sheet.message_post(body=body)

        self._refresh_sheet_boms(sheets.exists())

        return result

class RouteLineParameter(models.Model):
    _name = 'route.line.parameter' 
    _description = 'Route Line Parameter'

    technical_route_id = fields.Many2one('technical.route.line', string='Technical Routing Line')
    name = fields.Char('Parameter')
    value = fields.Text('Value')
    is_observation = fields.Boolean('Observación?')

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if self.env.context.get('skip_route_line_chatter'):
            return records
        for record in records:
            sheet = record.technical_route_id.technical_id
            if not sheet:
                continue
            sheet.message_post(
                body=Markup('Se agrego un parametro en la operacion %s: %s.') % (
                    html_escape(record.technical_route_id.operation_id.name or '-'),
                    html_escape(record.name or '-'),
                )
            )
        return records

    def write(self, vals):
        if self.env.context.get('skip_route_line_chatter'):
            return super().write(vals)
        tracked_fields = {'name', 'value', 'is_observation'}
        before_by_id = {}
        if tracked_fields.intersection(vals):
            before_by_id = {
                record.id: {
                    'name': record.name,
                    'value': record.value,
                    'is_observation': record.is_observation,
                    'operation_name': record.technical_route_id.operation_id.name,
                    'sheet': record.technical_route_id.technical_id,
                }
                for record in self
            }

        result = super().write(vals)

        for record in self:
            before = before_by_id.get(record.id)
            if not before or not before['sheet']:
                continue

            changes = []
            if before['name'] != record.name:
                changes.append(_html_change('Parametro', before['name'], record.name))
            if before['value'] != record.value:
                changes.append(_html_change('Valor', before['value'], record.value))
            if before['is_observation'] != record.is_observation:
                changes.append(
                    _html_change(
                        'Observacion',
                        _('Si') if before['is_observation'] else _('No'),
                        _('Si') if record.is_observation else _('No'),
                    )
                )

            if changes:
                before['sheet'].message_post(
                    body=Markup('Se actualizo un parametro de la operacion %s:<br/>%s') % (
                        html_escape(before['operation_name'] or '-'),
                        _html_bullet_list(changes),
                    )
                )

        return result

    def unlink(self):
        if self.env.context.get('skip_route_line_chatter'):
            return super().unlink()
        messages = [
            (
                record.technical_route_id.technical_id,
                Markup('Se elimino un parametro de la operacion %s: %s.') % (
                    html_escape(record.technical_route_id.operation_id.name or '-'),
                    html_escape(record.name or '-'),
                ),
            )
            for record in self
            if record.technical_route_id.technical_id
        ]

        result = super().unlink()

        for sheet, body in messages:
            sheet.message_post(body=body)

        return result
