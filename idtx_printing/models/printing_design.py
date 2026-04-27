from odoo import models, fields, api, _
from odoo.fields import Domain
from odoo.exceptions import ValidationError
import base64
import io

from markupsafe import Markup, escape
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
    rotary_recipe_line_ids = fields.One2many('printing.design.rotary.line', 'printing_design_id', string='Rotary Recipes')
    yield_meter = fields.Float('Yield')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('quoting', 'Quoting'),
        ('development', 'Development'),
        ('done', 'Done'),
    ], string='Status', default='draft', tracking=True, copy=False)
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

    def action_set_quoting(self):
        for rec in self:
            if rec.state == 'draft':
                rec.state = 'quoting'

    def action_set_development(self):
        for rec in self:
            if rec.state in ('draft', 'quoting'):
                rec.state = 'development'

    def _sync_state_from_recipes(self):
        for rec in self:
            if rec.rotary_recipe_line_ids.filtered(lambda line: line.state == 'approved'):
                rec.state = 'done'
            elif rec.state == 'done':
                rec.state = 'development'
    
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


class PrintingDesignRotaryLine(models.Model):
    _name = 'printing.design.rotary.line'
    _description = 'Printing Design Rotary Line'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _rec_name = 'name'

    printing_design_id = fields.Many2one('printing.design', string='Printing Design', ondelete='cascade', required=True)
    printing_design_code = fields.Char(related='printing_design_id.code', string='Design Code', store=True, readonly=True)
    printing_design_preview_image = fields.Binary(related='printing_design_id.preview_image', string='Design Preview', readonly=True)
    name = fields.Char('Recipe', required=True, copy=False, default=lambda self: _('New'), readonly=True)
    version = fields.Integer('Version', required=True, default=1, copy=False, readonly=True)
    recipe_date = fields.Date('Recipe Date', default=fields.Date.context_today, copy=False)
    previous_recipe_id = fields.Many2one('printing.design.rotary.line', string='Previous Recipe', ondelete='restrict', copy=False)
    production_percentage = fields.Float('Production Percentage', digits=(5, 2), default=25.00)
    has_been_approved = fields.Boolean('Has Been Approved', default=False, copy=False)
    is_current_version = fields.Boolean('Current Recipe', compute='_compute_is_current_version', store=True)
    color_line_ids = fields.One2many('printing.design.rotary.line.color', 'rotary_line_id', string='Colors', copy=True)
    state = fields.Selection([
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('obsolete', 'Obsolete'),
    ], string='Status', default='pending', copy=False, tracking=True)

    @api.constrains('production_percentage')
    def _check_production_percentage(self):
        for rec in self:
            if rec.production_percentage <= 0 or rec.production_percentage > 100:
                raise ValidationError(_('Production Percentage must be between 0 and 100.'))

    @api.depends(
        'version',
        'printing_design_id.rotary_recipe_line_ids.version',
        'printing_design_id.rotary_recipe_line_ids.state',
    )
    def _compute_is_current_version(self):
        for rec in self:
            approved_lines = rec.printing_design_id.rotary_recipe_line_ids.filtered(lambda line: line.state == 'approved') if rec.printing_design_id else self.env['printing.design.rotary.line']
            approved_versions = approved_lines.mapped('version')
            rec.is_current_version = rec.state == 'approved' and bool(approved_versions) and rec.version == max(approved_versions)

    @api.model_create_multi
    def create(self, vals_list):
        version_cache = {}
        for vals in vals_list:
            design_id = vals.get('printing_design_id')
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('printing.design.rotary.line') or _('New')
            if design_id and not vals.get('version'):
                if design_id not in version_cache:
                    current_versions = self.search([('printing_design_id', '=', design_id)]).mapped('version')
                    version_cache[design_id] = max(current_versions, default=0)
                version_cache[design_id] += 1
                vals['version'] = version_cache[design_id]
        return super().create(vals_list)

    def copy(self, default=None):
        default = dict(default or {})
        default.setdefault('name', _('New'))
        return super().copy(default)

    def _ensure_not_obsolete(self):
        obsolete_recipes = self.filtered(lambda rec: rec.state == 'obsolete')
        if obsolete_recipes:
            raise ValidationError(_('Obsolete recipes are read-only and cannot be modified.'))

    def action_approve(self):
        self._ensure_not_obsolete()
        for rec in self:
            if not rec.color_line_ids:
                raise ValidationError(_('The recipe must have at least one color before approval.'))
            if any(not color.chemical_line_ids for color in rec.color_line_ids):
                raise ValidationError(_('Each color must include at least one chemical line before approval.'))
            previous_recipes = rec.printing_design_id.rotary_recipe_line_ids.filtered(
                lambda line: line.id != rec.id and line.version < rec.version
            )
            if previous_recipes:
                previous_recipes.write({'state': 'obsolete'})
            rec.write({'state': 'approved', 'has_been_approved': True})
            rec.printing_design_id._sync_state_from_recipes()

    def action_return_to_pending(self):
        self._ensure_not_obsolete()
        for rec in self:
            previous_approved = rec.printing_design_id.rotary_recipe_line_ids.filtered(
                lambda line: line.id != rec.id and line.state == 'obsolete' and line.has_been_approved
            ).sorted(key=lambda line: (line.version, line.id))
            previous_pending = rec.printing_design_id.rotary_recipe_line_ids.filtered(
                lambda line: line.id != rec.id and line.state == 'obsolete' and not line.has_been_approved
            )
            rec.write({'state': 'pending'})
            if previous_approved:
                restored_recipe = previous_approved[-1]
                restored_recipe.write({'state': 'approved'})
                recipes_to_pending = previous_pending.filtered(lambda line: line.version > restored_recipe.version)
                if recipes_to_pending:
                    recipes_to_pending.write({'state': 'pending'})
            rec.printing_design_id._sync_state_from_recipes()

    def action_new_version(self):
        self.ensure_one()
        self._ensure_not_obsolete()
        new_version = max(self.printing_design_id.rotary_recipe_line_ids.mapped('version'), default=0) + 1
        new_recipe = self.copy({
            'version': new_version,
            'state': 'pending',
            'previous_recipe_id': self.id,
            'recipe_date': fields.Date.context_today(self),
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Recipe Version'),
            'view_mode': 'form',
            'res_model': self._name,
            'res_id': new_recipe.id,
            'target': 'current',
        }

    def action_open_recipe_sheet(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/printing/recipe/%s' % self.id,
            'target': 'new',
        }

class PrintingDesignRotaryLineColor(models.Model):
    _name = 'printing.design.rotary.line.color'
    _description = 'Printing Design Rotary Line Color'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id'

    rotary_line_id = fields.Many2one('printing.design.rotary.line', string='Rotary Line', ondelete='cascade', required=True)
    printing_design_id = fields.Many2one(related='rotary_line_id.printing_design_id', string='Printing Design', store=True)
    color_name = fields.Char('Color', required=True)
    chemical_line_ids = fields.One2many('printing.design.rotary.line.color.chemical', 'color_line_id', string='Chemicals', copy=True)

    @staticmethod
    def _build_chatter_body(title, lines):
        return Markup("%s<br/>%s") % (
            escape(title),
            Markup('<br/>').join(escape(line) for line in lines),
        )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.rotary_line_id:
                body = self._build_chatter_body(
                    _("Recipe color created:"),
                    [
                        _("Color: %s") % rec.color_name,
                    ],
                )
                rec.rotary_line_id.message_post(body=body, subtype_xmlid='mail.mt_note')
        return records

    def unlink(self):
        deleted_records = [
            {
                'rotary_line': rec.rotary_line_id,
                'color_name': rec.color_name,
            }
            for rec in self
        ]

        result = super().unlink()

        for deleted in deleted_records:
            if deleted['rotary_line']:
                body = self._build_chatter_body(
                    _("Recipe color deleted:"),
                    [
                        _("Color: %s") % deleted['color_name'],
                    ],
                )
                deleted['rotary_line'].message_post(body=body, subtype_xmlid='mail.mt_note')

        return result


class PrintingDesignRotaryLineColorChemical(models.Model):
    _name = 'printing.design.rotary.line.color.chemical'
    _description = 'Printing Design Rotary Line Color Chemical'
    _order = 'id'

    color_line_id = fields.Many2one('printing.design.rotary.line.color', string='Recipe Color', ondelete='cascade', required=True)
    product_id = fields.Many2one('product.template', string='Chemical', ondelete='restrict', required=True)
    quantity = fields.Float('Quantity', required=True, digits=(12, 5), default=0.0)

    @staticmethod
    def _build_chatter_body(title, lines):
        return Markup("%s<br/>%s") % (
            escape(title),
            Markup('<br/>').join(escape(line) for line in lines),
        )

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.color_line_id.rotary_line_id:
                body = self._build_chatter_body(
                    _("Recipe chemical created:"),
                    [
                        _("Color: %s") % rec.color_line_id.color_name,
                        _("Chemical: %s") % rec.product_id.display_name,
                        _("Quantity: %s") % rec.quantity,
                    ],
                )
                rec.color_line_id.rotary_line_id.message_post(body=body, subtype_xmlid='mail.mt_note')
        return records

    def write(self, vals):
        tracked_fields = {'product_id', 'quantity'}
        changes_by_record = {}
        if tracked_fields.intersection(vals):
            for rec in self:
                changes_by_record[rec.id] = {
                    'rotary_line': rec.color_line_id.rotary_line_id,
                    'color_name': rec.color_line_id.color_name,
                    'product_name': rec.product_id.display_name,
                    'quantity': rec.quantity,
                }

        result = super().write(vals)

        if changes_by_record:
            for rec in self:
                previous = changes_by_record.get(rec.id)
                if not previous or not previous['rotary_line']:
                    continue

                change_lines = [
                    _("Color: %s") % previous['color_name'],
                ]
                if 'product_id' in vals and previous['product_name'] != rec.product_id.display_name:
                    change_lines.append(
                        _("Chemical: %(old)s -> %(new)s") % {
                            'old': previous['product_name'],
                            'new': rec.product_id.display_name,
                        }
                    )
                if 'quantity' in vals and previous['quantity'] != rec.quantity:
                    if 'product_id' not in vals:
                        change_lines.append(
                            _("Chemical: %s") % rec.product_id.display_name,
                        )
                    change_lines.append(
                        _("Quantity: %(old)s -> %(new)s") % {
                            'old': previous['quantity'],
                            'new': rec.quantity,
                        }
                    )

                if change_lines:
                    body = self._build_chatter_body(
                        _("Recipe chemical updated:"),
                        change_lines,
                    )
                    previous['rotary_line'].message_post(
                        body=body,
                        subtype_xmlid='mail.mt_note',
                    )

        return result

    def unlink(self):
        deleted_records = [
            {
                'rotary_line': rec.color_line_id.rotary_line_id,
                'color_name': rec.color_line_id.color_name,
                'product_name': rec.product_id.display_name,
                'quantity': rec.quantity,
            }
            for rec in self
        ]

        result = super().unlink()

        for deleted in deleted_records:
            if deleted['rotary_line']:
                body = self._build_chatter_body(
                    _("Recipe chemical deleted:"),
                    [
                        _("Color: %s") % deleted['color_name'],
                        _("Chemical: %s") % deleted['product_name'],
                        _("Quantity: %s") % deleted['quantity'],
                    ],
                )
                deleted['rotary_line'].message_post(body=body, subtype_xmlid='mail.mt_note')

        return result

    @api.constrains('quantity')
    def _check_quantity(self):
        for rec in self:
            if rec.quantity <= 0:
                raise ValidationError(_('Chemical quantity must be greater than 0.'))