# -*- coding: utf-8 -*-
"""Al cerrar el TEJIDO: rearmar las bolsas con el hilo que volvió de la máquina.

Las bolsas separadas se abrieron para cargar los alimentadores, así que como
bolsas ya no existen: se consumen completas. Con los conos que se bajaron de la
máquina se arman bolsas NUEVAS, y aquí el tejedor dice cuántos conos y cuánto
pesa cada una. La diferencia entre lo consumido y lo rearmado es lo que se
volvió tela (más la pérdida), y se corrige después por inventario.
"""

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ThreadWeavingCloseBagsWizard(models.TransientModel):
    _name = 'thread.weaving.close.bags.wizard'
    _description = 'Rearmar bolsas al cerrar el tejido'

    workorder_id = fields.Many2one(
        'mrp.workorder', string='Orden de Trabajo', required=True)
    production_id = fields.Many2one(
        related='workorder_id.production_id', string='Orden de Fabricación')
    company_id = fields.Many2one(related='workorder_id.company_id')

    old_bag_ids = fields.Many2many(
        'thread.bag', string='Bolsas Separadas',
        help='Bolsas que se abrieron para cargar la máquina: se consumen completas.')
    old_qty = fields.Float('Separado (kg)', compute='_compute_totals', digits=(16, 2))
    old_bags = fields.Integer('Bolsas Separadas', compute='_compute_totals')
    old_cones = fields.Integer('Conos Separados', compute='_compute_totals')

    location_id = fields.Many2one(
        'stock.location', string='Ubicación de las Bolsas Nuevas',
        domain="[('usage', '=', 'internal')]", required=True,
        help='Dónde entran las bolsas rearmadas. Por defecto, de donde salió el hilo.')
    line_ids = fields.One2many(
        'thread.weaving.close.bags.wizard.line', 'wizard_id',
        string='Bolsas Nuevas')

    new_qty = fields.Float('Rearmado (kg)', compute='_compute_totals', digits=(16, 2))
    new_bags = fields.Integer('Bolsas Nuevas', compute='_compute_totals')
    new_cones = fields.Integer('Conos Rearmados', compute='_compute_totals')
    consumed_qty = fields.Float(
        'Queda Consumido (kg)', compute='_compute_totals', digits=(16, 2),
        help='Separado menos rearmado: el hilo que se volvió tela más la merma.')
    woven_qty = fields.Float('Tela Tejida (kg)', readonly=True)
    waste_qty = fields.Float(
        'Merma a Desecho (kg)', compute='_compute_totals', digits=(16, 2),
        help='Consumido menos la tela tejida: se registra como desecho y queda '
             'visible en la orden de fabricación.')
    balance_warning = fields.Char(compute='_compute_totals')
    available_lot_ids = fields.Many2many(
        'stock.lot', string='Lotes de la Orden', compute='_compute_available_lots',
        help='Lotes de las bolsas que se abrieron: el hilo rearmado solo puede '
             'ser de uno de ellos.')

    @api.depends('old_bag_ids')
    def _compute_available_lots(self):
        for wiz in self:
            wiz.available_lot_ids = wiz.old_bag_ids.mapped('lot_id')

    @api.depends('old_bag_ids', 'line_ids.net_weight', 'line_ids.cone_qty', 'woven_qty')
    def _compute_totals(self):
        for wiz in self:
            wiz.old_qty = sum(wiz.old_bag_ids.mapped('net_weight'))
            wiz.old_bags = len(wiz.old_bag_ids)
            wiz.old_cones = sum(wiz.old_bag_ids.mapped('cone_qty'))
            wiz.new_qty = sum(wiz.line_ids.mapped('net_weight'))
            wiz.new_bags = len(wiz.line_ids)
            wiz.new_cones = sum(wiz.line_ids.mapped('cone_qty'))
            wiz.consumed_qty = wiz.old_qty - wiz.new_qty
            wiz.waste_qty = wiz.consumed_qty - wiz.woven_qty
            aviso = ''
            if wiz.new_qty > wiz.old_qty + 0.001:
                aviso = _(
                    'Las bolsas nuevas pesan %(nuevo).2f kg y solo se separaron '
                    '%(viejo).2f kg: revisa los pesos.',
                    nuevo=wiz.new_qty, viejo=wiz.old_qty)
            elif wiz.new_cones > wiz.old_cones:
                aviso = _(
                    'Se rearman %(nuevo)s conos pero se separaron %(viejo)s: '
                    'no pueden salir más conos de los que entraron.',
                    nuevo=wiz.new_cones, viejo=wiz.old_cones)
            elif wiz.woven_qty and wiz.waste_qty < -0.001:
                aviso = _(
                    'La merma sale negativa (%(m).2f kg): lo rearmado más la tela '
                    'tejida (%(tela).2f kg) supera el hilo de las bolsas abiertas. '
                    'Revisa los pesos.', m=wiz.waste_qty, tela=wiz.woven_qty)
            wiz.balance_warning = aviso

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        wo = self.env['mrp.workorder'].browse(
            self.env.context.get('default_workorder_id')
            or self.env.context.get('active_id'))
        if not wo.exists():
            return res
        bolsas = wo._weaving_reserved_bags()
        # La tela es la que el ERP cuenta como producción de esta OT: excluye los
        # rollos TRANSFERIDOS a otra orden (los sumaba y la merma salía negativa)
        # e incluye los recibidos, igual que el avance y el Taller.
        res.update({
            'workorder_id': wo.id,
            'old_bag_ids': [(6, 0, bolsas.ids)],
            'woven_qty': wo._get_textile_produced_qty(),
            # Por defecto vuelven a donde salió el hilo.
            'location_id': (bolsas[:1].location_id
                            or wo._weaving_thread_moves()[:1].location_id).id or False,
        })
        return res

    # ------------------------------------------------------------------
    def action_add_line(self):
        """Agrega una bolsa nueva con el lote de las separadas."""
        self.ensure_one()
        lote = self.old_bag_ids[:1].lot_id
        self.env['thread.weaving.close.bags.wizard.line'].create({
            'wizard_id': self.id,
            'lot_id': lote.id,
            'name': self._next_bag_name(lote),
        })
        return self._reopen()

    def _reopen(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }

    def _next_bag_name(self, lot):
        """Correlativo de la bolsa rearmada: <LOTE>-S01, -S02…"""
        self.ensure_one()
        prefijo = '%s-S' % (lot.name or 'HILO')
        usados = set(self.env['thread.bag'].search(
            [('name', '=like', prefijo + '%')]).mapped('name'))
        usados |= set(self.line_ids.mapped('name'))
        numero = 1
        while '%s%02d' % (prefijo, numero) in usados:
            numero += 1
        return '%s%02d' % (prefijo, numero)

    # ------------------------------------------------------------------
    def action_confirm(self):
        self.ensure_one()
        wo = self.workorder_id
        if wo.state in ('done', 'cancel'):
            raise UserError(_('La orden de trabajo ya está cerrada.'))
        if self.new_qty > self.old_qty + 0.001:
            raise UserError(_(
                'Las bolsas nuevas (%(nuevo).2f kg) pesan más que el hilo '
                'separado (%(viejo).2f kg).', nuevo=self.new_qty, viejo=self.old_qty))
        if self.woven_qty and self.waste_qty < -0.001:
            raise UserError(_(
                'No se puede cerrar con merma negativa (%(m).2f kg): lo rearmado '
                '(%(nuevo).2f kg) más la tela tejida (%(tela).2f kg) supera los '
                '%(viejo).2f kg de las bolsas abiertas.',
                m=self.waste_qty, nuevo=self.new_qty, tela=self.woven_qty,
                viejo=self.old_qty))
        if self.line_ids.filtered(lambda l: l.net_weight <= 0):
            raise UserError(_('Hay bolsas nuevas sin peso neto.'))
        if self.line_ids.filtered(lambda l: l.cone_qty <= 0):
            raise UserError(_('Indica los conos de cada bolsa nueva.'))
        if self.line_ids.filtered(lambda l: not l.name):
            raise UserError(_('Falta el correlativo de alguna bolsa nueva.'))
        repetidos = [n for n in self.line_ids.mapped('name')
                     if self.line_ids.filtered(lambda l: l.name == n) and
                     len(self.line_ids.filtered(lambda l: l.name == n)) > 1]
        if repetidos:
            raise UserError(_('Correlativo repetido en las bolsas nuevas: %s',
                              ', '.join(sorted(set(repetidos)))))

        viejas = self.old_bag_ids
        # 1) salen del almacén las bolsas abiertas, por su peso real.
        consumido = wo._weaving_consume_bags(viejas)
        # 2) entra lo que volvió de la máquina, ya rearmado.
        nuevas = self._create_new_bags()
        # 3) la diferencia contra la tela tejida es merma: va al desecho.
        desechos = self._register_waste()
        cuerpo = Markup(_(
            'Cierre del tejido de %(wo)s: se rearmaron las bolsas.'
            '<ul>'
            '<li>Consumidas: %(nb)s bolsas, %(old).2f kg — %(bags)s</li>'
            '<li>Rearmadas: %(nn)s bolsas, %(new).2f kg, %(cones)s conos — %(new_names)s</li>'
            '<li>Queda consumido: %(cons).2f kg (tela tejida %(tela).2f kg)</li>'
            '<li>Merma a desecho: %(merma).2f kg %(scrap)s</li>'
            '</ul>')) % {
                'wo': wo.display_name, 'nb': len(viejas), 'old': consumido or self.old_qty,
                'bags': ', '.join(viejas.mapped('name')) or '—',
                'nn': len(nuevas), 'new': self.new_qty, 'cones': self.new_cones,
                'new_names': ', '.join(nuevas.mapped('name')) or '—',
                'cons': self.consumed_qty, 'tela': self.woven_qty,
                'merma': self.waste_qty,
                'scrap': ('— %s' % ', '.join(desechos.mapped('name'))) if desechos else '',
            }
        wo.production_id.message_post(body=cuerpo)

        # El cierre normal consume el movimiento de hilo: las bolsas separadas
        # pasan a Consumida por el camino de siempre.
        wo_cerrar = wo.with_context(skip_weaving_close_bags=True, mrp_display=True)
        cierre = getattr(wo_cerrar, 'do_finish', None) or wo_cerrar.button_finish
        resultado = cierre()
        if isinstance(resultado, dict) and resultado.get('type'):
            return resultado
        return {'type': 'ir.actions.act_window_close'}

    def _scrap_location(self):
        """Ubicación de desecho de la compañía.

        Odoo 19 toma la primera ubicación de tipo inventario (que suele ser el
        ajuste de inventario); la merma de tejido debe ir al Desecho.
        """
        self.ensure_one()
        Location = self.env['stock.location']
        base = [('usage', '=', 'inventory'), ('company_id', '=', self.company_id.id)]
        return Location.search(
            base + [('name', 'in', ('Scrap', 'Desecho', 'Desechos', 'Merma'))],
            limit=1) or Location.search(base, limit=1)

    def _register_waste(self):
        """Registra la merma como DESECHO desde Producción.

        Sale de Producción y no del almacén: ese hilo ya salió al consumirse la
        bolsa. Se reparte entre los lotes de las bolsas abiertas, a prorrata.
        """
        self.ensure_one()
        if self.waste_qty <= 0.001:
            return self.env['stock.scrap']
        wo = self.workorder_id
        origen = self.production_id.production_location_id
        destino = self._scrap_location()
        por_lote = {}
        for bag in self.old_bag_ids:
            por_lote[bag.lot_id] = por_lote.get(bag.lot_id, 0.0) + bag.net_weight
        total = sum(por_lote.values()) or 1.0
        Scrap = self.env['stock.scrap']
        desechos = Scrap
        for lote, kg in por_lote.items():
            merma = self.waste_qty * (kg / total)
            if merma <= 0.001:
                continue
            desecho = Scrap.create({
                'product_id': lote.product_id.id,
                'product_uom_id': lote.product_id.uom_id.id,
                'lot_id': lote.id,
                'scrap_qty': merma,
                'location_id': origen.id,
                'production_id': self.production_id.id,
                'workorder_id': wo.id,
                'company_id': self.company_id.id,
                'origin': _('Merma de tejido %s', wo.display_name),
                'should_replenish': False,
                **({'scrap_location_id': destino.id} if destino else {}),
            })
            # El cómputo lleva el origen al almacén de la OF; la merma sale de
            # Producción para no descontar dos veces el mismo hilo.
            if desecho.location_id != origen:
                desecho.location_id = origen
            desecho.do_scrap()
            desechos |= desecho
        return desechos

    def _create_new_bags(self):
        """Crea las bolsas rearmadas y las ingresa desde Producción."""
        self.ensure_one()
        if not self.line_ids:
            return self.env['thread.bag']
        Bag = self.env['thread.bag']
        Move = self.env['stock.move']
        wo = self.workorder_id
        origen = self.production_id.production_location_id or self.env[
            'stock.location'].search([
                ('usage', '=', 'production'),
                ('company_id', 'in', (self.company_id.id, False)),
            ], limit=1)
        if not origen:
            raise UserError(_('No hay ubicación virtual de Producción configurada.'))
        nuevas = Bag
        for linea in self.line_ids:
            move = Move.create({
                'product_id': linea.lot_id.product_id.id,
                'product_uom': linea.lot_id.product_id.uom_id.id,
                'product_uom_qty': linea.net_weight,
                'location_id': origen.id,
                'location_dest_id': self.location_id.id,
                'company_id': self.company_id.id,
                'origin': _('Rearmado de bolsas %s', wo.production_id.name),
                'description_picking': _('Hilo bajado de máquina — %s', wo.display_name),
                'picked': True,
                'move_line_ids': [(0, 0, {
                    'product_id': linea.lot_id.product_id.id,
                    'product_uom_id': linea.lot_id.product_id.uom_id.id,
                    'lot_id': linea.lot_id.id,
                    'quantity': linea.net_weight,
                    'location_id': origen.id,
                    'location_dest_id': self.location_id.id,
                    'company_id': self.company_id.id,
                })],
            })
            move._action_confirm()
            move._action_done()
            nuevas |= Bag.create({
                'name': linea.name,
                'product_id': linea.lot_id.product_id.id,
                'lot_id': linea.lot_id.id,
                'location_id': self.location_id.id,
                'cone_qty': linea.cone_qty,
                'net_weight': linea.net_weight,
                'gross_weight': linea.net_weight,
                'company_id': self.company_id.id,
                'state': 'available',
            })
        return nuevas


