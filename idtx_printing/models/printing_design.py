from odoo import models, fields, api, _
from odoo.fields import Domain
from odoo.exceptions import ValidationError
import base64
import io

from PIL import Image

# Extensiones permitidas
ALLOWED_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.bmp')

class PrintingDesign(models.Model):
    _name = 'printing.design'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Printing Design'
    _rec_name = 'code'
    _order = 'create_date desc'

    name = fields.Char('Name', required=True, copy=False, readonly=False, default=lambda self: _('New'))
    code = fields.Char('Code')
    printing_date = fields.Date('Printing Date', required=True)
    printing_type = fields.Selection([
        ('rotary', 'Rotary'),
        ('digital', 'Digital'),
    ], string='Printing Type', required=True)
    process_type_rotary = fields.Selection([
        ('reactive', 'Reactive'),
        ('pigment', 'Pigment'),
        ('discharge', 'Discharge'),
        ('devore', 'Devoré'),
    ], string='Rotary Process Type')
    process_type_digital = fields.Selection([
        ('reactive', 'Reactive'),
        ('pigment', 'Pigment'),
    ], string='Digital Process Type')
    file_name = fields.Char(string='Design File Name')
    design_image = fields.Binary(string='Design Image', attachment=True)
    preview_image = fields.Binary(string='Preview', compute='_compute_preview_image', store=True)
    fabric_base = fields.Char('Fabric Base')
    cylinder_qty = fields.Integer('Cylinder Qty')
    cylinder_size = fields.Selection([
        ('64', 'Cylinder 64'),
        ('82', 'Cylinder 82'),
        ('102', 'Cylinder 102'),
    ], string='Cylinder Size')
    shrinkage = fields.Float('Shrinkage')
    # raport = fields.Float('Raport')
    partner_id = fields.Many2one('res.partner', string='Customer')
    file_desc = fields.Char('Design Name')
    digital_unit_price_ids = fields.One2many('printing.design.price', 'digital_printing_id', string='Digital Prices')
    rotary_unit_price_ids = fields.One2many('printing.design.price', 'rotary_printing_id', string='Rotary Prices')
    yield_meter = fields.Float('Yield')
    is_locked = fields.Boolean(compute='_compute_is_locked', store=False)
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.ref('base.USD'))
    unit_price = fields.Monetary('Unit Price', currency_field='currency_id')
    bonding_price = fields.Monetary('Bonding Price', currency_field='currency_id')

    @api.depends('name')
    def _compute_is_locked(self):
        for rec in self:
            rec.is_locked = rec.name != _('New')

    @api.constrains('cylinder_qty')
    def _check_cylinder_qty(self):
        for rec in self:
            if rec.cylinder_qty <= 0 and rec.printing_type == 'rotary':
                raise ValidationError(_("Cylinder Qty must be greater than 0"))

    @api.depends('design_image', 'file_name')
    def _compute_preview_image(self):
        for rec in self:
            rec.preview_image = False
            if not rec.design_image:
                continue
            if not rec.file_name or not rec.file_name.lower().endswith(ALLOWED_EXTENSIONS):
                continue
            try:
                image_data = base64.b64decode(rec.design_image)
                image = Image.open(io.BytesIO(image_data))
                # Normaliza modo de color
                if image.mode not in ('RGB', 'RGBA'):
                    image = image.convert('RGB')
                # Resize para preview
                image.thumbnail((512, 512))
                buffer = io.BytesIO()
                image.save(buffer, format='PNG')
                rec.preview_image = base64.b64encode(buffer.getvalue())
            except Exception:
                rec.preview_image = False

    @api.constrains('design_image', 'file_name')
    def _check_file_type(self):
        for rec in self:
            if rec.design_image and (not rec.file_name or not rec.file_name.lower().endswith(ALLOWED_EXTENSIONS)):
                raise ValidationError(_('Only image files are allowed: JPG, JPEG, PNG, BMP.'))
            
    @api.depends('code', 'file_desc')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"[{rec.code or ''}] {rec.file_desc or ''}".strip()

    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        base_domain = Domain(domain or Domain.TRUE)
        if name:
            base_domain &= Domain('code', operator, name) | Domain('file_desc', operator, name)
        return [(rec.id, rec.display_name) for rec in self.search(base_domain, limit=limit)]
    
    #=== CRUD METHODS ===#

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        # Estampado Digital
        if 'digital_unit_price_ids' in fields_list:
            res['digital_unit_price_ids'] = [
                (0, 0, {'sequence': 1,'range': '1 roll lower than 20Kg.','min_qty': 1, 'max_qty': 59}),
                (0, 0, {'sequence': 2,'range': '60-100 mts','min_qty': 60, 'max_qty': 100}),
                (0, 0, {'sequence': 3,'range': '101-300 mts','min_qty': 101, 'max_qty': 300}),
                (0, 0, {'sequence': 4,'range': '301-500 mts','min_qty': 301, 'max_qty': 500}),
                (0, 0, {'sequence': 5,'range': '501-1000 mts','min_qty': 501, 'max_qty': 1000}),
                (0, 0, {'sequence': 6,'range': '1001 or +','min_qty': 1000, 'max_qty': 99999999}),
            ]
        # Estampado Rotativo
        if 'rotary_unit_price_ids' in fields_list:
            res['rotary_unit_price_ids'] = [
                (0, 0, {'sequence': 1,'raport': '64','unit_price': self.env.company.cylinder_64_price, 'color_qty': '8-10', 'sample_min_qty': '0-100 mts.', 'sample_price': self.env.company.sample_1_price}),
                (0, 0, {'sequence': 2,'raport': '82','unit_price': self.env.company.cylinder_82_price, 'color_qty': '4-6', 'sample_min_qty': '101-200 mts.', 'sample_price': self.env.company.sample_2_price}),
                (0, 0, {'sequence': 3,'raport': '102','unit_price': self.env.company.cylinder_102_price, 'color_qty': '1-3', 'sample_min_qty': '201-300 mts.', 'sample_price': self.env.company.sample_3_price}),
            ]

        return res

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _("New")) == _("New"):
                seq_date = fields.Datetime.context_timestamp(
                    self, fields.Datetime.to_datetime(vals['printing_date'])
                ) if 'printing_date' in vals else None
                vals['name'] = self.env['ir.sequence'].with_company(vals.get('company_id')).next_by_code(
                    'printing.design', sequence_date=seq_date) or _("New")
                vals['code'] = self._create_code(vals)
        return super().create(vals_list)

    # -------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------

    # @api.onchange('printing_date','printing_type','cylinder_qty','process_type_rotary','process_type_digital')
    def _create_code(self, vals):
        # for rec in self:
        p_date = vals['printing_date'] or fields.Date.context_today(self)
        year_2d = fields.Date.from_string(p_date).strftime('%y')
        last_code = len(self.search([])) #.sorted('code', True)
        seq = str(last_code + 1).zfill(4)
        cyl = ''
        if vals['printing_type'] == 'rotary':
            cyl = str(vals['cylinder_qty']) or 0
            process = vals['process_type_rotary']
        else:
            process = vals['process_type_digital']
        code = self._get_process_code(vals['printing_type'], process)
        parts = ['M' + year_2d, seq]
        if cyl:
            parts.append(cyl)
        if code:
            parts.append(code)
        return '-'.join(parts)

    def _get_process_code(self, printing_type, process):
        """
        RR = Rotary + Reactive
        RP = Rotary + Pigment
        RD = Rotary + Discharge
        RV = Rotary + Devoré
        DR = Digital + Reactive
        DP = Digital + Pigment
        """
        # printing_type = rec.printing_type
        if printing_type == 'rotary':
            # process = rec.process_type_rotary
            return {
                'reactive': 'RR',
                'pigment': 'RP',
                'discharge': 'RD',
                'devore': 'RV',
            }.get(process)

        if printing_type == 'digital':
            # process = rec.process_type_digital
            return {
                'reactive': 'DR',
                'pigment': 'DP',
            }.get(process)

        return ''

