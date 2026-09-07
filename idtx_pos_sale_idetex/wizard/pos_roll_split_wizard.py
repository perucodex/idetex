# -*- coding: utf-8 -*-
"""
Asistente para PARTIR un rollo en dos pedazos físicos.

Flujo:
  1. Usuario está en "Punto de venta → Existencias PdV" (vista list de
     idtx.pos.stock.report). Selecciona UN rollo.
  2. Click en menú "Acciones → Partir rollo" — abre este wizard.
  3. Wizard muestra datos del rollo (nombre, producto, color, kilos disponibles)
     y campo editable "Kilos del nuevo rollo".
  4. Vista previa en vivo: cuántos kg quedarán en el padre + cómo se llamará
     el nuevo rollo (Partida-C##, mismo correlativo que devoluciones).
  5. Al confirmar: crea stock.lot nuevo con idtx_parent_lot_id apuntando al
     padre, mueve los kg pedidos en stock.quant del padre al hijo (en la
     misma ubicación interna).

Validaciones:
  - Solo 1 rollo seleccionado (rechaza múltiple).
  - El rollo no debe estar reservado por un pedido POS draft.
  - 0 < qty < total disponible del padre.
"""
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class PosRollSplitWizard(models.TransientModel):
    _name = 'pos.roll.split.wizard'
    _description = 'Asistente para Partir Rollo'

    # ------------------------------------------------------------------
    # Datos del rollo padre (cargados en default_get desde active_ids)
    # ------------------------------------------------------------------
    lot_id = fields.Many2one(
        'stock.lot', string='Rollo origen', required=True, readonly=True,
        help='Lote del cual se va a separar el nuevo rollo.',
    )
    product_id = fields.Many2one(
        'product.product', string='Producto', related='lot_id.product_id', readonly=True,
    )
    color_name = fields.Char(
        string='Color', compute='_compute_color_info', readonly=True,
    )
    parent_qty = fields.Float(
        string='Kilos disponibles', readonly=True, digits='Product Unit of Measure',
        help='Cantidad actual del rollo padre (la suma de stock interno).',
    )
    location_id = fields.Many2one(
        'stock.location', string='Ubicación origen', readonly=True,
    )

    # ------------------------------------------------------------------
    # Datos del nuevo rollo (editables / computados)
    # ------------------------------------------------------------------
    split_qty = fields.Float(
        string='Kilos del nuevo rollo', required=True,
        digits='Product Unit of Measure',
    )
    remaining_qty = fields.Float(
        string='Kg que quedará en el padre',
        compute='_compute_preview', readonly=True,
        digits='Product Unit of Measure',
        help='Vista previa: cuántos kilos quedarán en el rollo padre después de la partición.',
    )
    new_lot_name = fields.Char(
        string='Nombre del nuevo rollo',
        compute='_compute_preview', readonly=True,
        help='Se calcula como el siguiente correlativo Partida-C## (igual lógica que devoluciones).',
    )

    # ------------------------------------------------------------------
    # COMPUTES
    # ------------------------------------------------------------------
    @api.depends('lot_id')
    def _compute_color_info(self):
        """ Obtiene el nombre del color del rollo padre, si el campo existe. """
        for wiz in self:
            wiz.color_name = ''
            if wiz.lot_id and 'color_name' in wiz.lot_id._fields:
                wiz.color_name = wiz.lot_id.color_name or ''

    @api.depends('lot_id', 'split_qty', 'parent_qty')
    def _compute_preview(self):
        """
        Calcula en vivo:
          - remaining_qty: lo que queda en el padre = parent_qty - split_qty
          - new_lot_name: el siguiente nombre Partida-C## (usa la lógica
            existente de get_next_refund_lot_names)
        """
        for wiz in self:
            wiz.remaining_qty = (wiz.parent_qty or 0.0) - (wiz.split_qty or 0.0)
            wiz.new_lot_name = ''
            if wiz.lot_id and (wiz.split_qty or 0) > 0:
                # Reutilizamos el helper existente — mismo correlativo C## que devoluciones
                next_names = self.env['pos.order'].get_next_refund_lot_names([wiz.lot_id.name])
                wiz.new_lot_name = next_names.get(wiz.lot_id.name, '')

    # ------------------------------------------------------------------
    # default_get: precarga el wizard a partir del active_id del list view
    # ------------------------------------------------------------------
    @api.model
    def default_get(self, fields_list):
        """
        Al abrir el wizard desde el menú "Acciones" del list view de
        idtx.pos.stock.report, leemos los active_ids del contexto.
        Validamos que sea EXACTAMENTE 1 rollo y precargamos sus datos.
        """
        defaults = super().default_get(fields_list)

        # active_model será 'idtx.pos.stock.report' cuando se invoca desde su list view
        active_model = self.env.context.get('active_model')
        active_ids = self.env.context.get('active_ids') or []

        # Validación 1: 1 sólo rollo seleccionado
        if len(active_ids) == 0:
            raise UserError(_('Selecciona un rollo de la lista para partir.'))
        if len(active_ids) > 1:
            raise UserError(_(
                'Selecciona solo 1 rollo para partir. Para partir varios rollos, '
                'haz la operación uno por uno.'
            ))

        # Si por algún motivo se invoca desde otro modelo, ignoramos
        if active_model != 'idtx.pos.stock.report':
            return defaults

        # Cargar el registro de la vista SQL — tiene lot_id, location_id y quantity
        report_rec = self.env['idtx.pos.stock.report'].browse(active_ids[0])
        if not report_rec.exists() or not report_rec.lot_id:
            raise UserError(_('No se pudo identificar el rollo. Refresca la vista.'))

        # Validación 2: el rollo no debe estar reservado
        # Buscamos el stock.lot real y verificamos pos_reserved_order_id
        lot = report_rec.lot_id
        if 'pos_reserved_order_id' in lot._fields and lot.pos_reserved_order_id:
            raise UserError(_(
                "El rollo %(lote)s está comprometido en el pedido POS #%(pedido)s.\n"
                "Cancela ese pedido primero antes de partir el rollo."
            ) % {
                'lote': lot.name,
                'pedido': lot.pos_reserved_order_id.name,
            })

        # Validación 3: debe haber stock para partir
        if (report_rec.quantity or 0) <= 0:
            raise UserError(_(
                'El rollo %s no tiene stock disponible para partir.'
            ) % lot.name)

        # Precargar campos del wizard
        defaults['lot_id'] = lot.id
        defaults['parent_qty'] = report_rec.quantity
        defaults['location_id'] = report_rec.location_id.id
        # Default a la mitad como sugerencia visual (cajero puede cambiarlo)
        if 'split_qty' in fields_list:
            defaults['split_qty'] = 0.0

        return defaults

    # ------------------------------------------------------------------
    # ACCIÓN PRINCIPAL: confirmar la partición
    # ------------------------------------------------------------------
    def action_confirm_split(self):
        """
        Ejecuta la partición:
          1. Re-valida en este momento (datos pueden haber cambiado mientras
             el wizard estaba abierto).
          2. Crea el nuevo stock.lot Partida-C## con idtx_parent_lot_id al padre.
          3. Decrementa stock.quant del padre por split_qty.
          4. Crea stock.quant del hijo con split_qty en la misma ubicación.
        """
        self.ensure_one()

        # Re-validaciones en el momento de confirmar (defensa contra cambios concurrentes)
        if self.split_qty <= 0:
            raise UserError(_('La cantidad a partir debe ser mayor a 0.'))

        # Tolerancia para comparación de floats (1 gramo)
        if self.split_qty >= self.parent_qty - 0.001:
            raise UserError(_(
                'La cantidad a partir (%(split).2f Kg) debe ser MENOR que el total '
                'disponible (%(total).2f Kg). Si quieres mover todo, no hace falta partir.'
            ) % {'split': self.split_qty, 'total': self.parent_qty})

        # Re-leer reserva por si cambió mientras editaban
        lot = self.lot_id
        if 'pos_reserved_order_id' in lot._fields and lot.pos_reserved_order_id:
            raise UserError(_(
                'El rollo %s fue reservado por un pedido POS mientras editabas. '
                'No se puede partir.'
            ) % lot.name)

        # --------------------------------------------------------------
        # 1. Generar nombre del hijo (mismo correlativo C## que devoluciones)
        # --------------------------------------------------------------
        next_names = self.env['pos.order'].get_next_refund_lot_names([lot.name])
        new_name = next_names.get(lot.name)
        if not new_name:
            raise UserError(_('No se pudo generar el nombre del nuevo rollo.'))

        # --------------------------------------------------------------
        # 2. Crear el nuevo stock.lot con trazabilidad al padre
        # --------------------------------------------------------------
        new_lot_vals = {
            'name': new_name,
            'product_id': lot.product_id.id,
            'company_id': lot.company_id.id,
        }
        # idtx_parent_lot_id existe en este módulo — enlaza al padre
        if 'idtx_parent_lot_id' in self.env['stock.lot']._fields:
            new_lot_vals['idtx_parent_lot_id'] = lot.id
        # Marcador para identificar este lote como "nacido de partición manual" —
        # solo los lotes con este flag aparecerán como revertibles en el wizard
        # de "Revertir partición" (separa splits físicos de los -C## de devolución).
        if 'idtx_is_split_child' in self.env['stock.lot']._fields:
            new_lot_vals['idtx_is_split_child'] = True
        # El override de stock_lot.create() llena ref + color heredado del padre
        new_lot = self.env['stock.lot'].create(new_lot_vals)

        # --------------------------------------------------------------
        # 3. Mover qty del padre al hijo en stock.quant
        # --------------------------------------------------------------
        # Buscar todas las quants internas del padre
        parent_quants = self.env['stock.quant'].search([
            ('lot_id', '=', lot.id),
            ('product_id', '=', lot.product_id.id),
            ('location_id.usage', '=', 'internal'),
        ])

        # Decrementar quants del padre tomando first-found hasta cubrir split_qty
        # (en textil Idetex normalmente hay 1 quant por lote, así que esto
        # toma todo de una; soporta múltiples por robustez)
        qty_pendiente = self.split_qty
        location_for_child = False
        for q in parent_quants:
            if qty_pendiente <= 0:
                break
            take = min(q.quantity, qty_pendiente)
            q.write({'quantity': q.quantity - take})
            qty_pendiente -= take
            if not location_for_child:
                location_for_child = q.location_id.id

        if not location_for_child:
            # No había quants — caso defensivo, ya validamos arriba
            raise UserError(_(
                'No se encontró stock interno del rollo %s. '
                'Verifica el inventario.'
            ) % lot.name)

        # Crear quant para el hijo en la misma ubicación
        # sudo() por si el usuario del POS no tiene perm directo de escritura en quants
        self.env['stock.quant'].sudo().create({
            'product_id': lot.product_id.id,
            'location_id': location_for_child,
            'lot_id': new_lot.id,
            'quantity': self.split_qty,
            'in_date': fields.Datetime.now(),
        })

        # --------------------------------------------------------------
        # 4. Feedback al usuario: cerrar el wizard y recargar la lista
        # --------------------------------------------------------------
        # Devolvemos una acción que cierra + recarga el list view para que
        # el usuario vea inmediatamente los dos rollos (padre con qty menor
        # + hijo nuevo con su qty).
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
