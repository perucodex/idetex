# -*- coding: utf-8 -*-
"""
Asistente para REVERTIR una partición de rollo.

Caso de uso:
  El cajero crea un sub-rollo con "Partir rollo" y se equivoca
  (cantidad mal digitada, rollo equivocado). Antes de venderlo,
  puede revertir: el hijo se ELIMINA y sus kilos vuelven al padre.

Flujo:
  1. Usuario está en "Punto de venta → Existencias PdV" y selecciona
     UN rollo hijo (con idtx_is_split_child=True).
  2. Click en "Acciones → Revertir partición" — abre este wizard.
  3. Wizard muestra: hijo + padre + kilos que se devuelven + kilos
     finales del padre.
  4. Al confirmar: suma quants del hijo al padre, borra quants del
     hijo y borra el stock.lot del hijo.

Validaciones (estrictas — esto es destructivo):
  - Solo 1 rollo seleccionado.
  - El rollo debe tener idtx_is_split_child=True (es decir, fue creado
    por "Partir rollo", NO por devolución).
  - Debe tener idtx_parent_lot_id (padre vivo).
  - El hijo NO debe estar reservado en pedido POS.
  - El hijo NO debe tener movimientos de salida (no se ha vendido/movido).
"""
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class PosRollSplitRevertWizard(models.TransientModel):
    _name = 'pos.roll.split.revert.wizard'
    _description = 'Asistente para Revertir Partición de Rollo'

    # ------------------------------------------------------------------
    # Datos del hijo (a eliminar)
    # ------------------------------------------------------------------
    child_lot_id = fields.Many2one(
        'stock.lot', string='Rollo hijo (a eliminar)',
        required=True, readonly=True,
        help='Lote que será eliminado y cuya cantidad volverá al padre.',
    )
    child_product_id = fields.Many2one(
        'product.product', string='Producto',
        related='child_lot_id.product_id', readonly=True,
    )
    child_qty = fields.Float(
        string='Kg a devolver al padre', readonly=True,
        digits='Product Unit of Measure',
        help='Cantidad actual del rollo hijo que será fusionada de vuelta.',
    )

    # ------------------------------------------------------------------
    # Datos del padre (destino)
    # ------------------------------------------------------------------
    parent_lot_id = fields.Many2one(
        'stock.lot', string='Rollo padre (destino)',
        readonly=True,
        help='Lote padre al cual volverán los kilos del hijo.',
    )
    parent_qty_before = fields.Float(
        string='Kg actual del padre', readonly=True,
        digits='Product Unit of Measure',
    )
    parent_qty_after = fields.Float(
        string='Kg final del padre (vista previa)',
        compute='_compute_parent_qty_after', readonly=True,
        digits='Product Unit of Measure',
    )

    # ------------------------------------------------------------------
    # COMPUTES
    # ------------------------------------------------------------------
    @api.depends('parent_qty_before', 'child_qty')
    def _compute_parent_qty_after(self):
        """ Vista previa de cuánto quedará el padre tras la reversión. """
        for wiz in self:
            wiz.parent_qty_after = (wiz.parent_qty_before or 0.0) + (wiz.child_qty or 0.0)

    # ------------------------------------------------------------------
    # default_get: precarga desde active_ids del list view de Existencias PdV
    # ------------------------------------------------------------------
    @api.model
    def default_get(self, fields_list):
        """
        Valida y precarga los datos del hijo + padre.
        """
        defaults = super().default_get(fields_list)

        # active_model = 'idtx.pos.stock.report' cuando se invoca desde el list view
        active_model = self.env.context.get('active_model')
        active_ids = self.env.context.get('active_ids') or []

        # Validación 1: 1 sólo rollo seleccionado
        if len(active_ids) == 0:
            raise UserError(_('Selecciona un rollo de la lista para revertir.'))
        if len(active_ids) > 1:
            raise UserError(_(
                'Selecciona solo 1 rollo para revertir. Para revertir varias '
                'particiones, hazlo una por una.'
            ))

        if active_model != 'idtx.pos.stock.report':
            return defaults

        # Leer el registro del reporte SQL (tiene lot_id, location_id, quantity)
        report_rec = self.env['idtx.pos.stock.report'].browse(active_ids[0])
        if not report_rec.exists() or not report_rec.lot_id:
            raise UserError(_('No se pudo identificar el rollo. Refresca la vista.'))

        child = report_rec.lot_id

        # Validación 2: debe tener PADRE (es derivado de otro lote)
        # Esto es lo mínimo: sin padre no se puede revertir a ningún lado.
        parent = child.idtx_parent_lot_id
        if not parent:
            raise UserError(_(
                'El rollo %s no tiene padre registrado. No se puede revertir.'
            ) % child.name)
        if not parent.exists():
            raise UserError(_(
                'El rollo padre de %s ya no existe en el sistema. '
                'No se puede revertir.'
            ) % child.name)

        # Validación 3: distinguir splits revertibles de refund children "vivos"
        # ─────────────────────────────────────────────────────────────────────
        # Casos PERMITIDOS:
        #   (A) idtx_is_split_child=True → split creado por el wizard nuevo
        #   (B) Sin asociación con pos_pack_operation_lot → split legacy puro
        #   (C) Asociado solo a pedidos POS en estado 'cancel' → split o refund
        #       cuyo pedido fue cancelado (lote nunca llegó a "vivir")
        #
        # Casos BLOQUEADOS:
        #   (D) Asociado a pedidos POS en estado distinto de cancel
        #       (draft/paid/done/invoiced) → es un refund child o split en uso
        if not child.idtx_is_split_child:
            # Buscar todas las pack_operation_lot que referencien este nombre
            pack_lots = self.env['pos.pack.operation.lot'].search([
                ('lot_name', '=', child.name),
            ])
            # Pedidos POS vivos (no cancelados) asociados a este lote
            live_orders = pack_lots.mapped('pos_order_line_id.order_id').filtered(
                lambda o: o.state != 'cancel'
            )
            if live_orders:
                raise UserError(_(
                    "El rollo %(lote)s está asociado a pedido(s) POS vivos "
                    "(%(pedidos)s). No se puede revertir hasta que esos "
                    "pedidos sean cancelados.\n\n"
                    "Si el lote es un -C## de devolución (no de partición manual), "
                    "usa el flujo de devolución correspondiente — no esta opción."
                ) % {
                    'lote': child.name,
                    'pedidos': ', '.join(live_orders.mapped('name')),
                })

        # Validación 4: el hijo NO debe estar reservado en pedido POS
        if 'pos_reserved_order_id' in child._fields and child.pos_reserved_order_id:
            raise UserError(_(
                "El rollo %(lote)s está comprometido en el pedido POS #%(pedido)s. "
                "Cancela ese pedido antes de revertir la partición."
            ) % {
                'lote': child.name,
                'pedido': child.pos_reserved_order_id.name,
            })

        # Validación 5: no debe tener movimientos de salida (ya vendido/movido)
        # Buscamos stock.move.line en estado 'done' donde el hijo SALIÓ de una
        # ubicación interna. Si existe, significa que ya se usó/vendió.
        out_moves = self.env['stock.move.line'].search([
            ('lot_id', '=', child.id),
            ('state', '=', 'done'),
            ('location_id.usage', '=', 'internal'),
            ('location_dest_id.usage', '!=', 'internal'),
        ], limit=1)
        if out_moves:
            raise UserError(_(
                'El rollo %s ya tiene movimientos de salida (venta/transferencia). '
                'No se puede revertir; usa el flujo de devolución correspondiente.'
            ) % child.name)

        # Validación 6: el hijo debe tener stock interno > 0
        # (si lo movieron a otra ubicación interna lo soportamos sumando todas las quants)
        child_internal_qty = sum(self.env['stock.quant'].search([
            ('lot_id', '=', child.id),
            ('product_id', '=', child.product_id.id),
            ('location_id.usage', '=', 'internal'),
        ]).mapped('quantity'))

        if child_internal_qty <= 0:
            raise UserError(_(
                'El rollo %s no tiene stock interno disponible para devolver. '
                'Refresca la vista — puede que ya esté en cero.'
            ) % child.name)

        # Calcular qty actual del padre (suma de sus quants internas)
        parent_internal_qty = sum(self.env['stock.quant'].search([
            ('lot_id', '=', parent.id),
            ('product_id', '=', parent.product_id.id),
            ('location_id.usage', '=', 'internal'),
        ]).mapped('quantity'))

        # Precargar datos del wizard
        defaults['child_lot_id'] = child.id
        defaults['child_qty'] = child_internal_qty
        defaults['parent_lot_id'] = parent.id
        defaults['parent_qty_before'] = parent_internal_qty

        return defaults

    # ------------------------------------------------------------------
    # ACCIÓN PRINCIPAL: confirmar la reversión
    # ------------------------------------------------------------------
    def action_confirm_revert(self):
        """
        Ejecuta la reversión:
          1. Re-valida estado actual (defensa contra cambios concurrentes).
          2. Suma quants del hijo al padre (en la misma ubicación de cada quant).
          3. Borra quants del hijo (los pone a 0 y los unlink).
          4. Borra el stock.lot del hijo.
        """
        self.ensure_one()

        child = self.child_lot_id
        parent = self.parent_lot_id

        # Re-validar elegibilidad (defensa contra cambios concurrentes):
        # debe ser un split nuevo (flag) o un derivado sin pedidos POS vivos.
        if not child.idtx_is_split_child:
            pack_lots = self.env['pos.pack.operation.lot'].search([
                ('lot_name', '=', child.name),
            ])
            live_orders = pack_lots.mapped('pos_order_line_id.order_id').filtered(
                lambda o: o.state != 'cancel'
            )
            if live_orders:
                raise UserError(_(
                    'El rollo %(lote)s fue asociado a un pedido POS vivo '
                    '(%(pedidos)s) mientras editabas. No se puede revertir.'
                ) % {
                    'lote': child.name,
                    'pedidos': ', '.join(live_orders.mapped('name')),
                })

        # Re-validar reserva (defensa contra concurrencia)
        if 'pos_reserved_order_id' in child._fields and child.pos_reserved_order_id:
            raise UserError(_(
                'El rollo %s fue reservado mientras editabas. No se puede revertir.'
            ) % child.name)

        # Re-validar que no haya salido del stock
        out_moves = self.env['stock.move.line'].search([
            ('lot_id', '=', child.id),
            ('state', '=', 'done'),
            ('location_id.usage', '=', 'internal'),
            ('location_dest_id.usage', '!=', 'internal'),
        ], limit=1)
        if out_moves:
            raise UserError(_(
                'El rollo %s tiene movimientos de salida nuevos. No se puede revertir.'
            ) % child.name)

        # --------------------------------------------------------------
        # 1. Recolectar TODAS las quants del hijo en ubicaciones internas
        # --------------------------------------------------------------
        # sudo() porque algunos usuarios POS no tienen perm directo en quants
        child_quants = self.env['stock.quant'].sudo().search([
            ('lot_id', '=', child.id),
            ('product_id', '=', child.product_id.id),
            ('location_id.usage', '=', 'internal'),
        ])

        if not child_quants:
            raise UserError(_(
                'El rollo %s no tiene quants internas. '
                'Refresca la vista — puede que ya esté en cero.'
            ) % child.name)

        # --------------------------------------------------------------
        # 2. Mover cada quant del hijo a su equivalente del padre
        #    (mismo product, misma location, mismo company)
        # --------------------------------------------------------------
        for cq in child_quants:
            qty_to_return = cq.quantity
            if qty_to_return <= 0:
                continue

            # Buscar (o crear) la quant del padre en esta misma ubicación
            parent_quant = self.env['stock.quant'].sudo().search([
                ('lot_id', '=', parent.id),
                ('product_id', '=', parent.product_id.id),
                ('location_id', '=', cq.location_id.id),
            ], limit=1)

            if parent_quant:
                # Sumar al quant existente
                parent_quant.write({
                    'quantity': parent_quant.quantity + qty_to_return,
                })
            else:
                # Crear quant nueva para el padre en esa ubicación
                self.env['stock.quant'].sudo().create({
                    'product_id': parent.product_id.id,
                    'location_id': cq.location_id.id,
                    'lot_id': parent.id,
                    'quantity': qty_to_return,
                    'in_date': fields.Datetime.now(),
                })

            # Vaciar la quant del hijo
            cq.write({'quantity': 0.0})

        # --------------------------------------------------------------
        # 3. Eliminar los quants del hijo (ya en 0) y luego el stock.lot
        # --------------------------------------------------------------
        # Refrescamos para tomar también quants 0 que pudieran existir
        all_child_quants = self.env['stock.quant'].sudo().search([
            ('lot_id', '=', child.id),
        ])
        all_child_quants.unlink()

        # Guardar el nombre para el mensaje antes de borrar
        child_name = child.name

        # Borrar el lote del hijo (no debería tener movimientos porque ya validamos)
        # sudo() por permisos; si falla por constraints, el rollback automático del ORM
        # deshace todo lo anterior y el usuario ve el error.
        child.sudo().unlink()

        # --------------------------------------------------------------
        # 4. Recargar la lista para mostrar el cambio
        # --------------------------------------------------------------
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