class ThreadWeavingCloseBagsWizardLine(models.TransientModel):
    _name = 'thread.weaving.close.bags.wizard.line'
    _description = 'Bolsa rearmada al cerrar el tejido'
    _order = 'id'

    wizard_id = fields.Many2one(
        'thread.weaving.close.bags.wizard', ondelete='cascade', required=True)
    name = fields.Char('Correlativo', required=True)
    lot_id = fields.Many2one(
        'stock.lot', string='Lote', required=True,
        default=lambda self: self._default_lot(),
        domain="[('id', 'in', parent.available_lot_ids)]")

    @api.model
    def _default_lot(self):
        """Si la orden abrió bolsas de un solo lote, ese lote va puesto."""
        wiz = self.env['thread.weaving.close.bags.wizard'].browse(
            self.env.context.get('default_wizard_id'))
        lotes = wiz.old_bag_ids.mapped('lot_id') if wiz.exists() else False
        return lotes.id if lotes and len(lotes) == 1 else False
    cone_qty = fields.Integer('Conos', required=True)
    net_weight = fields.Float('Peso Neto (kg)', digits=(16, 3), required=True)
    cone_weight = fields.Float(
        'Peso x Cono (kg)', compute='_compute_cone_weight', digits=(16, 4))

    @api.depends('net_weight', 'cone_qty')
    def _compute_cone_weight(self):
        for linea in self:
            linea.cone_weight = (linea.net_weight / linea.cone_qty) if linea.cone_qty else 0.0
