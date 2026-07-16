from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class BaseProcess(models.Model):
    _name = 'base.process'
    _description = 'Base Process'
    # El selector busca por nombre O por código (ej. "B503").
    _rec_names_search = ['name', 'code']

    sequence = fields.Integer('Sequence')
    color_recipe_id = fields.Many2one('color.recipe', string='Color Recipe')
    name = fields.Char('Name')
    code = fields.Char('Code')
    time = fields.Float('Time')
    program = fields.Char('Program')
    nc = fields.Integer('Nc')
    lin_maq = fields.Integer('Lin. Maq.')
    codmaq = fields.Char('Machine Code')
    base_process_line_ids = fields.One2many('base.process.line', 'base_process_id', string='Color Process Line')

    @api.depends('name', 'code')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = ('[%s] %s' % (rec.code, rec.name or '')) if rec.code else (rec.name or '')

    def _resequence_lines(self):
        """Normaliza la secuencia de las líneas para que ordenar SOLO por
        secuencia (como hace la lista con handle) respete primero el N°:
        una línea arrastrada fuera de su grupo de N° vuelve al borde del
        grupo al guardar."""
        for proc in self:
            lines = proc.base_process_line_ids.sorted(
                key=lambda l: (l.order_number or 0, l.sequence, l.id))
            for i, line in enumerate(lines):
                seq = (i + 1) * 10
                if line.sequence != seq:
                    line.with_context(skip_reseq=True).sequence = seq

class BaseProcessLine(models.Model):
    _name = 'base.process.line'
    _description = 'Base Process Line'
    _rec_name = 'product_id'
    # El N° manda: el handle solo reordena DENTRO del grupo de su N°
    # (arrastrada fuera del grupo, al guardar vuelve al borde de su grupo).
    _order = 'order_number, sequence, id'

    sequence = fields.Integer('Secuencia', default=10)
    base_process_id = fields.Many2one('base.process', string='Color Recipe Process Template')
    # 'colorants' = hueco de COLORANTES: en el proceso base es un solo item
    # (reemplaza a las familias 10-17 de TEXPLUS); los productos reales los
    # elige el laboratorio al crear la receta, como sub-lineas de esa linea.
    # 'range' = producto con TABLA de calculo (CF -> cantidad).
    line_type = fields.Selection([
        ('product', 'Producto'),
        ('colorants', 'Colorantes'),
        ('range', 'Tabla'),
    ], string='Tipo', default='product', required=True)
    product_id = fields.Many2one('product.template', string='Product')
    # N° de orden de ingreso a maquina dentro del proceso (TEXPLUS LPROFO.ProForNro).
    # Varios productos pueden compartir el mismo N° (entran juntos en la misma tanda).
    order_number = fields.Integer('N°', default=1)
    factor = fields.Float('Factor', digits=(12,5))
    uom = fields.Selection([
        ('por', '%'),
        ('gxl', 'Gr/L'),
    ], string='Uom', default='gxl')
    # Producto CON TABLA: su cantidad no es fija, se resuelve por rango según
    # la suma de % de colorantes del proceso (CF). Una sola línea por producto
    # con sus rangos anidados (reemplaza las N líneas repetidas de TEXPLUS).
    range_ids = fields.One2many('base.process.line.range', 'line_id', string='Tabla de Rangos', copy=True)
    has_table = fields.Boolean('Con Tabla', compute='_compute_has_table', store=True)

    @api.depends('line_type', 'product_id')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = 'COLORANTES' if rec.line_type == 'colorants' \
                else (rec.product_id.display_name or _('Línea'))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get('skip_reseq'):
            records.base_process_id._resequence_lines()
        return records

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('skip_reseq') \
                and ({'sequence', 'order_number'} & set(vals.keys())):
            self.base_process_id._resequence_lines()
        return res

    @api.depends('range_ids')
    def _compute_has_table(self):
        for rec in self:
            rec.has_table = bool(rec.range_ids)

class BaseProcessLineRange(models.Model):
    _name = 'base.process.line.range'
    _description = 'Rango de tabla de proceso base (CF -> cantidad)'
    _order = 'percent_from'

    line_id = fields.Many2one('base.process.line', string='Línea', required=True, ondelete='cascade')
    percent_from = fields.Float('% Desde', digits=(12, 5))
    percent_to = fields.Float('% Hasta', digits=(12, 5), required=True)
    factor = fields.Float('Cantidad', digits=(12, 5), required=True,
                          help='Cantidad (en la UdM de la línea) cuando la suma '
                               'de % de colorantes del proceso cae en este rango.')

    @api.constrains('percent_from', 'percent_to', 'line_id')
    def _check_ranges(self):
        for rec in self:
            if rec.percent_to <= rec.percent_from:
                raise ValidationError(_('El %% Hasta debe ser mayor que el %% Desde.'))
            for other in rec.line_id.range_ids - rec:
                if rec.percent_from < other.percent_to and other.percent_from < rec.percent_to:
                    raise ValidationError(_(
                        'Los rangos %(a)g–%(b)g y %(c)g–%(d)g se solapan.',
                        a=rec.percent_from, b=rec.percent_to,
                        c=other.percent_from, d=other.percent_to))
