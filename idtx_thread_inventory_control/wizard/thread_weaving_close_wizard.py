# -*- coding: utf-8 -*-
"""Liquidación del hilo al cerrar la operación de TEJIDO.

El tejedor separa bolsas para la OT (reserva), teje rollos y, al terminar, baja
de la máquina el hilo que sobró. Esta pantalla cierra ese ciclo declarando qué
pasó con cada kilo:

    bolsas usadas = tela tejida + hilo devuelto a 2da + merma

- Bolsas usadas: se consumen completas (salen del almacén de hilo).
- Hilo bajado de máquina: se pesa, se dice en cuántas bolsas y con cuántos
  conos, y entra al almacén de 2da calidad como bolsas nuevas.
- Merma: la diferencia, que se registra como desecho desde Producción (no
  vuelve a descontar el almacén: ese hilo ya salió al consumirse).
- Bolsas que no se abrieron: solo se libera la reserva, vuelven a Disponible.
"""

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero


class ThreadWeavingCloseWizard(models.TransientModel):
    _name = 'thread.weaving.close.wizard'
    _description = 'Liquidación de hilo al cerrar tejido'

    workorder_id = fields.Many2one(
        'mrp.workorder', string='Orden de Trabajo', required=True)
    production_id = fields.Many2one(
        related='workorder_id.production_id', string='Orden de Fabricación')
    company_id = fields.Many2one(related='workorder_id.company_id')

    woven_qty = fields.Float(
        'Tela Tejida (kg)', digits=(16, 2),
        help='Suma del peso de los rollos tejidos en esta orden de trabajo.')
    roll_count = fields.Integer('Rollos Tejidos')

    bag_line_ids = fields.One2many(
        'thread.weaving.close.wizard.bag', 'wizard_id', string='Bolsas Separadas')
    return_line_ids = fields.One2many(
        'thread.weaving.close.wizard.return', 'wizard_id',
        string='Hilo Bajado de Máquina')

    second_location_id = fields.Many2one(
        'stock.location', string='Almacén 2da Calidad',
        domain="[('usage', '=', 'internal')]",
        help='Dónde entra el hilo que se bajó de la máquina.')
    available_lot_ids = fields.Many2many(
        'stock.lot', string='Lotes usados', compute='_compute_available_lots',
        help='Lotes de las bolsas marcadas como usadas: el hilo bajado de la '
             'máquina solo puede venir de una bolsa que se abrió.')

    @api.depends('bag_line_ids.lot_id', 'bag_line_ids.used')
    def _compute_available_lots(self):
        for wiz in self:
            wiz.available_lot_ids = wiz.bag_line_ids.filtered('used').mapped('lot_id')

    # --- Balance (en pantalla) ---
    reserved_qty = fields.Float(
        'Separado (kg)', compute='_compute_balance', digits=(16, 2))
    used_qty = fields.Float(
        'Bolsas Usadas (kg)', compute='_compute_balance', digits=(16, 2))
    used_bags = fields.Integer('Bolsas Usadas', compute='_compute_balance')
    released_qty = fields.Float(
        'Reserva Liberada (kg)', compute='_compute_balance', digits=(16, 2))
    released_bags = fields.Integer('Bolsas Liberadas', compute='_compute_balance')
    returned_qty = fields.Float(
        'Devuelto a 2da (kg)', compute='_compute_balance', digits=(16, 2))
    returned_bags = fields.Integer('Bolsas a 2da', compute='_compute_balance')
    returned_cones = fields.Integer('Conos a 2da', compute='_compute_balance')
    waste_qty = fields.Float(
        'Merma (kg)', compute='_compute_balance', digits=(16, 2))
    waste_pct = fields.Float(
        'Merma (%)', compute='_compute_balance', digits=(16, 2))
    balance_warning = fields.Char(compute='_compute_balance')

    @api.depends('bag_line_ids.used', 'bag_line_ids.net_weight',
                 'return_line_ids.weight', 'return_line_ids.cone_qty',
                 'woven_qty')
    def _compute_balance(self):
        for wiz in self:
            usadas = wiz.bag_line_ids.filtered('used')
            libres = wiz.bag_line_ids - usadas
            wiz.reserved_qty = sum(wiz.bag_line_ids.mapped('net_weight'))
            wiz.used_qty = sum(usadas.mapped('net_weight'))
            wiz.used_bags = len(usadas)
            wiz.released_qty = sum(libres.mapped('net_weight'))
            wiz.released_bags = len(libres)
            wiz.returned_qty = sum(wiz.return_line_ids.mapped('weight'))
            wiz.returned_bags = len(wiz.return_line_ids)
            wiz.returned_cones = sum(wiz.return_line_ids.mapped('cone_qty'))
            merma = wiz.used_qty - wiz.woven_qty - wiz.returned_qty
            wiz.waste_qty = merma
            wiz.waste_pct = (merma / wiz.used_qty * 100) if wiz.used_qty else 0.0
            # Avisos de coherencia, en pantalla y antes de confirmar.
            aviso = ''
            if wiz.used_qty and merma < -0.001:
                aviso = _(
                    'La merma sale negativa (%(m).2f kg): lo tejido más lo '
                    'devuelto supera el peso de las bolsas marcadas como '
                    'usadas. Revisa qué bolsas se abrieron o el peso bajado.',
                    m=merma)
            elif wiz.woven_qty and not wiz.used_qty:
                aviso = _('Se tejieron %(w).2f kg pero no hay ninguna bolsa '
                          'marcada como usada.', w=wiz.woven_qty)
            elif wiz.used_qty and wiz.waste_pct > 10:
                aviso = _('La merma es %(p).1f %% del hilo usado: verifica el '
                          'peso bajado de máquina antes de confirmar.',
                          p=wiz.waste_pct)
            wiz.balance_warning = aviso

    # ------------------------------------------------------------------
    # Carga
    # ------------------------------------------------------------------
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        wo = self.env['mrp.workorder'].browse(
            self.env.context.get('default_workorder_id')
            or self.env.context.get('active_id'))
        if not wo.exists():
            return res
        if wo.operation_type != 'weaving':
            raise UserError(_('Esta liquidación es solo para la operación de tejido.'))
        rolls = wo.roll_ids.filtered(lambda r: r.transfer_state != 'recibido')
        # Si la OT se reabrió por reproceso, lo ya liquidado no vuelve a contar.
        tejido = sum(rolls.mapped('gross_weight')) - wo.weaving_liquidated_qty
        res.update({
            'workorder_id': wo.id,
            'woven_qty': max(0.0, tejido),
            'roll_count': len(rolls),
            'second_location_id': wo.company_id._get_thread_second_location().id,
            'bag_line_ids': [(0, 0, {
                'bag_id': bag.id,
                'used': True,
            }) for bag in wo._weaving_reserved_bags()],
        })
        return res

    # ------------------------------------------------------------------
    # Atajos de la lista de bolsas
    # ------------------------------------------------------------------
    def action_mark_all_used(self):
        self.ensure_one()
        self.bag_line_ids.used = True
        return self._reopen()

    def action_mark_none_used(self):
        self.ensure_one()
        self.bag_line_ids.used = False
        return self._reopen()

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }

    # ------------------------------------------------------------------
    # Confirmación
    # ------------------------------------------------------------------
    def action_confirm(self):
        self.ensure_one()
        if self.workorder_id.state in ('done', 'cancel'):
            raise UserError(_('La orden de trabajo ya está cerrada.'))
        if self.waste_qty < -0.001:
            raise UserError(_(
                'No se puede cerrar con merma negativa (%.2f kg): lo tejido '
                'más lo devuelto a 2da supera el hilo de las bolsas usadas.',
                self.waste_qty))
        if self.return_line_ids.filtered(lambda l: l.weight <= 0):
            raise UserError(_('Hay bolsas devueltas a 2da sin peso.'))
        if self.return_line_ids.filtered(lambda l: l.cone_qty <= 0):
            raise UserError(_('Indica los conos de cada bolsa devuelta a 2da.'))
        if self.returned_qty and not self.second_location_id:
            raise UserError(_('Falta el almacén de 2da calidad para el hilo bajado.'))
        if self.woven_qty and not self.used_qty:
            raise UserError(_(
                'Se tejieron %.2f kg: marca las bolsas que se abrieron en la '
                'tejedora antes de cerrar.', self.woven_qty))

        wo = self.workorder_id
        usadas = self.bag_line_ids.filtered('used').mapped('bag_id')
        libres = (self.bag_line_ids - self.bag_line_ids.filtered('used')).mapped('bag_id')

        # 0) Foto de lo declarado: el asistente es transitorio, el registro no.
        liquidacion = self._create_liquidation_record()
        # 1) Consumo de las bolsas abiertas (completas).
        movimientos = wo._weaving_thread_moves().filtered(
            lambda m: usadas & m.thread_bag_ids)
        consumido = wo._weaving_consume_bags(usadas)
        # 2) Hilo bajado de máquina -> bolsas de 2da en su almacén.
        bolsas_2da = self._create_second_quality_bags(liquidacion)
        # 3) Merma: desecho desde Producción (el hilo ya salió del almacén).
        desechos = self._register_waste()
        # 4) Bolsas que no se abrieron: solo se suelta la reserva.
        wo._weaving_release_bags(libres)
        liquidacion.write({
            'scrap_ids': [(6, 0, desechos.ids)],
            'move_ids': [(6, 0, movimientos.ids)],
            'second_bag_ids': [(6, 0, bolsas_2da.ids)],
        })

        # Markup para que el chatter renderice el HTML; los valores se
        # interpolan vía Markup.__mod__, que los escapa.
        wo.production_id.message_post(body=Markup(_(
            'Liquidación de hilo <b>%(liq)s</b> al cerrar el tejido de %(wo)s:'
            '<ul>'
            '<li>Bolsas usadas: %(nb)s (%(used).2f kg) — %(bags)s</li>'
            '<li>Tela tejida: %(woven).2f kg — rollos: %(rolls)s</li>'
            '<li>Devuelto a 2da: %(ret).2f kg — bolsas: %(rb)s, conos: %(cones)s</li>'
            '<li>Merma: %(waste).2f kg (%(pct).2f %%) %(scrap)s</li>'
            '<li>Reserva liberada: %(freed).2f kg — bolsas: %(fb)s</li>'
            '</ul>')) % {
                'liq': liquidacion.name,
                'wo': wo.display_name, 'nb': len(usadas), 'used': consumido,
                'bags': ', '.join(usadas.mapped('name')) or '—',
                'woven': self.woven_qty, 'rolls': self.roll_count,
                'ret': self.returned_qty, 'rb': len(bolsas_2da),
                'cones': self.returned_cones,
                'waste': self.waste_qty, 'pct': self.waste_pct,
                'scrap': ('— %s' % ', '.join(desechos.mapped('name'))) if desechos else '',
                'freed': self.released_qty, 'fb': len(libres),
            })

        # 5) Cerrar la OT sin volver a consumir ni volver a pedir liquidación.
        wo.sudo().weaving_liquidated_qty += self.woven_qty
        wo_cerrar = wo.with_context(
            skip_weaving_thread_consume=True, skip_weaving_liquidation=True,
            # Evita que el cierre intente navegar a la vista tablet: la
            # liquidación se abrió en un diálogo y solo debe cerrarse.
            mrp_display=True)
        # El cierre del Taller pasa por do_finish (cronómetro, empleados y
        # siguiente operación); si no existe, se cierra la OT directamente.
        cierre = getattr(wo_cerrar, 'do_finish', None) or wo_cerrar.button_finish
        resultado = cierre()
        if isinstance(resultado, dict) and resultado.get('type'):
            return resultado
        return {'type': 'ir.actions.act_window_close'}

    def _create_liquidation_record(self):
        """Guarda lo declarado en un registro permanente (trazabilidad)."""
        self.ensure_one()
        return self.env['thread.weaving.liquidation'].create({
            'workorder_id': self.workorder_id.id,
            'production_id': self.production_id.id,
            'company_id': self.company_id.id,
            'woven_qty': self.woven_qty,
            'roll_count': self.roll_count,
            'reserved_qty': self.reserved_qty,
            'used_qty': self.used_qty,
            'used_bags': self.used_bags,
            'released_qty': self.released_qty,
            'released_bags': self.released_bags,
            'returned_qty': self.returned_qty,
            'returned_bags': self.returned_bags,
            'returned_cones': self.returned_cones,
            'waste_qty': self.waste_qty,
            'waste_pct': self.waste_pct,
            'second_location_id': self.second_location_id.id,
            'bag_line_ids': [(0, 0, {
                'bag_id': l.bag_id.id,
                'bag_name': l.bag_id.name,
                'lot_id': l.lot_id.id,
                'product_id': l.product_id.id,
                'cone_qty': l.cone_qty,
                'net_weight': l.net_weight,
                'used': l.used,
            }) for l in self.bag_line_ids],
            'return_line_ids': [(0, 0, {
                'lot_id': l.lot_id.id,
                'cone_qty': l.cone_qty,
                'weight': l.weight,
                'avg_cone_weight': l.avg_cone_weight,
            }) for l in self.return_line_ids],
        })

    def _production_location(self):
        """Ubicación virtual de Producción de la OF (a donde entró el hilo)."""
        self.ensure_one()
        ubicacion = self.production_id.production_location_id
        if not ubicacion:
            ubicacion = self.env['stock.location'].search([
                ('usage', '=', 'production'),
                ('company_id', 'in', (self.company_id.id, False)),
            ], limit=1)
        if not ubicacion:
            raise UserError(_('No hay ubicación virtual de Producción configurada.'))
        return ubicacion

    def _scrap_location(self):
        """Ubicación de desecho de la compañía.

        Odoo elige por defecto la primera ubicación de tipo inventario (que
        suele ser el ajuste de inventario); la merma de tejido debe ir al
        Desecho, así que se busca esa primero.
        """
        self.ensure_one()
        Location = self.env['stock.location']
        base = [('usage', '=', 'inventory'), ('company_id', '=', self.company_id.id)]
        return Location.search(
            base + [('name', 'in', ('Scrap', 'Desecho', 'Desechos', 'Merma'))],
            limit=1) or Location.search(base, limit=1)

    def _create_second_quality_bags(self, liquidacion=None):
        """Crea las bolsas de 2da con el hilo bajado de máquina y las ingresa
        al almacén de 2da (movimiento desde Producción: ese hilo ya se
        consumió del almacén de primera)."""
        self.ensure_one()
        if not self.return_line_ids:
            return self.env['thread.bag']
        Bag = self.env['thread.bag']
        Move = self.env['stock.move']
        wo = self.workorder_id
        origen = self._production_location()
        bolsas = Bag
        # Las líneas del registro van en el mismo orden que las del asistente.
        registro = list(liquidacion.return_line_ids) if liquidacion else []
        for indice, linea in enumerate(self.return_line_ids):
            move = Move.create({
                'product_id': linea.lot_id.product_id.id,
                'product_uom': linea.lot_id.product_id.uom_id.id,
                'product_uom_qty': linea.weight,
                'location_id': origen.id,
                'location_dest_id': self.second_location_id.id,
                'company_id': wo.company_id.id,
                'origin': _('Hilo 2da de %s', wo.production_id.name),
                'description_picking': _('Hilo bajado de máquina — %s',
                                         wo.display_name),
                'picked': True,
                'move_line_ids': [(0, 0, {
                    'product_id': linea.lot_id.product_id.id,
                    'product_uom_id': linea.lot_id.product_id.uom_id.id,
                    'lot_id': linea.lot_id.id,
                    'quantity': linea.weight,
                    'location_id': origen.id,
                    'location_dest_id': self.second_location_id.id,
                    'company_id': wo.company_id.id,
                })],
            })
            move._action_confirm()
            move._action_done()
            # La bolsa de 2da se distingue por su ubicación (almacén de 2da);
            # el correlativo lleva sufijo -2 para no confundirla con la de 1ra.
            bolsa = Bag.create({
                'name': self._next_second_bag_name(linea.lot_id),
                'product_id': linea.lot_id.product_id.id,
                'lot_id': linea.lot_id.id,
                'location_id': self.second_location_id.id,
                'net_weight': linea.weight,
                'gross_weight': linea.weight,
                'cone_qty': linea.cone_qty,
                'company_id': wo.company_id.id,
                'state': 'available',
            })
            bolsas |= bolsa
            if indice < len(registro):
                registro[indice].bag_id = bolsa.id
        return bolsas

    def _next_second_bag_name(self, lot):
        """Correlativo de bolsa de 2da: <LOTE>-2DA-nn."""
        self.ensure_one()
        prefijo = '%s-2DA-' % (lot.name or 'HILO')
        existentes = self.env['thread.bag'].search(
            [('name', '=like', prefijo + '%')], order='name desc', limit=1)
        siguiente = 1
        if existentes:
            try:
                siguiente = int((existentes.name or '').rsplit('-', 1)[-1]) + 1
            except ValueError:
                siguiente = 1
        return '%s%02d' % (prefijo, siguiente)

    def _register_waste(self):
        """Registra la merma como DESECHO desde Producción.

        El hilo consumido entró a la ubicación virtual de Producción; de ahí
        una parte se volvió tela, otra volvió como 2da y el resto es merma. Por
        eso el desecho sale de Producción y no del almacén: si saliera del
        almacén se descontaría dos veces el mismo hilo.

        Se usa el desecho estándar (Inventario → Desechos) para que la merma
        quede con su referencia, su lote y su enlace a la OF/OT.
        """
        self.ensure_one()
        if float_is_zero(self.waste_qty, precision_digits=3):
            return self.env['stock.scrap']
        wo = self.workorder_id
        origen = self._production_location()
        # Reparto de la merma entre los lotes usados, a prorrata de lo usado.
        usadas = self.bag_line_ids.filtered('used').mapped('bag_id')
        por_lote = {}
        for bag in usadas:
            por_lote[bag.lot_id] = por_lote.get(bag.lot_id, 0.0) + bag.net_weight
        total = sum(por_lote.values()) or 1.0
        Scrap = self.env['stock.scrap']
        desechos = Scrap
        destino = self._scrap_location()
        for lote, kg in por_lote.items():
            merma = self.waste_qty * (kg / total)
            if float_is_zero(merma, precision_digits=3):
                continue
            desecho = Scrap.create({
                'product_id': lote.product_id.id,
                'product_uom_id': lote.product_id.uom_id.id,
                'lot_id': lote.id,
                'scrap_qty': merma,
                'location_id': origen.id,
                'production_id': wo.production_id.id,
                'workorder_id': wo.id,
                'company_id': wo.company_id.id,
                'origin': _('Merma de tejido %s', wo.display_name),
                'should_replenish': False,
                **({'scrap_location_id': destino.id} if destino else {}),
            })
            # El cómputo de la ubicación de origen la lleva al almacén de la
            # OF; aquí la merma sale de Producción para no descontar dos veces.
            if desecho.location_id != origen:
                desecho.location_id = origen
            desecho.do_scrap()
            desechos |= desecho
        return desechos