class PrintingDesign(models.Model):
    _name = 'printing.design.price'
    _description = 'Printing Design Price'
    
    digital_printing_id = fields.Many2one('printing.design', string='Digital Printing')
    rotary_printing_id = fields.Many2one('printing.design', string='Rotary Printing')
    sequence = fields.Integer('sequence')
    # Digital
    range = fields.Char('Range')
    min_qty = fields.Float('Min. Qty')
    max_qty = fields.Float('Max. Qty')
    # Rotary
    raport = fields.Char('Raport')
    color_qty = fields.Char('Color Qty')
    sample_min_qty = fields.Char('Sample Min. Qty')
    sample_price = fields.Monetary('Sample Price', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.ref('base.USD'))
    unit_price = fields.Monetary('Unit Price', currency_field='currency_id')
    strike_off = fields.Monetary('Strike Off Price', currency_field='currency_id')
    total_price = fields.Monetary('Price per Kg.', compute='_compute_total_price', currency_field='currency_id')
        
    @api.depends('unit_price','digital_printing_id.yield_meter','rotary_printing_id.yield_meter')
    def _compute_total_price(self):
        for rec in self:
            if rec.max_qty == 59:
                rec.total_price = rec.unit_price
            else:
                if rec.digital_printing_id and rec.digital_printing_id.printing_type == 'digital':
                    rec.total_price = rec.unit_price * rec.digital_printing_id.yield_meter
                else:
                    rec.total_price = rec.unit_price * rec.rotary_printing_id.yield_meter