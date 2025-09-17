from odoo import models, fields, api, _, Command
from .covatex import MySQLConnector
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
    program = fields.Char('Program')
    fabric_composition = fields.Char('Fabric Composition')
    atx = fields.Char('ATX')
    density = fields.Integer('Density')
    width = fields.Float('Width')
    gauge_id = fields.Many2one('product.gauge', string='Gauge')
    first_wash_shrinkage = fields.Char('First Wash Shrinkage')
    first_wash_twist = fields.Char('First Wash Twist')
    yield_meter = fields.Float('Yield')
    scrap = fields.Float('Scrap', default=0.01)
    weave_type = fields.Selection(related='analysis_id.weave_type', store=True)
    batch = fields.Char('Batch')
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
        ('test', 'Test'),
        ('done', 'Done'),
        ('prod', 'Product'),
    ], string='State', default='test')
    user_id = fields.Many2one('res.users','Prepared by',default=lambda self: self.env.user)
    size_chart_ids = fields.One2many('technical.size.line', 'technical_id', string='Size Chart')
    route_line_ids = fields.One2many('technical.route.line', 'technical_id', string='Route Line')

    def action_fetch_from_mysql(self):

        connector = MySQLConnector(
            host="170.233.144.110",
            user="root",
            password="Server01",
            database="prueba_covatex"
        )
        # _logger.info("clave1:******************************" + MySQLConnector.decrypt_data('X9vPTUu4s85CrJqn7IilfudhiMVlBvKN0mqx9yrhjQyL91VOKWyV/GQROQ5zqWlH'))
        # print(str(round(self.density, 2)))
        values = {
            'id_usuarios': 23,
            'fecha': fields.Date.context_today(self),
            'articulo': MySQLConnector.encrypt_data(self.analysis_id.product_description or ''),
            'cod_articulo': MySQLConnector.encrypt_data(self.analysis_id.product_code or ''),
            'cod_cliente': MySQLConnector.encrypt_data(str(self.partner_id.id) or ''),
            'programa': MySQLConnector.encrypt_data(self.program or ''),
            'composicion_tela': MySQLConnector.encrypt_data(self.fabric_composition or ''),
            'atx': MySQLConnector.encrypt_data(self.atx or ''),
            'densidad': MySQLConnector.encrypt_data(str(round(self.density, 2)) or ''),
            'ancho': MySQLConnector.encrypt_data(str(round(self.width, 2)) or ''),
            'primera_lav_encog': MySQLConnector.encrypt_data(self.first_wash_shrinkage or ''),
            'primera_lav_revir': MySQLConnector.encrypt_data(self.first_wash_twist or ''),
            'rendimiento': MySQLConnector.encrypt_data(str(self.yield_meter) or ''),
            'merma': MySQLConnector.encrypt_data(str(self.scrap) or ''),
            'tipo_tejido': MySQLConnector.encrypt_data('ABIERTO' if self.weave_type == 'open' else 'TUBULAR'),
            'tipo_operacion': MySQLConnector.encrypt_data('VENTA'),
            'partida': MySQLConnector.encrypt_data(self.batch or ''),
            'galga': MySQLConnector.encrypt_data(self.analysis_id.gauge_id.code or ''),
            'observacion': MySQLConnector.encrypt_data(self.notes or ''),
            'cantidad_procesos': MySQLConnector.encrypt_data(str(len(self.route_line_ids)) or ''),
            'hilanderia': MySQLConnector.encrypt_data(''),
        }
        connector.insert("rutas", values)

    @api.depends('order_line.invoice_lines')
    def _get_boms(self):
        # The invoice_ids are obtained thanks to the invoice lines of the SO
        # lines, and we also search for possible refunds created directly from
        # existing invoices. This is necessary since such a refund is not
        # directly linked to the SO.
        for order in self:
            invoices = order.order_line.invoice_lines.move_id.filtered(lambda r: r.move_type in ('out_invoice', 'out_refund'))
            order.invoice_ids = invoices
            order.invoice_count = len(invoices)

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
    
    def action_done(self):
        self.state = 'done'

    def action_return(self):
        self.state = 'done' if self.state == 'prod' else 'test'

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
    value = fields.Char('Value')