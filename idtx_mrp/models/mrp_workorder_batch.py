# -*- coding: utf-8 -*-

from odoo import api, Command, fields, models, _
from odoo.exceptions import UserError, ValidationError

class MrpWorkorderBatch(models.Model):
    _name = 'mrp.workorder.batch'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Mrp Workorder Batch'

    # workorder_id = fields.Many2one('mrp.workorder', string='Workorder')
    sequence = fields.Integer('Sequence')
    name = fields.Char('Name', required=True, copy=False, readonly=False, default=lambda self: _('New'))
    batch_date = fields.Date('Batch Date', required=True, default=lambda self: fields.Date.context_today(self))
    wo_roll_ids = fields.Many2many('mrp.workorder.roll', string='Batch Rolls')
    total_weight = fields.Float('Total', compute='_compute_total_weight')
    # Control de peso (JP, 22-sep-2026): peso de la partida tomado en balanza
    # en la operación marcada "Control de peso". Es el peso que usa la RECETA
    # (el crudo pudo bajar en los procesos previos).
    controlled_weight = fields.Float(
        'Peso tras control (kg)', readonly=True, copy=False, tracking=True, digits=(12, 2))
    controlled_weight_date = fields.Datetime('Fecha del control de peso', readonly=True, copy=False)
    controlled_weight_user_id = fields.Many2one(
        'res.users', 'Pesado por', readonly=True, copy=False, ondelete='set null')
    controlled_weight_scale_id = fields.Many2one(
        'scale.registry', 'Balanza del control', readonly=True, copy=False, ondelete='set null')
    recipe_weight = fields.Float(
        'Peso para receta (kg)', compute='_compute_recipe_weight', digits=(12, 2),
        help='Peso tras control si la partida ya pasó por Control de peso; '
             'si no, el peso crudo de los rollos.')
    mrwo_id = fields.Many2one('mrp.routing.workcenter.operation', string='Last Operation')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('batch', 'Batch'),
        ('split', 'Dividida'),
        ('unbuild', 'Unbuild'),
    ], string='State', default='draft')

    # --- Genealogía de división (sublotes ISA-95: la partida padre es el
    # registro del teñido; las hijas heredan sus propiedades y siguen rutas
    # separadas, identificadas como <padre>-A, <padre>-B, ...) ---
    parent_batch_id = fields.Many2one(
        'mrp.workorder.batch', string='Partida Origen', readonly=True,
        index=True, ondelete='restrict', copy=False,
        help='Partida de teñido de la que se dividió esta sub-partida.')
    split_code = fields.Char('Sub-partida', readonly=True, copy=False,
                             help='Código del grupo dentro de la partida original (A, B, ...).')
    child_batch_ids = fields.One2many(
        'mrp.workorder.batch', 'parent_batch_id', string='Sub-partidas')
    child_count = fields.Integer(compute='_compute_child_count')
    # --- Lote de teñido: partidas por PRODUCTO que se tiñen JUNTAS ---
    # Una partida armada con rollos de varios productos se separa al
    # confirmarla en una partida por producto con el MISMO número: cada una
    # sigue su ruta y registra sus operaciones; las operaciones "conjuntas"
    # (mismo baño) se registran en todas a la vez. La partida original queda
    # como LOTE DE TEÑIDO (madre, estado Dividida): receta, sub-receta y
    # kilos totales del baño (JP, 18-sep-2026).
    is_dye_lot = fields.Boolean('Lote de teñido', readonly=True, copy=False)
    # --- Reproceso PARCIAL: partida de reproceso con el MISMO número ---
    # Al aprobar una alerta de reproceso sobre PARTE de los rollos, esos rollos
    # salen de la original a una partida nueva "<número> · Reproceso N" que
    # hereda la historia de operaciones (parent_batch_id) y se lleva el
    # reproceso y la alerta. La original sigue viva con el resto.
    reprocess_seq = fields.Integer('N° de reproceso', readonly=True, copy=False)
    transferred_roll_ids = fields.One2many(
        'mrp.workorder.roll', 'reprocess_from_batch_id',
        string='Rollos transferidos a reproceso')
    dye_product_id = fields.Many2one(
        'product.template', string='Producto del lote', readonly=True, copy=False,
        help='Partida por producto de un lote de teñido: el producto que agrupa.')
    dye_sibling_ids = fields.Many2many(
        'mrp.workorder.batch', compute='_compute_dye_siblings',
        string='Se tiñe junto con')
    dye_lot_weight = fields.Float(
        'Kilos del lote', compute='_compute_dye_siblings',
        help='Kilos totales del baño: esta partida más las que se tiñen con ella.')
    origin_roll_ids = fields.Many2many(
        'mrp.workorder.roll', string='Rollos Originales',
        compute='_compute_origin_roll_ids',
        help='Composición original de la partida dividida: los rollos que hoy '
             'viven en sus sub-partidas (recursivo si estas se volvieron a dividir).')

    def _compute_origin_roll_ids(self):
        for rec in self:
            rolls = rec.wo_roll_ids
            seen = self.browse()
            # Las partidas de REPROCESO parcial no cuentan: sus rollos salieron
            # de la original (viva), que ya no los tiene.
            children = rec.child_batch_ids.filtered(lambda c: not c.reprocess_seq)
            while children:
                rolls |= children.wo_roll_ids
                seen |= children
                children = children.child_batch_ids.filtered(lambda c: not c.reprocess_seq) - seen
            rec.origin_roll_ids = rolls

    def _compute_child_count(self):
        for rec in self:
            rec.child_count = len(rec.child_batch_ids)

    @api.depends('dye_product_id', 'parent_batch_id.is_dye_lot',
                 'parent_batch_id.child_batch_ids.wo_roll_ids.gross_weight',
                 'parent_batch_id.child_batch_ids.controlled_weight',
                 'wo_roll_ids.gross_weight', 'controlled_weight')
    def _compute_dye_siblings(self):
        for rec in self:
            siblings = self.browse()
            if rec.dye_product_id and rec.parent_batch_id.is_dye_lot:
                siblings = rec.parent_batch_id.child_batch_ids - rec
            rec.dye_sibling_ids = siblings
            # Kilos del baño con el peso que usa la receta (tras control si lo hay).
            rec.dye_lot_weight = rec.recipe_weight + sum(siblings.mapped('recipe_weight'))

    @api.depends('controlled_weight', 'wo_roll_ids.gross_weight',
                 'child_batch_ids.wo_roll_ids.gross_weight')
    def _compute_recipe_weight(self):
        for rec in self:
            rec.recipe_weight = rec.controlled_weight if rec.controlled_weight > 0 else rec.total_weight

    def _dye_lot_batches(self):
        """Partidas que van en el MISMO baño (pareja de _dye_lot_rolls): la
        propia y sus hermanas del lote; para el lote (madre), sus hijas."""
        self.ensure_one()
        if self.dye_product_id and self.parent_batch_id.is_dye_lot:
            return self | self.dye_sibling_ids
        if self.is_dye_lot and self.child_batch_ids:
            return self.child_batch_ids
        return self

    def action_set_controlled_weight(self, weight, scale=None):
        """Control de peso: guarda el peso de balanza de la partida (el que usa
        la receta) y lo deja en el chatter junto al crudo."""
        self.ensure_one()
        weight = round(float(weight or 0), 2)
        if weight <= 0:
            raise UserError(_('El peso del control debe ser mayor a cero.'))
        previous = self.controlled_weight
        self.write({
            'controlled_weight': weight,
            'controlled_weight_date': fields.Datetime.now(),
            'controlled_weight_user_id': self.env.uid,
            'controlled_weight_scale_id': scale.id if scale else False,
        })
        self.message_post(body=_(
            'Control de peso: %(kg).2f kg (peso crudo %(raw).2f kg, diferencia %(diff)+.2f kg)%(prev)s. '
            'La receta se calcula con este peso.',
            kg=weight, raw=self.total_weight, diff=weight - self.total_weight,
            prev=_(' — reemplaza el control anterior de %(p).2f kg', p=previous) if previous else ''))

    @api.depends('name', 'dye_product_id', 'is_dye_lot', 'reprocess_seq')
    def _compute_display_name(self):
        # Las partidas por producto comparten el número: se distinguen por el
        # producto (WB00067 · CUELLO..., WB00067 · JERSEY...). La partida de
        # reproceso parcial también: "WB00067 · Reproceso 1".
        for rec in self:
            name = rec.name or ''
            if rec.dye_product_id:
                name = '%s · %s' % (name, rec.dye_product_id.name)
            elif rec.is_dye_lot:
                name = _('%s (lote de teñido)') % name
            if rec.reprocess_seq:
                name = _('%s · Reproceso %s') % (name, rec.reprocess_seq)
            rec.display_name = name

    def _split_for_reprocess(self, rolls, alert=None):
        """Reproceso PARCIAL: saca `rolls` de esta partida a una partida nueva
        con el MISMO número ("· Reproceso N") que hereda la historia de
        operaciones (parent_batch_id) y la receta. La original sigue viva con
        el resto y muestra los rollos como transferidos. Devuelve la nueva."""
        self.ensure_one()
        if self.state != 'batch':
            raise UserError(_('Solo se puede separar rollos de una partida confirmada (%s).') % self.display_name)
        rolls = rolls & self.wo_roll_ids
        if not rolls:
            raise UserError(_('Selecciona al menos un rollo de la partida %s para reprocesar.') % self.display_name)
        if rolls == self.wo_roll_ids:
            raise UserError(_('Se seleccionaron TODOS los rollos: el reproceso aplica a la partida completa, sin separar.'))
        seq = max(self.child_batch_ids.mapped('reprocess_seq') or [0]) + 1
        child = self.create([{
            'name': self.name,
            'parent_batch_id': self.id,
            'reprocess_seq': seq,
            'dye_product_id': self.dye_product_id.id,
            'batch_date': self.batch_date,
            'mrwo_id': self.mrwo_id.id,
            'state': 'batch',
            'wo_roll_ids': [Command.set(rolls.ids)],
        }])
        self.write({'wo_roll_ids': [Command.unlink(r.id) for r in rolls]})
        rolls.write({'reprocess_from_batch_id': self.id, 'reprocess_batch_id': child.id})
        detail = ', '.join(rolls.mapped('name'))
        why = _(' por la alerta de calidad %s') % alert.name if alert else ''
        self.message_post(body=_(
            'Reproceso parcial%(why)s: %(n)s rollo(s) (%(kg).2f kg) transferidos a %(child)s: %(detail)s.',
            why=why, n=len(rolls), kg=sum(rolls.mapped('gross_weight')),
            child=child.display_name, detail=detail))
        child.message_post(body=_(
            'Partida de reproceso creada%(why)s con %(n)s rollo(s) (%(kg).2f kg) de %(parent)s: %(detail)s.',
            why=why, n=len(rolls), kg=sum(rolls.mapped('gross_weight')),
            parent=self.display_name, detail=detail))
        (self | child)._sync_linked_workorders()
        return child

    def _dye_lot_rolls(self):
        """Rollos que van en el MISMO baño: los propios más los de las partidas
        hermanas del lote (partida por producto). Para el lote (madre) y las
        partidas normales, los propios o la composición original."""
        self.ensure_one()
        if self.dye_product_id and self.parent_batch_id.is_dye_lot:
            return self.wo_roll_ids | self.dye_sibling_ids.wo_roll_ids
        return self.wo_roll_ids or self.origin_roll_ids

    def _route_signatures(self):
        """Rutas distintas entre las OF de los rollos: una firma por OF =
        secuencia de operaciones (mrwo) de sus OT no canceladas."""
        self.ensure_one()
        return {
            tuple((w.mrwo_id.id or w.name) for w in prod.workorder_ids.filtered(
                lambda w: w.state != 'cancel').sorted(lambda w: (w.sequence, w.id)))
            for prod in self.wo_roll_ids.production_id
        }

    def _split_by_product(self):
        """Separa una partida con rollos de VARIOS productos en una partida por
        producto con el MISMO número. La original pasa a ser el lote de teñido
        (sin rollos propios, estado Dividida). Devuelve las hijas."""
        self.ensure_one()
        products = self.wo_roll_ids.mapped('product_id')
        if len(products) < 2 or self.is_dye_lot or self.dye_product_id:
            return self.browse()
        # Solo si las RUTAS de sus OF son distintas (basta una operación
        # diferente). Con la misma ruta los productos se procesan como una
        # sola partida, sin separar (JP, 18-sep-2026).
        if len(self._route_signatures()) < 2:
            return self.browse()
        children = self.browse()
        for product in products.sorted(lambda p: p.default_code or p.name or ''):
            rolls = self.wo_roll_ids.filtered(lambda r: r.product_id == product)
            children |= self.with_context(bypass_split_readonly=True).create([{
                'name': self.name,
                'parent_batch_id': self.id,
                'dye_product_id': product.id,
                'batch_date': self.batch_date,
                'mrwo_id': self.mrwo_id.id,
                'state': 'batch',
                'wo_roll_ids': [Command.set(rolls.ids)],
            }])
        self.with_context(bypass_split_readonly=True).write({
            'wo_roll_ids': [Command.clear()], 'state': 'split', 'is_dye_lot': True})
        self.message_post(body=_(
            'Lote de teñido: se separó en una partida por producto (mismo número): %s. '
            'Kilos totales del baño: %.2f.') % (
                ', '.join(children.mapped('display_name')), sum(children.mapped('total_weight'))))
        for child in children:
            child.message_post(body=_(
                'Partida por producto del lote de teñido %s. Se tiñe junto con: %s.') % (
                    self.name, ', '.join((children - child).mapped('display_name')) or '-'))
        return children

    def action_view_dye_siblings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Se tiñe junto con'),
            'res_model': 'mrp.workorder.batch', 'view_mode': 'list,form',
            'domain': [('id', 'in', self.dye_sibling_ids.ids)],
        }

    def _compute_total_weight(self):
        for rec in self:
            if rec.wo_roll_ids:
                rec.total_weight = sum(rec.wo_roll_ids.mapped('gross_weight'))
            elif rec.child_batch_ids:
                # Partida dividida: el total histórico es la suma de sus hijas.
                rec.total_weight = sum(
                    rec.child_batch_ids.wo_roll_ids.mapped('gross_weight'))
            else:
                rec.total_weight = 0

    @api.constrains('wo_roll_ids')
    def _check_same_color_recipe(self):
        """Una partida solo puede agrupar rollos de órdenes de fabricación del
        MISMO COLOR (misma línea de Lab Dip): se tiñe todo junto. La receta
        concreta la resuelve la partida por combinación de productos, así que
        aquí ya no se exige la misma receta sino el mismo color."""
        for batch in self:
            productions = batch.wo_roll_ids.production_id
            by_color = {}
            for prod in productions:
                line = (prod.sale_order_line_id.lab_dev_line_id
                        or prod.color_recipe_id.lab_dev_line_id)
                by_color.setdefault(line, self.env['mrp.production'])
                by_color[line] |= prod
            if len(by_color) > 1:
                detail = '\n'.join(
                    '- %s: %s' % (
                        line.display_name if line else _('(sin color de laboratorio)'),
                        ', '.join(prods.mapped('name')),
                    )
                    for line, prods in by_color.items()
                )
                raise ValidationError(_(
                    'La partida %(batch)s no puede mezclar órdenes de fabricación '
                    'de colores distintos:\n%(detail)s',
                    batch=batch.name, detail=detail,
                ))

    @api.constrains('wo_roll_ids')
    def _check_customer_rolls_same_production(self):
        """Rollos del CLIENTE (OF de servicio sin tejido): no se conocen sus
        lotes de hilo, así que no se mezclan con tejido propio ni con otra OF
        (otra entrega del mismo cliente puede ser otro hilo). Una partida de
        tela del cliente es de UNA sola OF (JP, 18-sep-2026)."""
        for batch in self:
            customer = batch.wo_roll_ids.filtered(lambda r: r.origin == 'customer')
            if not customer:
                continue
            own = batch.wo_roll_ids - customer
            if own:
                raise ValidationError(_(
                    'La partida %(batch)s mezcla rollos del cliente (%(cust)s) con '
                    'rollos de tejido propio (%(own)s). Los rollos del cliente van '
                    'en partidas aparte: no se conocen sus lotes de hilo.',
                    batch=batch.name, cust=', '.join(customer.mapped('name')),
                    own=', '.join(own.mapped('name'))))
            prods = customer.production_id
            if len(prods) > 1:
                raise ValidationError(_(
                    'La partida %(batch)s mezcla rollos del cliente de distintas OF '
                    '(%(prods)s). Sin lotes de hilo conocidos, cada partida de tela '
                    'del cliente debe ser de una sola OF.',
                    batch=batch.name, prods=', '.join(prods.mapped('name'))))

    @api.constrains('wo_roll_ids')
    def _check_same_option_per_production(self):
        """Dentro de una partida, los rollos de una misma OF deben compartir
        la OPCIÓN de tejido: la opción define la combinación de lotes de hilo
        (y por ella la sub-receta), así que con opciones mezcladas la receta
        de la partida sería ambigua."""
        for batch in self:
            by_prod = {}
            for roll in batch.wo_roll_ids:
                prod = roll.production_id
                by_prod.setdefault(prod, {}).setdefault(
                    roll.option_id, []).append(roll.name or str(roll.id))
            offending = {prod: opts for prod, opts in by_prod.items()
                         if len(opts) > 1}
            if offending:
                detail = '\n'.join(
                    '- %s: %s' % (
                        prod.display_name,
                        '; '.join('%s (%s)' % (
                            opt.name or opt.display_name if opt else _('(sin opción)'),
                            ', '.join(names))
                            for opt, names in opts.items()),
                    )
                    for prod, opts in offending.items()
                )
                raise ValidationError(_(
                    'La partida %(batch)s no puede mezclar rollos de la misma '
                    'orden de fabricación con opciones distintas:\n%(detail)s',
                    batch=batch.name, detail=detail,
                ))

    #=== CRUD METHODS ===#

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _("New")) == _("New"):
                seq_date = fields.Datetime.context_timestamp(
                    self, fields.Datetime.to_datetime(vals['batch_date'])
                ) if 'batch_date' in vals else None
                vals['name'] = self.env['ir.sequence'].with_company(vals.get('company_id')).next_by_code(
                    'mrp.workorder.batch', sequence_date=seq_date) or _("New")

        return super().create(vals_list)
    
    def _sync_linked_workorders(self):
        """Recalcula qty_produced de las OTs que PROCESAN estas partidas
        (las tienen en batch_ids): su cantidad producida es el peso de los
        rollos de la partida que pertenecen a su OF, asi que cualquier
        cambio de composicion/estado de la partida las desactualiza."""
        if not self.ids:
            return
        self.env['mrp.workorder'].search(
            [('batch_ids', 'in', self.ids)])._sync_textile_qty_produced()

    def write(self, vals):
        # Partida DIVIDIDA = registro histórico, solo lectura para trazabilidad.
        # Se bloquea cualquier edición de usuario; se permiten los recomputes
        # del sistema (campos computados almacenados, que se escriben por flush
        # cuando cambian los hijos) y el bypass explícito de flujos internos.
        if not self.env.context.get('bypass_split_readonly'):
            split = self.filtered(lambda b: b.state == 'split')
            if split:
                raise UserError(_(
                    'La partida %s está dividida: es un registro histórico de '
                    'solo lectura (trazabilidad).') % split[0].name)
        res = super().write(vals)
        if {'wo_roll_ids', 'state'} & set(vals.keys()):
            self._sync_linked_workorders()
        return res

    def clear_rolls(self):
        workorders = self.wo_roll_ids.mapped('workorder_id')
        self.wo_roll_ids = [Command.clear()]
        workorders._sync_textile_qty_produced()
    
    def create_batch(self):
        for rec in self:
            if any(roll.in_batch for roll in rec.wo_roll_ids):
                raise UserError(_('Some rolls are in other batch, please select rolls again.'))
            # Verifica que todos los rollos compartan color a procesar (los
            # transferidos usan el color de su nueva OF).
            rec._check_same_color_recipe()
            rec._check_same_option_per_production()
            rec.wo_roll_ids.write({'in_batch': True})
            rec.state = 'batch'
            rec.wo_roll_ids.mapped('workorder_id')._sync_textile_qty_produced()
            # Varios productos que se tiñen juntos: una partida por producto
            # con el mismo número (lote de teñido).
            rec._split_by_product()

    def action_back_to_draft(self):
        """Devuelve la partida a borrador para corregir su composición
        (rollos de más o de menos), SOLO si nadie la usó todavía: sin
        registros de operación en taller, sin OTs que la tengan anexada
        y sin divisiones de por medio."""
        for rec in self:
            if rec.state != 'batch':
                raise UserError(_(
                    'Solo una partida confirmada puede regresar a borrador.'))
            if rec.parent_batch_id:
                raise UserError(_(
                    'La partida %(batch)s es una sub-partida: su composición '
                    'proviene de la división de %(parent)s. Corrígela con una '
                    'nueva división, no regresándola a borrador.',
                    batch=rec.name, parent=rec.parent_batch_id.name))
            if 'batch.registry' in self.env:
                registries = self.env['batch.registry'].search_count(
                    [('batch_id', '=', rec.id)])
                if registries:
                    raise UserError(_(
                        'La partida %(batch)s ya tiene %(count)s registro(s) '
                        'de operación en el taller; no puede regresar a '
                        'borrador.', batch=rec.name, count=registries))
            using_wos = self.env['mrp.workorder'].search(
                [('batch_ids', 'in', rec.id)])
            if using_wos:
                raise UserError(_(
                    'La partida %(batch)s ya está anexada a la(s) OT(s): '
                    '%(wos)s; no puede regresar a borrador.',
                    batch=rec.name,
                    wos=', '.join(using_wos.mapped('display_name'))))
            rec.wo_roll_ids.write({'in_batch': False})
            rec.state = 'draft'
            rec.wo_roll_ids.mapped('workorder_id')._sync_textile_qty_produced()
            rec.message_post(body=_(
                'Partida regresada a borrador para corregir su composición.'))

    def unbuild_batch(self):
        # if self.workorder_id:
        #     raise UserError(_('Can\'t unbild a batch already in use, production %s.') %self.workorder_id.production_id.name)
        for rec in self:
            # Con registros de operación no se puede desarmar (solo dividir).
            if 'batch.registry' in self.env and self.env['batch.registry'].search_count(
                    [('batch_id', '=', rec.id)]):
                raise UserError(_(
                    'La partida %s ya tiene registros de operación; no se puede '
                    'desarmar (solo dividir en sub-partidas).') % rec.name)
            rec.wo_roll_ids.write({'in_batch': False})
            rec.state = 'unbuild'
            rec.wo_roll_ids.mapped('workorder_id')._sync_textile_qty_produced()

    def rebuild_batch(self):
        for rec in self:
            if any(roll.in_batch for roll in rec.wo_roll_ids):
                raise UserError(_('Some rolls are in other batch, can\'t rebuild batch.'))
            # Re-verifica el color a procesar: rollos transferidos usan el color
            # de su NUEVA OF, así que al rearmar hay que revalidar que todos los
            # rollos (aunque sean de productos distintos) compartan color.
            rec._check_same_color_recipe()
            rec._check_same_option_per_production()
            rec.wo_roll_ids.write({'in_batch': True})
            rec.state = 'batch'
            rec.wo_roll_ids.mapped('workorder_id')._sync_textile_qty_produced()

    # ------------------------------------------------------------------
    # División de partida (sublotes)
    # ------------------------------------------------------------------
    def action_open_split_wizard(self):
        self.ensure_one()
        if self.state != 'batch':
            raise UserError(_('Solo se puede dividir una partida confirmada.'))
        # Solo se puede dividir una partida que YA tiene registros de operación.
        if 'batch.registry' in self.env and not self.env['batch.registry'].search_count(
                [('batch_id', '=', self.id)]):
            raise UserError(_(
                'La partida %s aún no tiene registros de operación; no se puede '
                'dividir todavía (por ahora solo desarmar).') % self.name)
        if len(self.wo_roll_ids) < 2:
            raise UserError(_('La partida necesita al menos 2 rollos para dividirse.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Dividir partida %s') % self.name,
            'res_model': 'mrp.workorder.batch.split',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_batch_id': self.id},
        }

    def _apply_split(self, groups):
        """Divide la partida en sub-partidas <nombre>-<código>.

        `groups` = {código: recordset de rollos}. Reglas: todos los rollos de la
        partida quedan asignados a exactamente un grupo y hay al menos 2 grupos.
        El padre conserva el nombre y el registro del teñido (pasa a estado
        'Dividida', sin rollos propios: su composición histórica es la unión de
        sus hijas). Las hijas heredan fecha/última operación y siguen su ruta
        por separado.
        """
        self.ensure_one()
        if self.state != 'batch':
            raise UserError(_('Solo se puede dividir una partida confirmada.'))
        groups = {
            (code or '').strip().upper(): rolls
            for code, rolls in groups.items() if rolls
        }
        if len(groups) < 2:
            raise UserError(_('La división requiere al menos 2 grupos con rollos.'))
        union = self.env['mrp.workorder.roll']
        total = 0
        for rolls in groups.values():
            union |= rolls
            total += len(rolls)
        if union != self.wo_roll_ids or total != len(self.wo_roll_ids):
            raise UserError(_(
                'Todos los rollos de la partida deben quedar asignados a '
                'exactamente un grupo (sin repetidos ni faltantes).'))

        children = self.env['mrp.workorder.batch']
        for code in sorted(groups):
            name = '%s-%s' % (self.name, code)
            if self.search_count([('name', '=', name)]):
                raise UserError(_('Ya existe una partida con el nombre %s.') % name)
            children |= self.create([{
                'name': name,
                'parent_batch_id': self.id,
                'split_code': code,
                'batch_date': self.batch_date,
                'mrwo_id': self.mrwo_id.id,
                'state': 'batch',
                'wo_roll_ids': [Command.set(groups[code].ids)],
            }])
        # El padre queda como registro histórico del teñido (sin rollos propios;
        # los rollos siguen in_batch=True porque viven en las hijas).
        self.wo_roll_ids = [Command.clear()]
        self.state = 'split'
        self.message_post(body=_(
            'Partida dividida en: %s') % ', '.join(children.mapped('name')))
        for child in children:
            child.message_post(body=_(
                'Sub-partida creada por división de %s (teñida junto a %s).') % (
                self.name, ', '.join((children - child).mapped('name'))))
        return children

    def action_view_children(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sub-partidas de %s') % self.name,
            'res_model': 'mrp.workorder.batch',
            'view_mode': 'list,form',
            'domain': [('parent_batch_id', '=', self.id)],
        }

    def action_view_parent(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.workorder.batch',
            'res_id': self.parent_batch_id.id,
            'view_mode': 'form',
        }