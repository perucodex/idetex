from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

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
    def action_tablet_finalize_printing(self, pedido_line_id, rollo_num, selections):
        pedido_line = self.env['control.pedido.line'].browse(int(pedido_line_id))
        if not pedido_line.exists():
            raise UserError('La partida seleccionada no existe.')

        rollo_num = int(rollo_num or 0)
        if rollo_num <= 0:
            raise UserError('El N° Rollo debe ser mayor a 0.')

        apariencia = self.create({
            'pedido_line_id': pedido_line.id,
            'rollo_num': rollo_num,
            'type_deffect': 'printing',
        })

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
