from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

class ControlAparienciaLine(models.Model):
    _inherit = 'control.apariencia.line'

    @api.model
    def _get_context_type_deffect(self):
        for key in ('appearance_type', 'default_type_deffect'):
            type_deffect = self.env.context.get(key)
            if type_deffect in ('quality', 'printing'):
                return type_deffect
        return False
    
    type_deffect = fields.Selection([
        ('quality', 'Quality'),
        ('printing', 'Printing'),
    ], string='Deffect Type', default=lambda self: self._get_context_type_deffect() or 'quality')
    printing_type = fields.Selection(related='pedido_line_id.printing_type', string='Printing Type', readonly=True)

    @api.onchange('pedido_line_id', 'rollo_num', 'type_deffect')
    def _onchange_validate_rollo_unique_by_type(self):
        for rec in self:
            existing_lines = rec.pedido_line_id.apariencia_line_ids.filtered(lambda l: l.rollo_num == rec.rollo_num and l.type_deffect == rec.type_deffect) - self
            if existing_lines: 
                raise ValidationError(_('An evaluation already exists for this roll number with the same defect type in this batch.'))
            
    @api.model_create_multi
    def create(self, vals_list):
        forced_type = self._get_context_type_deffect()
        if forced_type:
            for vals in vals_list:
                vals['type_deffect'] = forced_type

        return super().create(vals_list)
    
    def _get_rollo_unique_domain(self, rec):
        domain = super()._get_rollo_unique_domain(rec)
        domain.append(('type_deffect', '=', rec.type_deffect))
        return domain

    def _get_rollo_unique_create_domain(self, pedido_line_id, rollo_num):
        domain = super()._get_rollo_unique_create_domain(pedido_line_id, rollo_num)
        type_deffect = self._get_context_type_deffect()
        if type_deffect:
            domain.append(('type_deffect', '=', type_deffect))
        return domain

    def _get_tablet_apariencia_create_vals(self, pedido_line, rollo_num, width, meters):
        vals = super()._get_tablet_apariencia_create_vals(pedido_line, rollo_num, width, meters)
        type_deffect = self._get_context_type_deffect()
        if type_deffect:
            vals['type_deffect'] = type_deffect
        return vals

    @api.model
    def action_tablet_get_partidas(self, query="", limit=20):
        partidas = super().action_tablet_get_partidas(query=query, limit=limit)
        if not partidas:
            return partidas

        line_ids = [partida.get('id') for partida in partidas if partida.get('id')]
        lines = self.env['control.pedido.line'].browse(line_ids)
        lines_by_id = {line.id: line for line in lines}

        for partida in partidas:
            line = lines_by_id.get(partida.get('id'))
            if line and line.design_image:
                partida['design_image_url'] = f"/web/image/control.pedido.line/{line.id}/design_image"
            else:
                partida['design_image_url'] = False

        return partidas

    @api.model
    def action_tablet_get_defectos(self):
        type_deffect = self._get_context_type_deffect() or 'quality'
        defectos = self.env['control.apariencia.defecto'].search(
            [('is_active', '=', True), ('type_deffect', '=', type_deffect)],
            order='name asc, id asc',
        )
        return [
            {
                'defecto_id': defecto.id,
                'name': defecto.name,
                'is_hueco': bool(defecto.is_hueco),
            }
            for defecto in defectos
        ]

    @api.model
    def action_tablet_get_defectos_printing(self, pedido_line_id=False):
        domain = [('is_active', '=', True), ('type_deffect', '=', 'printing')]

        pedido_line_id = int(pedido_line_id or 0)
        printing_type = False
        if pedido_line_id:
            pedido_line = self.env['control.pedido.line'].browse(pedido_line_id)
            if pedido_line.exists() and pedido_line.printing_type in ('digital', 'rotary'):
                printing_type = pedido_line.printing_type

        if printing_type:
            domain += ['|', ('type_printing', '=', printing_type), ('type_printing', '=', 'both')]

        defectos = self.env['control.apariencia.defecto'].search(domain, order='name asc, id asc')
        return [
            {
                'defecto_id': defecto.id,
                'name': defecto.name,
                'is_hueco': bool(defecto.is_hueco),
                'type_printing': defecto.type_printing,
            }
            for defecto in defectos
        ]

    @api.model
    def action_tablet_check_rollo_available_printing(self, pedido_line_id, rollo_num):
        return self.with_context(appearance_type='printing').action_tablet_check_rollo_available(
            pedido_line_id,
            rollo_num,
        )

    @api.model
    def action_tablet_finalize(self, pedido_line_id, rollo_num, selections, width=None, meters=None):
        return super(ControlAparienciaLine, self.with_context(appearance_type='quality')).action_tablet_finalize(
            pedido_line_id,
            rollo_num,
            selections,
            width,
            meters,
        )
    
    @api.model
    def action_tablet_finalize_printing(self, pedido_line_id, rollo_num, selections, width=None, meters=None):
        pedido_line = self.env['control.pedido.line'].browse(int(pedido_line_id))
        if not pedido_line.exists():
            raise UserError(_('The selected batch does not exist.'))

        rollo_num = int(rollo_num or 0)
        if rollo_num <= 0:
            raise UserError(_('The roll number must be greater than 0.'))

        width = float(width or 0.0)
        if width <= 0:
            raise UserError(_('Width must be greater than 0.'))

        meters = float(meters or 0.0)
        if meters <= 0:
            raise UserError(_('Meters must be greater than 0.'))

        create_vals = self.with_context(appearance_type='printing')._get_tablet_apariencia_create_vals(
            pedido_line,
            rollo_num,
            width,
            meters,
        )
        apariencia = self.create(create_vals)

        defect_cmds = []
        for item in selections or []:
            defecto_id = int(item.get('defecto_id') or 0)
            if not defecto_id:
                continue

            defecto = self.env['control.apariencia.defecto'].browse(defecto_id)
            if not defecto.exists():
                continue

            size_codes = [str(code) for code in (item.get('sizes') or []) if str(code) in ('1', '2', '3', '4')]
            if not size_codes:
                fallback_count = int(item.get('count') or 0)
                if fallback_count > 0:
                    size_codes = ['1'] * fallback_count
                else:
                    continue

            defect_cmds.append((0, 0, {
                'defecto_id': defecto.id,
                'printing_quantity': len(size_codes),
                'tamano_defecto_ids': [(0, 0, {'print_size': code}) for code in size_codes],
            }))

        if defect_cmds:
            apariencia.write({'defecto_line_ids': defect_cmds})

        return {'ok': True, 'apariencia_id': apariencia.id}


class ControlAparienciaDefectoLine(models.Model):
    _inherit = 'control.apariencia.defecto.line'

    type_deffect = fields.Selection(related='apariencia_id.type_deffect', store=True)
    printing_quantity = fields.Integer('Quantity')

    @api.depends('tamano_defecto_ids', 'type_deffect', 'printing_quantity')
    def _compute_cantidad(self):
        quality_lines = self.filtered(lambda rec: rec.type_deffect == 'quality')
        printing_lines = self - quality_lines

        if quality_lines:
            super(ControlAparienciaDefectoLine, quality_lines)._compute_cantidad()

        for rec in printing_lines:
            rec.cantidad = int(rec.printing_quantity or 0)

class ControlAparienciaTamanoDefecto(models.Model):
    _inherit = "control.apariencia.tamano.defecto"

    print_size = fields.Selection([
        ('1', 'Hasta 7.62 cm'),
        ('2', '> 7.62 cm y hasta 15.24 cm'),
        ('3', '> 15.24 cm y hasta 22.86 cm'),
        ('4', '> 22.86 cm'),
    ], string='Tamaño del Defecto Estampado')
    