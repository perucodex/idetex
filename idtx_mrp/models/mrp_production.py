# -*- coding: utf-8 -*-

import logging

from odoo import api, fields, models, _
from odoo.fields import Command
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    batch_id = fields.Many2one('mrp.workorder.batch', string='Batch')
    roll_ids = fields.One2many('mrp.production.roll', 'production_id', string='Rolls')
    # Rollos CRUDOS de la OF (tejidos en sus OTs o recibidos del cliente).
    wo_roll_ids = fields.One2many('mrp.workorder.roll', 'production_id', string='Rollos Crudos')
    reception_ids = fields.One2many('mrp.roll.reception', 'production_id', string='Recepciones de crudo')
    reception_count = fields.Integer(compute='_compute_reception_stats')
    customer_roll_count = fields.Integer(compute='_compute_reception_stats')
    customer_roll_weight = fields.Float(compute='_compute_reception_stats')
    has_weaving_workorder = fields.Boolean(compute='_compute_can_receive_customer_rolls')
    # OF de SERVICIO sin OT de tejido: el crudo lo trae el cliente.
    can_receive_customer_rolls = fields.Boolean(compute='_compute_can_receive_customer_rolls')
    production_type = fields.Selection([
        ('sale', 'Sale'),
        ('service', 'Service'),
        ('pilot', 'Pilot'),
        ('sample', 'Sample'),
        ('reposicion', 'Reposición'),
    ], string='Production Type', required=True,
        # Sin default: en una OF creada a mano el usuario DEBE elegir el tipo
        # (antes nacia como "Venta" en silencio). Las creaciones automaticas lo
        # fijan explicitamente: pedido de venta (sale_type del pedido),
        # reposicion ('reposicion') y reglas de abastecimiento (stock.rule).
        help='Obligatorio. Con pedido de venta se hereda del tipo de venta; '
             'en una OF libre (muestra, piloto) lo elige el usuario.')

    @api.depends('reception_ids.state', 'wo_roll_ids.origin', 'wo_roll_ids.gross_weight')
    def _compute_reception_stats(self):
        for rec in self:
            rec.reception_count = len(rec.reception_ids.filtered(lambda r: r.state != 'cancel'))
            customer_rolls = rec.wo_roll_ids.filtered(lambda r: r.origin == 'customer')
            rec.customer_roll_count = len(customer_rolls)
            rec.customer_roll_weight = sum(customer_rolls.mapped('gross_weight'))

    @api.depends('production_type', 'state', 'workorder_ids.operation_type',
                 'workorder_ids.workcenter_id.operation_type', 'workorder_ids.state')
    def _compute_can_receive_customer_rolls(self):
        for rec in self:
            rec.has_weaving_workorder = rec._has_weaving_workorder()
            rec.can_receive_customer_rolls = (
                rec.production_type == 'service'
                and not rec.has_weaving_workorder
                and rec.state in ('confirmed', 'progress', 'to_close'))

    def _has_weaving_workorder(self):
        self.ensure_one()
        # Por operación LAB (mrwo_id) O por centro de trabajo: una OT de la
        # tejeduría con la operación LAB mal enlazada sigue siendo tejido.
        return bool(self.workorder_ids.filtered(
            lambda wo: wo.state != 'cancel'
            and 'weaving' in (wo.operation_type, wo.workcenter_id.operation_type)))

    def action_receive_customer_rolls(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Recibir rollos del cliente'),
            'res_model': 'mrp.roll.reception',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_production_id': self.id},
        }

    def action_view_receptions(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('idtx_mrp.mrp_roll_reception_action')
        action['domain'] = [('production_id', '=', self.id)]
        action['context'] = {'default_production_id': self.id}
        return action

    def _remove_thread_components_without_weaving(self):
        """OF de SERVICIO sin OT de tejido: la tela cruda la trae el cliente,
        así que el HILO de la LdM nunca se consumirá (el consumo de hilo se
        dispara al cerrar la OT de tejido, que aquí no existe). El componente
        y su traslado a preproducción se ELIMINAN de la OF (JP, 10-sep-2026:
        "esa línea ya no debería existir"), no solo se cancelan: un movimiento
        cancelado seguía mostrándose en Componentes como "No disponible".

        Idempotente: también limpia OF donde el hilo quedó cancelado por la
        versión anterior (movimientos en estado cancel)."""
        StockMove = self.env['stock.move']
        for production in self.filtered(lambda p: p.production_type == 'service'):
            if production._has_weaving_workorder():
                continue
            moves = production.move_raw_ids.filtered(
                lambda m: m.state != 'done'
                and 'is_thread' in m.product_id._fields and m.product_id.is_thread)
            if not moves:
                continue
            detail = ', '.join('%s (%.2f)' % (m.product_id.display_name, m.product_uom_qty) for m in moves)
            # Traslado de hilo a preproducción que alimenta al componente. Tras
            # cancelar se pierde el enlace orig/dest, así que además se busca
            # por grupo de producción + producto (movimientos ya cancelados).
            feeding = moves.move_orig_ids.filtered(lambda m: m.state != 'done')
            if production.production_group_id:
                feeding |= StockMove.search([
                    ('production_group_id', '=', production.production_group_id.id),
                    ('product_id', 'in', moves.product_id.ids),
                    ('raw_material_production_id', '=', False),
                    ('production_id', '=', False),
                    ('picking_id', '!=', False),
                    ('state', '!=', 'done'),
                ])
            pickings = feeding.picking_id
            to_cancel = (feeding | moves).filtered(lambda m: m.state != 'cancel')
            # skip_mo_check: el core CANCELA LA OF entera cuando quedan todos
            # sus componentes cancelados (mrp/stock_move._action_cancel); aquí
            # la OF sigue viva, solo se le quita el hilo.
            if to_cancel:
                to_cancel.with_context(skip_mo_check=True)._action_cancel()
            (feeding | moves).unlink()
            # El traslado queda vacío: se elimina para que la OF no muestre un
            # traslado cancelado de un insumo que nunca existió.
            pickings.filtered(lambda p: not p.move_ids).unlink()
            production.message_post(body=_(
                'OF de servicio sin tejido: se eliminó el componente de hilo %s '
                'y su traslado a preproducción. El crudo lo entrega el cliente.', detail))

    @api.depends('bom_id', 'product_id', 'qty_producing', 'product_uom_id', 'never_product_template_attribute_value_ids')
    def _compute_workorder_ids(self):
        res = super()._compute_workorder_ids()
        for rec in self:
            for wo in rec.workorder_ids:
                # Solo sincronizar desde la operación de LdM cuando existe:
                # este compute se re-ejecuta ante muchos cambios (p.ej.
                # qty_producing) y pisar mrwo_id con False borraba la
                # Operación LAB de las OTs sin operación de LdM enlazada.
                op = wo.operation_id.operation_id
                if op and wo.mrwo_id != op:
                    wo.mrwo_id = op
        return res

    def _roll_done_qty(self, final=False):
        self.ensure_one()
        total_done = 0.0
        if final:
            wo_rolls = self.roll_ids
        else:
            wo_rolls = self.workorder_ids.mapped('roll_ids')
        for roll in wo_rolls:
            weight = float(roll.gross_weight or 0.0)
            if weight > 0:
                total_done += weight
                continue
            qty = float(roll.quantity or 0.0)
            if qty > 0:
                total_done += qty
        return total_done

    def _roll_qty_sync_targets(self):
        """Punto de extensión para definir dónde aplica la sincronización por rollos."""
        # El comportamiento por defecto aplica al recordset actual.
        # Los módulos dependientes pueden sobrescribir para filtrar objetivos (p. ej. solo tejido).
        return self

    def _sync_qty_producing_from_production_rolls(self):
        for production in self._roll_qty_sync_targets():
            # qty_producing debe provenir solo de los rollos finalizados.
            production.qty_producing = production._roll_done_qty(True)

    def _consume_woven_thread(self):
        """Consume el HILO al cerrar la operación de TEJIDO.

        El hilo se gasta en la tejedora, así que ahí debe salir del almacén:
        mientras se tejen rollos la cantidad consumida del componente va
        subiendo (se ve en el Taller), y al cerrar la OT de tejido esos kilos
        se descuentan de verdad y las bolsas usadas pasan a "Consumida".

        Antes esto no ocurría nunca: en este flujo la OF no se cierra con
        "Producir" (el stock del producto nace al pesar cada rollo), así que
        los movimientos de hilo se quedaban en 'assigned' para siempre y el
        hilo ya gastado seguía contando como disponible.
        """
        for production in self:
            if production.state in ('draft', 'cancel'):
                continue
            tejido = production.workorder_ids.filtered(
                lambda wo: wo.operation_type == 'weaving')
            # Solo cuando el tejido terminó: si quedan OTs de tejido abiertas
            # (o reabiertas por reproceso) todavía puede sumarse consumo.
            if not tejido or tejido.filtered(lambda wo: wo.state not in ('done', 'cancel')):
                continue
            # Y solo si realmente se tejió algo.
            if not tejido.mapped('roll_ids'):
                continue
            # Se consume lo RESERVADO (venga de elegir bolsas o de los kilos
            # por lote de la pantalla de opciones de tejeduría). Lo que sobró en
            # máquina y las bolsas no usadas se corrigen después por inventario.
            hilo = production.move_raw_ids.filtered(
                lambda m: m.product_id.is_thread
                and m.state not in ('done', 'cancel')
                and m.quantity > 0)
            if not hilo:
                continue
            try:
                consumido = [(m.product_id.display_name, m.quantity) for m in hilo]
                hilo.picked = True
                hilo._action_done()
                production.message_post(body=_(
                    'Hilo consumido al cerrar el tejido: %s',
                    ', '.join('%s (%.2f kg)' % (nombre, qty)
                              for nombre, qty in consumido)))
            except Exception as e:  # noqa: BLE001 - no debe bloquear el cierre de la OT
                _logger.warning(
                    'No se pudo consumir el hilo de %s: %s', production.name, e)

    def button_mark_done(self):
        targets = self._roll_qty_sync_targets()
        for production in targets:
            if not production.roll_ids:
                continue

            # Rollos PESADOS en "Pesado de rollos": su quant ya se creó al
            # pesar (modo inventario). Volver a producir duplicaría el stock.
            weighed = production.roll_ids.filtered('weighed_date')
            if weighed:
                raise UserError(_(
                    'La OF %(prod)s tiene rollos pesados en "Pesado de rollos" '
                    '(su stock ya se generó al pesar): no se puede volver a '
                    'producir. Rollos: %(rolls)s',
                    prod=production.name,
                    rolls=', '.join(weighed.mapped('lot_id.name'))))

            # En tejido, el qty_produced de la orden de trabajo puede representar
            # tela intermedia (no rollos finales empacados). Se reinicia para que
            # el cierre final de la MO use solo lotes de rollos.
            # El core prohíbe cambiar qty_produced en workorders done/cancel.
            wo_to_reset = production.workorder_ids.filtered(lambda wo: wo.state not in ('done', 'cancel'))
            if wo_to_reset:
                wo_to_reset.write({'qty_produced': 0.0})
            if production.qty_produced:
                production.qty_produced = 0.0
            roll_lot_ids = production.roll_ids.mapped('lot_id').ids
            # Restricción del core: para productos con tracking por lote,
            # solo se permite un lot_producing_id.
            # Los lotes por rollo se conservan en líneas del movimiento final;
            # aquí se define un único lote principal.
            if production.product_tracking == 'lot':
                production.lot_producing_ids = [Command.set(roll_lot_ids[:1])]
            else:
                production.lot_producing_ids = [Command.set(roll_lot_ids)]

            missing_lot_rolls = production.roll_ids.filtered(lambda r: not r.lot_id)
            if missing_lot_rolls:
                raise UserError(_("All finished rolls must have a lot before producing."))

            total_qty = production._roll_done_qty(final=True)
            if total_qty <= 0:
                raise UserError(_("Finished roll quantity must be greater than zero before producing."))

            open_finished_moves = production.move_finished_ids.filtered(
                lambda m: m.product_id == production.product_id and m.state not in ('done', 'cancel')
            )
            finished_move = open_finished_moves[:1]
            if not finished_move:
                # Reconstruye movimientos finales faltantes (puede ocurrir tras cancelaciones/ediciones previas).
                production._create_update_move_finished()
                open_finished_moves = production.move_finished_ids.filtered(
                    lambda m: m.product_id == production.product_id and m.state not in ('done', 'cancel')
                )
                finished_move = open_finished_moves[:1]
            if not finished_move:
                # Último fallback: crear un movimiento final nuevo para el producto principal.
                move_vals = production._get_move_finished_values(
                    production.product_id.id,
                    total_qty,
                    production.product_uom_id.id,
                )
                finished_move = self.env['stock.move'].create(move_vals)
                if finished_move.state == 'draft':
                    finished_move._action_confirm()
            if not finished_move:
                raise UserError(_("No active finished move found for %(mo)s.", mo=production.display_name))

            # Mantener solo un movimiento final activo del producto principal.
            # Movimientos abiertos extra generan lotes/cantidades duplicadas en _post_inventory.
            extra_open_moves = (production.move_finished_ids.filtered(
                lambda m: m.product_id == production.product_id and m.state not in ('done', 'cancel')
            ) - finished_move)
            if extra_open_moves:
                extra_open_moves.with_context(skip_mo_check=True)._action_cancel()

            line_commands = [Command.clear()]
            for roll in production.roll_ids:
                roll_qty = float(roll.gross_weight or 0.0) or float(roll.quantity or 0.0)
                if roll_qty <= 0:
                    continue
                vals = finished_move._prepare_move_line_vals(quantity=roll_qty)
                vals.update({
                    'lot_id': roll.lot_id.id,
                    'quantity': roll_qty,
                    'picked': True,
                })
                line_commands.append(Command.create(vals))

            if len(line_commands) == 1:
                raise UserError(_("Finished rolls must have a positive quantity/weight to create lot moves."))

            finished_move.move_line_ids = line_commands
            # Mantener qty_produced en 0 antes de _post_inventory; el core marcará
            # picked y publicará este movimiento con el total de rollos.
            finished_move.picked = False
            finished_move.quantity = total_qty
            finished_move.product_uom_qty = total_qty
            production.qty_producing = total_qty
            production.qty_produced = 0.0

        ctx = dict(self.env.context, skip_consumption=True)
        return super(MrpProduction, self.with_context(ctx)).button_mark_done()

    def action_confirm(self):
        res = super().action_confirm()
        self.picking_ids.action_assign()
        self._remove_thread_components_without_weaving()
        return res
