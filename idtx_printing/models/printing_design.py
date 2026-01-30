from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import base64
import io

from PIL import Image

# Extensiones permitidas
ALLOWED_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.bmp')

class PrintingDesign(models.Model):
    _name = 'printing.design'
    _description = 'Printing Design'
    _rec_name = 'code'

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
    cylinder_qty = fields.Integer('Cylinder Qty')
    cylinder_size = fields.Selection([
        ('64', 'Cylinder 64'),
        ('82', 'Cylinder 82'),
        ('102', 'Cylinder 102'),
    ], string='Cylinder Size')
    shrinkage = fields.Float('Shrinkage')
    raport = fields.Float('Raport')
    partner_id = fields.Many2one('res.partner', string='Customer')
    file_desc = fields.Char('Design Name')
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.ref('base.USD'))
    unit_price = fields.Monetary('Unit Price', currency_field='currency_id')
    yield_meter = fields.Float('Yield')
    total_price = fields.Monetary('Total Price', compute='_compute_total_price', currency_field='currency_id')
    is_locked = fields.Boolean(compute='_compute_is_locked', store=False)

    @api.depends('name')
    def _compute_is_locked(self):
        for rec in self:
            rec.is_locked = rec.name != _('New')

    @api.constrains('cylinder_qty')
    def _check_cylinder_qty(self):
        for rec in self:
            if rec.cylinder_qty <= 0 and rec.printing_type == 'rotary':
                raise ValidationError(_("Cylinder Qty must be greater than 0"))
        
    @api.depends('yield_meter')
    def _compute_total_price(self):
        for rec in self:
            rec.total_price = rec.unit_price * rec.yield_meter

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
            
    #=== CRUD METHODS ===#

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _("New")) == _("New"):
                seq_date = fields.Datetime.context_timestamp(
                    self, fields.Datetime.to_datetime(vals['printing_date'])
                ) if 'printing_date' in vals else None
                vals['name'] = self.env['ir.sequence'].with_company(vals.get('company_id')).next_by_code(
                    'printing.design', sequence_date=seq_date) or _("New")
        return super().create(vals_list)

    # -------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------

    @api.onchange('printing_date','printing_type','cylinder_qty','process_type_rotary','process_type_digital')
    def _onchange_get_code(self):
        for rec in self:
            p_date = rec.printing_date or fields.Date.context_today(self)
            year_2d = fields.Date.from_string(p_date).strftime('%y')
            last_code = rec.search([], limit=1).sorted('code', True)
            seq = str(int(last_code[5:8]) + 1).zfill(4)
            cyl = ''
            if rec.printing_type == 'rotary':
                cyl = str(rec.cylinder_qty) or 0
            code = self._get_process_code(rec)
            parts = ['M' + year_2d, seq]
            if cyl:
                parts.append(cyl)
            if code:
                parts.append(code)
            rec.code = '-'.join(parts)

    def _get_process_code(self, rec):
        """
        RR = Rotary + Reactive
        RP = Rotary + Pigment
        RD = Rotary + Discharge
        RV = Rotary + Devoré
        DR = Digital + Reactive
        DP = Digital + Pigment
        """
        printing_type = rec.printing_type
        if printing_type == 'rotary':
            process = rec.process_type_rotary
            return {
                'reactive': 'RR',
                'pigment': 'RP',
                'discharge': 'RD',
                'devore': 'RV',
            }.get(process)

        if printing_type == 'digital':
            process = rec.process_type_digital
            return {
                'reactive': 'DR',
                'pigment': 'DP',
            }.get(process)

        return ''