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
    mrp_base_process_id = fields.Many2one(related='analysis_id.mrp_base_process_id')
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
        return super().create(vals_list)
    
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

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
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
            return super().write(vals)
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

        return result

    def unlink(self):
        if self.env.context.get('skip_route_line_chatter'):
            return super().unlink()
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
