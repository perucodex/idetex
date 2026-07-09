# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MrpWorkorderBatchSplit(models.TransientModel):
    """Divide una partida en sub-partidas (<nombre>-A, <nombre>-B, ...).

    Propone la agrupación por PRODUCTO (el caso típico: productos que tras el
    teñido siguen rutas/máquinas distintas), editable rollo por rollo.
    """

    _name = 'mrp.workorder.batch.split'
    _description = 'Dividir partida en sub-partidas'

    batch_id = fields.Many2one('mrp.workorder.batch', required=True, readonly=True)
    line_ids = fields.One2many('mrp.workorder.batch.split.line', 'wizard_id',
                               string='Rollos')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        batch = self.env['mrp.workorder.batch'].browse(res.get('batch_id'))
        if not batch:
            return res
        # Grupo propuesto = por producto (A, B, C... en orden de aparición).
        code_by_product = {}
        lines = []
        for roll in batch.wo_roll_ids:
            product = roll.product_id
            if product not in code_by_product:
                n = len(code_by_product)
                code_by_product[product] = (
                    chr(65 + n) if n < 26 else 'A%s' % (n - 25))
            lines.append((0, 0, {
                'roll_id': roll.id,
                'group_code': code_by_product[product],
            }))
        res['line_ids'] = lines
        return res

    def action_split(self):
        self.ensure_one()
        Roll = self.env['mrp.workorder.roll']
        groups = {}
        for line in self.line_ids:
            code = (line.group_code or '').strip().upper()
            if not code:
                raise UserError(_(
                    'Asigna un grupo al rollo %s.') % (line.roll_id.name or line.roll_id.id))
            groups.setdefault(code, Roll)
            groups[code] |= line.roll_id
        children = self.batch_id._apply_split(groups)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sub-partidas de %s') % self.batch_id.name,
            'res_model': 'mrp.workorder.batch',
            'view_mode': 'list,form',
            'domain': [('id', 'in', children.ids)],
        }


class MrpWorkorderBatchSplitLine(models.TransientModel):
    _name = 'mrp.workorder.batch.split.line'
    _description = 'Línea de división de partida'
    _order = 'group_code, id'

    wizard_id = fields.Many2one('mrp.workorder.batch.split', required=True,
                                ondelete='cascade')
    roll_id = fields.Many2one('mrp.workorder.roll', string='Rollo',
                              required=True, readonly=True)
    workorder_id = fields.Many2one(related='roll_id.workorder_id', string='Orden de trabajo')
    production_id = fields.Many2one(related='roll_id.workorder_id.production_id',
                                    string='Orden de fabricación')
    product_id = fields.Many2one(related='roll_id.product_id', string='Producto')
    gross_weight = fields.Float(related='roll_id.gross_weight', string='Peso Bruto')
    group_code = fields.Char('Grupo', required=True,
                             help='Rollos con el mismo grupo forman una sub-partida '
                                  '(<partida>-<grupo>).')