class ThreadWeavingCloseWizardBag(models.TransientModel):
    _name = 'thread.weaving.close.wizard.bag'
    _description = 'Bolsa separada para el tejido'

    wizard_id = fields.Many2one(
        'thread.weaving.close.wizard', ondelete='cascade', required=True)
    bag_id = fields.Many2one('thread.bag', string='Bolsa', required=True)
    bag_name = fields.Char(related='bag_id.name', string='Correlativo')
    lot_id = fields.Many2one(related='bag_id.lot_id', string='Lote')
    product_id = fields.Many2one(related='bag_id.product_id', string='Hilo')
    net_weight = fields.Float(related='bag_id.net_weight', string='Peso Neto (kg)')
    cone_qty = fields.Integer(related='bag_id.cone_qty', string='Conos')
    location_id = fields.Many2one(related='bag_id.location_id', string='Ubicación')
    used = fields.Boolean(
        'Usada', default=True,
        help='Marcada: la bolsa se abrió y su hilo se consume. '
             'Sin marcar: no se usó y solo se libera la reserva.')


class ThreadWeavingCloseWizardReturn(models.TransientModel):
    _name = 'thread.weaving.close.wizard.return'
    _description = 'Hilo bajado de máquina (2da calidad)'

    wizard_id = fields.Many2one(
        'thread.weaving.close.wizard', ondelete='cascade', required=True)
    lot_id = fields.Many2one(
        'stock.lot', string='Lote', required=True,
        domain="[('id', 'in', parent.available_lot_ids)]")
    weight = fields.Float('Peso (kg)', digits=(16, 3), required=True)
    cone_qty = fields.Integer('Conos', required=True)
    avg_cone_weight = fields.Float(
        'Peso x Cono (kg)', compute='_compute_avg_cone_weight', digits=(16, 4))

    @api.depends('weight', 'cone_qty')
    def _compute_avg_cone_weight(self):
        for linea in self:
            linea.avg_cone_weight = (linea.weight / linea.cone_qty) if linea.cone_qty else 0.0
