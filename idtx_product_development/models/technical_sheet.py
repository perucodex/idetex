from odoo import models, fields, api, _, Command
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
    mesh_length = fields.Float('Mesh Length')
    # Datos de crudo
    raw_width = fields.Float('Width')
    raw_density = fields.Float('Density')
    raw_widening = fields.Float('Widening')
    # Datos de acabado
    finish_width = fields.Float('Width')
    finish_density = fields.Float('Density')
    finish_yield = fields.Float('Yield')
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
    user_id = fields.Many2one('res.users','Prepared by',default=lambda self: self.env.user)
    size_chart_ids = fields.One2many('technical.size.line', 'technical_id', string='Size Chart')
    route_line_ids = fields.One2many('technical.route.line', 'technical_id', string='Route Line')

    # def action_fetch_from_mysql(self):

    #     connector = MySQLConnector(
    #         host="170.233.144.110",
    #         user="root",
    #         password="Server01",
    #         database="prueba_covatex"
    #     )
    #     # _logger.info("clave1:******************************" + MySQLConnector.decrypt_data('X9vPTUu4s85CrJqn7IilfudhiMVlBvKN0mqx9yrhjQyL91VOKWyV/GQROQ5zqWlH'))
    #     # print(str(round(self.density, 2)))
    #     values = {
    #         'id_usuarios': 23,
    #         'fecha': fields.Date.context_today(self),
    #         'articulo': MySQLConnector.encrypt_data(self.analysis_id.product_description or ''),
    #         'cod_articulo': MySQLConnector.encrypt_data(self.analysis_id.product_code or ''),
    #         'cod_cliente': MySQLConnector.encrypt_data(str(self.partner_id.id) or ''),
    #         'programa': MySQLConnector.encrypt_data(self.program or ''),
    #         'composicion_tela': MySQLConnector.encrypt_data(self.fabric_composition or ''),
    #         'atx': MySQLConnector.encrypt_data(self.atx or ''),
    #         'densidad': MySQLConnector.encrypt_data(str(round(self.density, 2)) or ''),
    #         'ancho': MySQLConnector.encrypt_data(str(round(self.width, 2)) or ''),
    #         'primera_lav_encog': MySQLConnector.encrypt_data(self.first_wash_shrinkage or ''),
    #         'primera_lav_revir': MySQLConnector.encrypt_data(self.first_wash_twist or ''),
    #         'rendimiento': MySQLConnector.encrypt_data(str(self.yield_meter) or ''),
    #         'merma': MySQLConnector.encrypt_data(str(self.scrap) or ''),
    #         'tipo_tejido': MySQLConnector.encrypt_data('ABIERTO' if self.weave_type == 'open' else 'TUBULAR'),
    #         'tipo_operacion': MySQLConnector.encrypt_data('VENTA'),
    #         'partida': MySQLConnector.encrypt_data(self.batch or ''),
    #         'galga': MySQLConnector.encrypt_data(self.analysis_id.gauge_id.code or ''),
    #         'observacion': MySQLConnector.encrypt_data(self.notes or ''),
    #         'cantidad_procesos': MySQLConnector.encrypt_data(str(len(self.route_line_ids)) or ''),
    #         'hilanderia': MySQLConnector.encrypt_data(''),
    #     }
    #     connector.insert("rutas", values)

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
            }) for route in self.analysis_id.routing_ids.sorted(key=lambda r: r.sequence)],
            'bom_line_ids': [Command.create({'product_id': f.product_template_id.product_variant_id.id, 'product_qty': f.percentage}) for f in analysis_line.fiber_ids],
        })
        # Consumir el hilo en tejeduria
        # Solo si existe un producto de hilado
        if any(p.is_thread for p in analysis_line.fiber_ids.product_template_id.product_variant_id):
            weaving_operation = bom_id.operation_ids.filtered(lambda o: o.operation_id.workcenter_id.operation_type == 'weaving')
            if weaving_operation:
                for l in bom_id.bom_line_ids:
                    l.operation_id = weaving_operation
            else:
                # Si hay productos para tejer y no se encontró un proceso de tejido
                if bom_id.bom_line_ids:
                    raise UserError(_('There is no weaving operation in bom. Please check your product routing!'))
        self.product_id.bom_ids += bom_id

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
    value = fields.Char('Value')