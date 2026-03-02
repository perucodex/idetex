from odoo import api, fields, models
from odoo.exceptions import UserError

class ControlAparienciaLine(models.Model):
    _inherit = 'control.apariencia.line'
    
    type_deffect = fields.Selection([
        ('quality', 'Quality'),
        ('printing', 'Printing'),
    ], string='Deffect Type')
    
    def _get_rollo_unique_domain(self, rec):
        domain = super()._get_rollo_unique_domain(rec)
        domain.append(('type_deffect', '=', rec.type_deffect))
        return domain

    def _get_rollo_unique_create_domain(self, pedido_line_id, rollo_num):
        domain = super()._get_rollo_unique_create_domain(pedido_line_id, rollo_num)
        appearance_type = self.env.context.get('appearance_type', 'quality')
        if appearance_type in ('quality', 'printing'):
            domain.append(('type_deffect', '=', appearance_type))
        return domain

    def _get_tablet_apariencia_create_vals(self, pedido_line, rollo_num):
        vals = super()._get_tablet_apariencia_create_vals(pedido_line, rollo_num)
        appearance_type = self.env.context.get('appearance_type')
        if appearance_type in ('quality', 'printing'):
            vals['type_deffect'] = appearance_type
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
    def action_tablet_get_defectos_printing(self):
        defectos = self.env['control.apariencia.defecto'].search(
            [('is_active', '=', True),('type_deffect', '=', 'printing')], order='name asc, id asc'
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
    def action_tablet_check_rollo_available_printing(self, pedido_line_id, rollo_num):
        return self.with_context(appearance_type='printing').action_tablet_check_rollo_available(
            pedido_line_id,
            rollo_num,
        )

    @api.model
    def action_tablet_finalize(self, pedido_line_id, rollo_num, selections):
        return super(ControlAparienciaLine, self.with_context(appearance_type='quality')).action_tablet_finalize(
            pedido_line_id,
            rollo_num,
            selections,
        )
    
    @api.model
    def action_tablet_finalize_printing(self, pedido_line_id, rollo_num, selections):
        pedido_line = self.env['control.pedido.line'].browse(int(pedido_line_id))
        if not pedido_line.exists():
            raise UserError('La partida seleccionada no existe.')

        rollo_num = int(rollo_num or 0)
        if rollo_num <= 0:
            raise UserError('El N° Rollo debe ser mayor a 0.')

        create_vals = self.with_context(appearance_type='printing')._get_tablet_apariencia_create_vals(
            pedido_line,
            rollo_num,
        )
        apariencia = self.create(create_vals)

        defect_cmds = []
        for item in selections or []:
            defecto_id = int(item.get('defecto_id') or 0)
            count = int(item.get('count') or 0)
            if not defecto_id:
                continue

            defecto = self.env['control.apariencia.defecto'].browse(defecto_id)
            if not defecto.exists():
                continue

            defect_cmds.append((0, 0, {
                'defecto_id': defecto.id,
                'printing_quantity': count,
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
