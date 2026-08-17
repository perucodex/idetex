# -*- coding: utf-8 -*-
from markupsafe import Markup

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

# Las 3 áreas que archivan su copia del LabDip (coinciden con las 3 etiquetas).
AREA_SELECTION = [
    ('calidad', 'Calidad'),
    ('tintoreria', 'Tintorería'),
    ('laboratorio', 'Laboratorio'),
]
AREA_LABELS = dict(AREA_SELECTION)


class ColorRecipeLocation(models.Model):
    _name = 'color.recipe.location'
    _description = 'Ubicación de LabDip'
    _order = 'recipe_id, area'

    recipe_id = fields.Many2one(
        'color.recipe', string='Receta', required=True,
        ondelete='cascade', index=True)
    area = fields.Selection(AREA_SELECTION, string='Área', required=True, index=True)
    drawer = fields.Char(string='Cajón', required=True)
    user_id = fields.Many2one(
        'res.users', string='Registrado por',
        default=lambda self: self.env.user, readonly=True)
    company_id = fields.Many2one(
        related='recipe_id.company_id', store=True, index=True)

    # Campos de solo lectura para listar/buscar cómodo.
    recipe_name = fields.Char(related='recipe_id.name', store=True, string='Receta')
    recipe_color_code = fields.Char(
        related='recipe_id.recipe_color_code', store=True, string='Código')
    color_name = fields.Char(related='recipe_id.color_name', store=True, string='Color')
    lab_dev_name = fields.Char(related='recipe_id.lab_dev_id.name', string='N° LD')
    partner_id = fields.Many2one(related='recipe_id.partner_id', string='Cliente', store=True)

    _sql_constraints = [
        ('recipe_area_uniq', 'unique(recipe_id, area)',
         'Ya existe una ubicación registrada para esta receta en esta área.'),
    ]

    @staticmethod
    def _clean_drawer(value):
        return (value or '').strip().upper()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'drawer' in vals:
                vals['drawer'] = self._clean_drawer(vals['drawer'])
        records = super().create(vals_list)
        for rec in records:
            rec._post_location_change('created')
        return records

    def write(self, vals):
        if 'drawer' in vals:
            vals['drawer'] = self._clean_drawer(vals['drawer'])
        old_drawers = {rec.id: rec.drawer for rec in self}
        res = super().write(vals)
        if 'drawer' in vals or 'area' in vals:
            for rec in self:
                rec._post_location_change('updated', old_drawers.get(rec.id))
        return res

    def _post_location_change(self, kind, old_drawer=None):
        """Deja constancia del cambio de ubicación en el chatter de la receta."""
        self.ensure_one()
        recipe = self.recipe_id
        if not recipe:
            return
        area_label = self._display_area()
        if kind == 'updated':
            if not old_drawer or old_drawer == self.drawer:
                return
            body = Markup(_('Ubicación actualizada — <b>%(area)s</b>: cajón %(old)s → <b>%(new)s</b>')) % {
                'area': area_label, 'old': old_drawer, 'new': self.drawer or ''}
        else:
            body = Markup(_('Ubicación registrada — <b>%(area)s</b>: cajón <b>%(new)s</b>')) % {
                'area': area_label, 'new': self.drawer or ''}
        recipe.message_post(body=body)

    @api.constrains('drawer')
    def _check_drawer(self):
        for rec in self:
            if not self._clean_drawer(rec.drawer):
                raise ValidationError(_('El cajón es obligatorio.'))

    def _display_area(self):
        self.ensure_one()
        return AREA_LABELS.get(self.area, self.area or '')

    @api.depends('recipe_name', 'area', 'drawer')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = '%s · %s · Cajón %s' % (
                rec.recipe_name or '', rec._display_area(), rec.drawer or '')

    # ------------------------------------------------------------------
    # API para la pantalla kiosco (OWL)
    # ------------------------------------------------------------------
    @api.model
    def kiosk_resolve(self, barcode):
        """Busca la receta por el código de barras escaneado (recipe_color_code)."""
        code = (barcode or '').strip()
        if not code:
            raise UserError(_('Escanee un código de barras.'))
        recipe = self.env['color.recipe'].search(
            [('recipe_color_code', '=', code)], limit=1)
        if not recipe:
            raise UserError(_('No se encontró ninguna receta con el código "%s".') % code)
        existing = self.search([('recipe_id', '=', recipe.id)])
        return {
            'recipe_id': recipe.id,
            'name': recipe.name or '',
            'code': recipe.recipe_color_code or '',
            'color_name': recipe.color_name or '',
            'lab_dev': recipe.lab_dev_id.name or '',
            'partner': recipe.partner_id.name or '',
            'locations': {loc.area: loc.drawer for loc in existing},
        }

    @api.model
    def kiosk_register(self, recipe_id, area, drawer):
        """Registra/actualiza la ubicación (una vigente por receta+área)."""
        if area not in AREA_LABELS:
            raise UserError(_('Seleccione un área válida.'))
        clean = self._clean_drawer(drawer)
        if not clean:
            raise UserError(_('Escanee o indique el cajón.'))
        recipe = self.env['color.recipe'].browse(recipe_id)
        if not recipe.exists():
            raise UserError(_('La receta ya no existe.'))
        existing = self.search(
            [('recipe_id', '=', recipe.id), ('area', '=', area)], limit=1)
        previous = existing.drawer if existing else ''
        if existing:
            existing.write({'drawer': clean, 'user_id': self.env.user.id})
            loc = existing
        else:
            loc = self.create({
                'recipe_id': recipe.id,
                'area': area,
                'drawer': clean,
            })
        return {
            'recipe_name': recipe.name or '',
            'code': recipe.recipe_color_code or '',
            'color_name': recipe.color_name or '',
            'area': area,
            'area_label': AREA_LABELS.get(area, area),
            'drawer': loc.drawer,
            'previous_drawer': previous or '',
            'replaced': bool(previous and previous != loc.drawer),
        }
