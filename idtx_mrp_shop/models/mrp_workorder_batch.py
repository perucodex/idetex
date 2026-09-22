from markupsafe import Markup, escape

from odoo import fields, models, api, _
from odoo.exceptions import AccessError, UserError
from odoo.fields import Domain
import re
import requests

class MrpWorkorderBatch(models.Model):
    _inherit = 'mrp.workorder.batch'

    partner_ids = fields.Many2many('res.partner', string='Partners', compute='_compute_partner_ids', store=True)
    color_recipe_id = fields.Many2one(
        'color.recipe', string='Receta de Color',
        compute='_compute_colors', store=True,
        help='Receta con la que se tiñe la partida: la aprobada cuya '
             'combinación de productos coincide con los productos de los '
             'rollos (exacta primero; si no, la combinada que los contenga).')
    # La sub-receta ya NO se resuelve sola por lot_key: la selecciona el
    # usuario en la partida (entre las sub-recetas de su receta de color).
    # Sin sub-receta seleccionada el Taller no deja registrar el teñido.
    recipe_lot_id = fields.Many2one(
        'color.recipe.lot', string='Sub-receta (Lotes)',
        domain="[('id', 'in', allowed_recipe_lot_ids)]",
        help='Sub-receta (combinación de lotes de hilo) con la que se tiñe '
             'la partida. La selecciona el usuario; sin ella no se puede '
             'registrar el teñido en el Taller. Solo se pueden elegir '
             'versiones VALIDADAS por laboratorio (ni pendientes ni '
             'obsoletas) cuya combinación de lotes coincida con los lotes '
             'de hilo de los rollos de la partida.')
    allowed_recipe_lot_ids = fields.Many2many(
        'color.recipe.lot', compute='_compute_allowed_recipe_lot_ids',
        string='Sub-recetas Elegibles',
        help='Sub-recetas validadas de la receta de color cuya combinación '
             'de lotes coincide EXACTAMENTE con los lotes de hilo de los '
             'rollos de la partida (los de la opción de tejido elegida). '
             'Si los rollos aún no tienen lotes registrados, todas las '
             'validadas de la receta.')

    def _is_customer_batch(self):
        """Partida de TELA DEL CLIENTE: todos sus rollos son recibidos del
        cliente (OF de servicio sin tejido, sin lotes de hilo conocidos)."""
        self.ensure_one()
        rolls = self.wo_roll_ids
        return bool(rolls) and all(r.origin == 'customer' for r in rolls)

    @api.depends('wo_roll_ids.thread_lot_ids', 'wo_roll_ids.origin',
                 'wo_roll_ids.production_id', 'color_recipe_id',
                 'dye_product_id', 'parent_batch_id.child_batch_ids.wo_roll_ids.thread_lot_ids',
                 'color_recipe_id.recipe_lot_ids.lot_ids',
                 'color_recipe_id.recipe_lot_ids.production_id',
                 'color_recipe_id.recipe_lot_ids.state')
    def _compute_allowed_recipe_lot_ids(self):
        Sub = self.env['color.recipe.lot']
        for batch in self:
            subs = batch.color_recipe_id.recipe_lot_ids.filtered(
                lambda r: r.state == 'validated')
            lots = (batch._dye_lot_rolls() if batch.dye_product_id
                    else batch.wo_roll_ids).thread_lot_ids
            if batch._is_customer_batch():
                # Tela del cliente: la sub-receta es la de SU OF (sin lotes).
                prods = batch.wo_roll_ids.production_id
                subs = subs.filtered(
                    lambda r: not r.lot_ids and r.production_id in prods)
            elif lots:
                # Igual que color.recipe._find_lot_subrecipe: compara contra
                # los lotes REALES de cada sub-receta (inmune a lot_key
                # desactualizado), con match exacto de la combinación.
                key = Sub._make_lot_key(lots.ids)
                subs = subs.filtered(
                    lambda r: Sub._make_lot_key(r.lot_ids.ids) == key)
            batch.allowed_recipe_lot_ids = subs
    # Candado de laboratorio: un responsable (group_module_laboratory_manager)
    # bloquea la sub-receta asignada y ya nadie puede cambiarla; solo él puede
    # revertir la asignación (quita la sub-receta y desbloquea).
    recipe_lot_locked = fields.Boolean(
        'Sub-receta Bloqueada', copy=False,
        help='Bloqueada por laboratorio: la sub-receta asignada ya no se '
             'puede cambiar hasta que un responsable de laboratorio revierta '
             'la asignación.')

    _LAB_MANAGER_GROUP = 'idtx_laboratory.group_module_laboratory_manager'

    def _es_lab_manager(self):
        # su: sudo/superuser (shell, scripts, flujos de sistema) no se bloquea.
        return self.env.su or self.env.user.has_group(self._LAB_MANAGER_GROUP)

    def _check_lab_manager(self):
        if not self._es_lab_manager():
            raise AccessError(_(
                'Solo un responsable de laboratorio puede bloquear o '
                'revertir la sub-receta de la partida.'))

    def write(self, vals):
        # Guardas del candado (bypass_recipe_lot_lock: flujos internos como
        # la división de partidas).
        if not self.env.context.get('bypass_recipe_lot_lock') \
                and {'recipe_lot_id', 'recipe_lot_locked'} & set(vals):
            es_manager = self._es_lab_manager()
            if 'recipe_lot_locked' in vals and not es_manager:
                raise AccessError(_(
                    'Solo un responsable de laboratorio puede bloquear o '
                    'revertir la sub-receta de la partida.'))
            if 'recipe_lot_id' in vals:
                desbloqueando = es_manager and vals.get('recipe_lot_locked') is False
                locked = self.filtered('recipe_lot_locked')
                if locked and not desbloqueando:
                    raise UserError(_(
                        'La sub-receta de %s está bloqueada por laboratorio: '
                        'pide a un responsable de laboratorio revertir la '
                        'asignación.') % locked[0].name)
        res = super().write(vals)
        # Lote de teñido: la sub-receta se elige una vez y vale para todas
        # las partidas por producto (misma receta, mismo baño).
        if 'recipe_lot_id' in vals and not self.env.context.get('skip_dye_sibling_sync'):
            for batch in self:
                siblings = batch.dye_sibling_ids.filtered(
                    lambda b: b.recipe_lot_id != batch.recipe_lot_id)
                if siblings:
                    siblings.with_context(
                        skip_dye_sibling_sync=True, bypass_recipe_lot_lock=True,
                    ).write({'recipe_lot_id': vals['recipe_lot_id']})
        return res

    def action_lock_recipe_lot(self):
        self._check_lab_manager()
        for rec in self:
            if not rec.recipe_lot_id:
                raise UserError(_(
                    'La partida %s no tiene sub-receta seleccionada.') % rec.name)
            if rec.recipe_lot_locked:
                continue
            rec.recipe_lot_locked = True
            rec.message_post(body=_(
                'Sub-receta %s bloqueada por laboratorio.')
                % rec.recipe_lot_id.display_name)

    def action_unlock_recipe_lot(self):
        self._check_lab_manager()
        for rec in self.filtered('recipe_lot_locked'):
            sub = rec.recipe_lot_id.display_name
            rec.write({'recipe_lot_id': False, 'recipe_lot_locked': False})
            rec.message_post(body=_(
                'Asignación de sub-receta revertida por laboratorio '
                '(era %s).') % sub)
    color_code = fields.Char(related='color_recipe_id.color_code', string='Código de Color')
    color_name = fields.Char(related='color_recipe_id.color_name', string='Nombre de Color')
    registry_ids = fields.One2many('batch.registry', 'batch_id', string='Registers')
    reprocess_count = fields.Integer(
        'Reprocesos', compute='_compute_reprocess_count',
        help='Reprocesos asignados a la partida: alertas de calidad de reproceso '
             'aprobadas, ya ejecutadas o pendientes en el Taller.')
    quality_alert_ids = fields.One2many(
        'quality.alert', 'batch_id', string='Alertas de Calidad')
    quality_alert_count = fields.Integer(
        'N° Alertas', compute='_compute_quality_alert_count')
    # Operaciones (mrwo_id) con un reproceso PENDIENTE para esta partida: las
    # marca el reproceso al reabrir (X + posteriores) y las limpia el Taller al
    # re-registrar. Sirve para que una partida ya procesada vuelva a aparecer en
    # el buscador de partidas SOLO cuando hay un reproceso en curso.
    pending_reprocess_mrwo_ids = fields.Many2many(
        'mrp.routing.workcenter.operation',
        'batch_pending_reprocess_mrwo_rel', 'batch_id', 'mrwo_id',
        string='Reprocesos Pendientes', copy=False)
    # "Última Operación": la operación del registro (batch.registry) más
    # reciente de la partida (= última operación realizada). Si aún no tiene
    # registros propios (sub-partida recién dividida), hereda la del padre.
    mrwo_id = fields.Many2one(
        'mrp.routing.workcenter.operation', string='Last Operation',
        compute='_compute_last_operation', store=True, readonly=True,
        recursive=True)
    recipe_lot_warning = fields.Text(
        'Aviso de Receta por Lote', compute='_compute_recipe_lot_warning',
        help='Alerta cuando la combinación de lotes de hilo de los rollos de '
             'la partida no tiene sub-receta validada en la receta de color.')

    @api.depends('wo_roll_ids.thread_lot_ids', 'color_recipe_id',
                 'recipe_lot_id', 'recipe_lot_id.state', 'recipe_lot_id.lot_key',
                 'color_recipe_id.product_ids',
                 'color_recipe_id.recipe_lot_ids.lot_key',
                 'color_recipe_id.recipe_lot_ids.state')
    def _compute_recipe_lot_warning(self):
        for batch in self:
            batch.recipe_lot_warning = False
            rolls = batch.wo_roll_ids
            if not rolls:
                continue
            recipe = batch.color_recipe_id
            msgs = []
            batch_products = rolls.mapped('product_id')
            customer = batch._is_customer_batch()
            if not recipe:
                msgs.append(_(
                    'No hay receta de color aprobada para la combinación de '
                    'producto(s) %(products)s de la partida: se debe '
                    'desarrollar/aprobar en laboratorio.',
                    products=' + '.join(batch_products.mapped('name'))))
            else:
                uncovered = batch_products - recipe.product_ids
                # Tela del cliente: la receta se desarrolló con otra tela; lo
                # que la valida es la sub-receta de la OF, no la lista de
                # productos.
                if uncovered and not customer:
                    msgs.append(_(
                        'La receta %(recipe)s no cubre lo(s) producto(s) '
                        '%(products)s de la partida: se requiere una receta '
                        'aprobada para esa combinación de productos.',
                        recipe=recipe.name,
                        products=', '.join(uncovered.mapped('name'))))
            no_lots = rolls.filtered(
                lambda r: not r.thread_lot_ids and r.origin != 'customer')
            if no_lots:
                msgs.append(_(
                    'Rollos sin lotes de hilo registrados: %s. No se puede '
                    'verificar la receta de su combinación de lotes.')
                    % ', '.join(no_lots.mapped('name')))
            lots = (batch._dye_lot_rolls() if batch.dye_product_id else rolls).thread_lot_ids
            if recipe and customer:
                # TELA DEL CLIENTE: sin lotes de hilo; la sub-receta es la de
                # la OF del cliente, validada por laboratorio.
                prods = rolls.production_id
                partner = rolls.partner_id[:1].name or prods.partner_id[:1].name or ''
                sub = batch.recipe_lot_id
                of_subs = recipe.recipe_lot_ids.filtered(
                    lambda r: not r.lot_ids and r.production_id in prods
                    and r.state != 'obsolete')
                if not sub:
                    validated = of_subs.filtered(lambda r: r.state == 'validated')
                    if validated:
                        msgs.append(_(
                            'Tela del cliente %(partner)s (%(prods)s) sin sub-receta '
                            'seleccionada: elígela en este formulario (existe '
                            '[%(sub)s] para la OF). Sin sub-receta no se puede '
                            'registrar el teñido en el Taller.',
                            partner=partner, prods=', '.join(prods.mapped('name')),
                            sub=validated[:1].display_name))
                    else:
                        msgs.append(_(
                            'Tela del cliente %(partner)s (%(prods)s): la OF aún no '
                            'tiene sub-receta validada en %(recipe)s (%(color)s). '
                            'Laboratorio debe registrarla y validarla (sin lotes de '
                            'hilo) y luego seleccionarla en la partida. Sin '
                            'sub-receta no se puede registrar el teñido en el Taller.',
                            partner=partner, prods=', '.join(prods.mapped('name')),
                            recipe=recipe.name, color=recipe.color_name or ''))
                else:
                    if sub.state == 'obsolete':
                        msgs.append(_(
                            'La sub-receta seleccionada [%s] está OBSOLETA: '
                            'selecciona la versión vigente.') % sub.display_name)
                    elif sub.state != 'validated':
                        msgs.append(_(
                            'La sub-receta seleccionada [%(sub)s] de %(recipe)s '
                            'sigue PENDIENTE de validación de laboratorio.',
                            sub=sub.display_name, recipe=recipe.name))
                    if sub.lot_ids or sub.production_id not in prods:
                        msgs.append(_(
                            'La sub-receta seleccionada [%(sub)s] no es la de la OF '
                            'de estos rollos del cliente (%(prods)s): revisa la '
                            'selección.', sub=sub.display_name,
                            prods=', '.join(prods.mapped('name'))))
            elif recipe and lots:
                lot_names = ', '.join(lots.mapped('name'))
                sub = batch.recipe_lot_id
                if not sub:
                    # La sub-receta la elige el usuario; se le orienta según
                    # exista o no una para la combinación de lotes de los rollos.
                    match = recipe._find_lot_subrecipe(lots)
                    if match:
                        msgs.append(_(
                            'La partida no tiene sub-receta seleccionada: '
                            'elígela en este formulario (existe [%(match)s] '
                            'para la combinación de lotes [%(lots)s]). Sin '
                            'sub-receta no se puede registrar el teñido en '
                            'el Taller.',
                            match=match.display_name, lots=lot_names))
                    else:
                        msgs.append(_(
                            'La combinación de lotes de hilado [%(lots)s] aún '
                            'no tiene sub-receta en %(recipe)s (%(color)s): se '
                            'debe validar en laboratorio y luego seleccionarla '
                            'en la partida. Sin sub-receta no se puede '
                            'registrar el teñido en el Taller.',
                            lots=lot_names, recipe=recipe.name,
                            color=recipe.color_name or ''))
                else:
                    if sub.state == 'obsolete':
                        current = sub._version_group().filtered(
                            lambda r: r.state == 'validated')[:1]
                        detail = _(' (la vigente es [%s])') % current.display_name \
                            if current else ''
                        msgs.append(_(
                            'La sub-receta seleccionada [%(sub)s] está '
                            'OBSOLETA%(detail)s: selecciona la versión '
                            'vigente.', sub=sub.display_name, detail=detail))
                    elif sub.state != 'validated':
                        msgs.append(_(
                            'La sub-receta seleccionada [%(sub)s] de %(recipe)s '
                            'sigue PENDIENTE de validación de laboratorio.',
                            sub=sub.display_name, recipe=recipe.name))
                    if sub.lot_key != sub._make_lot_key(lots.ids):
                        msgs.append(_(
                            'La sub-receta seleccionada [%(sub)s] no coincide '
                            'con los lotes de hilo de los rollos de la partida '
                            '[%(lots)s]: revisa la selección.',
                            sub=sub.display_name, lots=lot_names))
            batch.recipe_lot_warning = '\n'.join(msgs) if msgs else False

    @api.depends('wo_roll_ids')
    def _compute_partner_ids(self):
        for rec in self:
            partners = rec.wo_roll_ids.production_id.sale_order_line_id.order_id.mapped('partner_id')
            rec.partner_ids = [(6, 0, partners.ids)] if partners else [(5, 0, 0)]

    @api.depends('wo_roll_ids', 'child_batch_ids.wo_roll_ids', 'wo_roll_ids.origin',
                 'dye_product_id', 'parent_batch_id.child_batch_ids.wo_roll_ids',
                 'wo_roll_ids.production_id.color_recipe_id',
                 'wo_roll_ids.production_id.manual_lab_dev_line_id',
                 'wo_roll_ids.production_id.sale_order_line_id.lab_dev_line_id.color_recipe_ids.state',
                 'wo_roll_ids.production_id.sale_order_line_id.lab_dev_line_id.color_recipe_ids.recipe_lot_ids.production_id')
    def _compute_colors(self):
        """La PARTIDA resuelve su receta por combinación de productos: la
        receta aprobada del color (línea de Lab Dip de las OFs) cuya
        combinación coincide EXACTAMENTE con los productos de los rollos;
        si no hay exacta, la combinada que los contenga (la más chica)."""
        for rec in self:
            rolls = rec.wo_roll_ids
            if not rolls and rec.child_batch_ids:
                # Partida dividida: conserva el color histórico desde sus hijas.
                rolls = rec.child_batch_ids.wo_roll_ids
            productions = rolls.production_id
            # Color: del Lab Dip del pedido; si no, de la receta de la OF; si
            # no, el color elegido a mano en una OF libre (muestra/piloto).
            line = (productions.sale_order_line_id.lab_dev_line_id
                    or productions.color_recipe_id.lab_dev_line_id
                    or productions.manual_lab_dev_line_id)[:1]
            # Partida por producto de un lote de teñido: la receta es la de la
            # COMBINACIÓN de productos que se tiñen juntos (todo el lote).
            lot_rolls = rec._dye_lot_rolls() if rec.dye_product_id else rolls
            products = lot_rolls.mapped('product_id')
            recipe = self.env['color.recipe']
            if line and products:
                candidates = line.color_recipe_ids.filtered(
                    lambda r: r.state == 'approved'
                    and not (products - r.product_ids))
                exact = candidates.filtered(
                    lambda r: r._product_key() == tuple(sorted(products.ids)))
                recipe = (exact or candidates.sorted(
                    key=lambda r: (len(r.product_ids), r.id)))[:1]
            if not recipe and line and rolls and all(r.origin == 'customer' for r in rolls):
                # TELA DEL CLIENTE: la tela del cliente no suele estar entre
                # los productos de la receta (se desarrolló con otra tela).
                # Manda la receta aprobada del color que tenga la sub-receta
                # de la OF del cliente; si aún no la tiene y el color solo
                # tiene una receta aprobada, esa.
                approved = line.color_recipe_ids.filtered(lambda r: r.state == 'approved')
                with_sub = approved.filtered(lambda r: r.recipe_lot_ids.filtered(
                    lambda s: not s.lot_ids and s.state != 'obsolete'
                    and s.production_id in productions))
                recipe = (with_sub or (approved if len(approved) == 1 else approved.browse()))[:1]
            if not recipe:
                # Fallback legado: la receta resuelta en las OFs.
                recipe = productions.color_recipe_id[:1]
            rec.color_recipe_id = recipe

    def _split_for_reprocess(self, rolls, alert=None):
        child = super()._split_for_reprocess(rolls, alert=alert)
        if child and self.recipe_lot_id:
            child.with_context(bypass_recipe_lot_lock=True, skip_dye_sibling_sync=True).write({
                'recipe_lot_id': self.recipe_lot_id.id,
                'recipe_lot_locked': self.recipe_lot_locked,
            })
        return child

    def _split_by_product(self):
        children = super()._split_by_product()
        if children and self.recipe_lot_id:
            children.with_context(bypass_recipe_lot_lock=True, skip_dye_sibling_sync=True).write({
                'recipe_lot_id': self.recipe_lot_id.id,
                'recipe_lot_locked': self.recipe_lot_locked,
            })
        return children

    def _apply_split(self, groups):
        # Las sub-partidas heredan la sub-receta elegida en el padre (se tiñeron
        # juntas con ella) y su candado; sin esto, dividir obligaría a
        # re-seleccionarla. bypass: el que divide no es de laboratorio.
        children = super()._apply_split(groups)
        if self.recipe_lot_id:
            children.with_context(bypass_recipe_lot_lock=True).write({
                'recipe_lot_id': self.recipe_lot_id.id,
                'recipe_lot_locked': self.recipe_lot_locked,
            })
        return children

    @api.depends('quality_alert_ids.tipo', 'quality_alert_ids.state')
    def _compute_reprocess_count(self):
        # Reprocesos ASIGNADOS a la partida (alertas de reproceso aprobadas),
        # ejecutados o pendientes. Una partida de reproceso parcial nace con 1
        # (la alerta se traslada a ella) y la original solo cuenta los suyos
        # (JP, 18-sep-2026). Las ejecuciones siguen en registry.reprocess_number.
        for rec in self:
            rec.reprocess_count = len(rec.quality_alert_ids.filtered(
                lambda a: a.tipo == 'reproceso' and a.state == 'approved'))

    @api.depends('quality_alert_ids')
    def _compute_quality_alert_count(self):
        for rec in self:
            rec.quality_alert_count = len(rec.quality_alert_ids)

    @api.depends('registry_ids.registry_date', 'registry_ids.workorder_id.mrwo_id',
                 'parent_batch_id.mrwo_id')
    def _compute_last_operation(self):
        sentinel = fields.Datetime.to_datetime('1900-01-01 00:00:00')
        for rec in self:
            regs = rec.registry_ids.sorted(
                key=lambda r: (r.registry_date or sentinel, r.id))
            rec.mrwo_id = (regs[-1].workorder_id.mrwo_id
                           if regs else rec.parent_batch_id.mrwo_id)

    def _get_lineage_registered_mrwo(self):
        """Operaciones (mrp.routing.workcenter.operation) que la partida YA
        procesó, contando el LINAJE: una sub-partida hereda los registros de
        sus partidas de origen (antes de dividirse pasaron por ellas)."""
        lineage = self.env['mrp.workorder.batch']
        for batch in self:
            node = batch
            lineage |= node
            while node.parent_batch_id:
                node = node.parent_batch_id
                lineage |= node
        return lineage.registry_ids.mapped('workorder_id.mrwo_id')

    def _get_process_tree(self):
        """Árbol genealógico de los procesos (OTs) de la partida según las OFs
        de sus rollos. Mientras las rutas coinciden operación-a-operación es un
        tramo COMPARTIDO (banda con todas las OFs + operaciones); en cuanto
        divergen se ramifica (columnas lado a lado), recursivo, hasta la
        cabecera por OF. Devuelve el nodo raíz anidado:
        {'ofs': [nombres], 'ops': [operaciones], 'branches': [nodos hijos]}."""
        self.ensure_one()
        productions = self.origin_roll_ids.production_id
        of_seqs = []
        for prod in productions:
            wos = prod.workorder_ids.sorted(lambda w: (w.sequence, w.id))
            of_seqs.append({
                'prod': prod,
                'ops': [(w.mrwo_id.name or w.name or '') for w in wos],
            })
        if not of_seqs:
            return {}
        return self._build_process_node(of_seqs, 0)

    def _build_process_node(self, group, depth):
        # Avanza el prefijo COMPARTIDO: mientras todas las OFs del grupo tengan
        # la misma operación en la posición `d`.
        shared = []
        d = depth
        while True:
            ops_at_d = [g['ops'][d] if len(g['ops']) > d else None for g in group]
            if any(o is None for o in ops_at_d) or len(set(ops_at_d)) != 1:
                break
            shared.append(ops_at_d[0])
            d += 1
        # Divergencia: subgrupos por operación en la posición `d` (recursivo).
        subgroups, order = {}, []
        for g in group:
            if len(g['ops']) > d:
                key = g['ops'][d]
                if key not in subgroups:
                    subgroups[key] = []
                    order.append(key)
                subgroups[key].append(g)
        branches = [self._build_process_node(subgroups[k], d) for k in order]
        return {
            'ofs': [g['prod'].name for g in group],
            'ops': shared,
            'branches': branches,
        }

    def action_view_quality_alerts(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Alertas de Calidad de %s') % self.name,
            'res_model': 'quality.alert',
            'view_mode': 'list,form',
            'domain': [('batch_id', '=', self.id)],
            'context': {'default_batch_id': self.id},
        }

    # =========================
    # Reporte "Receta de Tinte"
    # =========================
    def _get_report_rolls_by_product(self):
        """Rollos del Reporte de Partida agrupados por PRODUCTO. Cada grupo se
        parte en DOS COLUMNAS (se lee hacia abajo la izquierda y sigue la
        derecha) para que la tabla no ocupe todo el ancho ni tantas páginas.
        Devuelve una lista de dicts con el producto, las filas emparejadas
        (izquierda, derecha|False) y los subtotales del producto."""
        self.ensure_one()
        Roll = self.env['mrp.workorder.roll']
        groups = {}
        for roll in self.origin_roll_ids:
            groups.setdefault(roll.product_id, Roll)
            groups[roll.product_id] |= roll
        data = []
        for product, rolls in groups.items():
            ordered = rolls.sorted(key=lambda r: (r.name or '', r.id))
            half = (len(ordered) + 1) // 2
            left, right = ordered[:half], ordered[half:]
            data.append({
                'product': product,
                # Rectilíneo (cuellos/puños): los rollos llevan talla y
                # cantidad de piezas; en tela plana esas columnas no aplican.
                'rect': product.analysis_id.weave_type == 'rect',
                'rolls': ordered,
                'rows': [(left[i], right[i] if i < len(right) else False)
                         for i in range(half)],
                # Con un solo rollo (o ninguno a la derecha) la segunda
                # columna no se dibuja: no tiene sentido una cabecera vacía.
                'has_right': bool(right),
                'count': len(ordered),
                'quantity': sum(ordered.mapped('quantity')),
                'weight': sum(ordered.mapped('gross_weight')),
            })
        return sorted(data, key=lambda g: g['product'].display_name or '')

    def _get_dye_report_data(self):
        """Datos del reporte Receta de Tinte de la partida:
        - Kilos (peso bruto de los rollos), Piezas (n° de rollos).
        - Volumen (L) = Kilos x Relación de Baño (sub-receta > receta > línea LabDip).
        - Metros = kilos de cada producto x rendimiento (m/kg) de su ficha
          técnica (análisis).
        - Cantidad por químico: Gr/L -> factor x Volumen; % -> factor x Kilos
          (en gramos). Procesos de la sub-receta si tiene propios; si no, los
          de la receta madre.
        """
        self.ensure_one()
        # Kilos del BAÑO: en una partida por producto de un lote de teñido se
        # suman las hermanas (la relación de baño es del lote completo).
        rolls = self._dye_lot_rolls()
        recipe = self.color_recipe_id
        sub = self.recipe_lot_id
        # Kilos con Control de peso: peso tras control de cada partida del baño
        # (o su crudo si aún no pasó por el control). Los kilos por producto se
        # escalan en la misma proporción para que sigan sumando el total.
        raw_kilos = sum(rolls.mapped('gross_weight'))
        kilos = sum(self._dye_lot_batches().mapped('recipe_weight')) or raw_kilos
        weight_factor = (kilos / raw_kilos) if raw_kilos else 1.0
        rb = (sub.bath_ratio if sub else 0) or (recipe.bath_ratio if recipe else 0) \
            or (recipe.lab_dev_line_id.bath_ratio if recipe and recipe.lab_dev_line_id else 0)
        fac_abs = (sub.absorption_factor if sub else 0.0) \
            or (recipe.absorption_factor if recipe else 0.0)
        volume = kilos * rb
        products, total_meters = [], 0.0
        for tmpl in rolls.mapped('product_id'):
            p_rolls = rolls.filtered(lambda r: r.product_id == tmpl)
            p_kilos = round(sum(p_rolls.mapped('gross_weight')) * weight_factor, 2)
            yield_m = tmpl.analysis_id.yield_meter if tmpl.analysis_id else 0.0
            meters = p_kilos * yield_m
            total_meters += meters
            products.append({
                'product': tmpl, 'kilos': p_kilos, 'yield': yield_m,
                'meters': meters, 'pieces': len(p_rolls),
            })
        processes = []
        process_src = (sub.process_ids if sub and sub.process_ids
                       else (recipe.color_recipe_process_ids if recipe else self.env['color.recipe.process']))
        # N° de ingreso a máquina ACUMULATIVO entre procesos: cada proceso
        # base numera desde 1, pero en la receta completa la numeración
        # continúa (proceso 1 usa 1..2 -> el N° 1 del proceso 2 se imprime 3).
        order_offset = 0
        # CF de la receta completa: fallback para las tablas de los procesos
        # SIN colorantes propios (p.ej. preparado con sal) — la sal se dosifica
        # según el colorante del teñido aunque viva en otro proceso.
        cf_total = process_src._cf_sum()
        for proc in process_src.sorted(lambda p: (p.sequence, p.id)):
            lines, max_local = [], 0
            proc_lines = proc.color_recipe_process_line_ids
            # CF del proceso (suma de % de colorantes, incluye sub-líneas del
            # hueco COLORANTES): resuelve EN VIVO las líneas con TABLA cuyo
            # factor guardado quedó desactualizado (recetas históricas).
            cf = proc._cf_sum() or cf_total
            for l in proc_lines:
                local = l.order_number or 1
                max_local = max(max_local, local)
                # Hueco COLORANTES: se imprimen sus sub-líneas (los productos
                # reales elegidos por el laboratorio), no el hueco en sí.
                sub_lines = l.child_ids if l.line_type == 'colorants' else l
                if l.line_type == 'colorants' and not l.child_ids:
                    continue
                for sl in sub_lines:
                    factor = sl.factor
                    if sl.base_line_id.range_ids and not sl.factor_manual:
                        rng = sl.base_line_id.range_ids.filtered(
                            lambda r: r.percent_from <= cf <= r.percent_to)[:1]
                        if rng:
                            factor = rng.factor
                    grams = (factor * volume) if sl.uom == 'gxl' \
                        else (factor / 100.0 * kilos * 1000.0)
                    lines.append({'line': sl, 'factor': factor, 'grams': grams,
                                  'has_table': bool(sl.base_line_id.range_ids),
                                  'order': order_offset + local})
            order_offset += max_local
            processes.append({'process': proc, 'lines': lines})
        return {
            'rolls': rolls, 'kilos': kilos, 'pieces': len(rolls),
            'rb': rb, 'fac_abs': fac_abs, 'volume': volume,
            'meters': total_meters, 'products': products,
            'recipe': recipe, 'sub': sub, 'processes': processes,
            'productions': rolls.production_id,
        }

    def action_print_dye_recipe(self):
        return self.env.ref(
            'idtx_mrp_shop.action_report_batch_dye_recipe').report_action(self)

    def get_dye_recipe_html(self):
        """HTML del contenido del reporte (mismas tablas), para el modal
        en pantalla del botón Mostrar Receta."""
        self.ensure_one()
        return self.env['ir.qweb']._render(
            'idtx_mrp_shop.report_batch_dye_recipe_content', {'doc': self})

    def action_show_dye_recipe(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'idtx_mrp_shop.dye_recipe_dialog',
            'params': {'batch_id': self.id, 'title': _('Receta de Tinte %s') % self.name},
        }

    # =========================
    # Lookup para UI (Shop Floor)
    # =========================
    @api.model
    def search_batch_lookup(self, query="", limit=20, state="batch", prefer_id=None,
                            workorder_id=None):
        limit = int(limit or 20)
        # OT que llama (p.ej. TEÑIDO en el taller): filtra partidas con al menos
        # un rollo del MISMO producto de su OF, y marca con warning las que
        # traen rollos fabricados en OTRA OF.
        caller_wo = self.env['mrp.workorder'].browse(int(workorder_id)) if workorder_id else False
        caller_production = caller_wo.production_id if caller_wo else False
        caller_tmpl = caller_production.product_id.product_tmpl_id if caller_production else False
        query = (query or "").strip()
        query_terms = [term.strip() for term in query.split(",") if term.strip()] if query else []
        try:
            prefer_id = int(prefer_id) if prefer_id else None
        except (TypeError, ValueError):
            prefer_id = None

        has_partner_m2o = "partner_id" in self._fields
        has_partner_m2m = "partner_ids" in self._fields
        has_color_name = "color_name" in self._fields
        has_color_names = "color_names" in self._fields
        has_color_code = "color_code" in self._fields
        has_color_id = "color_id" in self._fields

        parts = []
        if state:
            parts.append(Domain("state", "=", state))
        if caller_tmpl:
            # roll.product_id es la plantilla del producto de su OT
            parts.append(Domain("wo_roll_ids.product_id", "=", caller_tmpl.id))
        caller_recipe = caller_production.color_recipe_id if caller_production else False
        if caller_recipe:
            # Mismo COLOR: la partida se tiñe con la receta de la OF llamante
            # (blanco no aparece si la OT es para negro).
            parts.append(Domain("color_recipe_id", "=", caller_recipe.id))

        # Ocultar partidas YA procesadas por esta operación (tienen un
        # batch.registry de la misma mrwo_id), salvo que tengan un reproceso
        # PENDIENTE en esa operación (lo marca la alerta de calidad al reabrir).
        # Las SUB-PARTIDAS heredan el proceso del padre: si un ancestro ya hizo
        # la operación, la hija tampoco aparece (las divididas solo divergen en
        # las operaciones POSTERIORES al split).
        if caller_wo and caller_wo.mrwo_id:
            mrwo = caller_wo.mrwo_id
            # "Ya procesada por ESTE paso de ruta": tiene un registro en LA OT
            # llamante o en una OT HERMANA (misma operación en OTRA OF, para
            # partidas multi-OF). NO se cuentan las operaciones duplicadas de la
            # MISMA OF (dos "CONTROL PESO" en la ruta son pasos distintos y cada
            # uno debe procesar la partida) -> el chequeo es por OT, no por
            # operación.
            processed = self.env['batch.registry'].search([
                '|',
                    ('workorder_id', '=', caller_wo.id),
                    '&',
                        ('workorder_id.mrwo_id', '=', mrwo.id),
                        ('workorder_id.production_id', '!=', caller_wo.production_id.id),
            ]).mapped('batch_id')
            lineage = processed
            frontier = processed
            while frontier:
                frontier = frontier.child_batch_ids
                lineage |= frontier
            excluded = lineage.filtered(
                lambda b: mrwo not in b.pending_reprocess_mrwo_ids)
            if excluded:
                parts.append(Domain('id', 'not in', excluded.ids))

            # La partida debe haber COMPLETADO la operación de partida ANTERIOR
            # de la ruta: no se registra esta operación sobre una partida que
            # aún no pasó el paso previo (p.ej. ABIERTO TINTO exige TEÑIDO
            # hecho). workorder_ids ya viene en orden de ruta; el predecesor es
            # la operación de partida inmediatamente anterior a la llamante. La
            # PRIMERA operación de partida de la ruta no tiene predecesora (no
            # exige nada).
            route_ops = list(caller_wo.production_id.workorder_ids.filtered(
                lambda w: w.operation_type in caller_wo.BATCH_OPERATION_TYPES))
            predecessor = False
            if caller_wo in route_ops:
                pos = route_ops.index(caller_wo)
                if pos > 0:
                    predecessor = route_ops[pos - 1]
            if predecessor and predecessor.mrwo_id:
                done = self.env['batch.registry'].search(
                    [('workorder_id.mrwo_id', '=', predecessor.mrwo_id.id)]
                ).mapped('batch_id')
                # Las SUB-PARTIDAS heredan el avance del ancestro: si un padre
                # completó el paso previo antes de dividirse, las hijas también
                # lo cumplen.
                eligible = done
                frontier = done
                while frontier:
                    frontier = frontier.child_batch_ids
                    eligible |= frontier
                parts.append(Domain('id', 'in', eligible.ids))

        if query_terms:
            term_domains = []
            for term in query_terms:
                or_parts = [Domain("name", "ilike", term)]
                if has_partner_m2o:
                    or_parts.append(Domain("partner_id.name", "ilike", term))
                if has_partner_m2m:
                    or_parts.append(Domain("partner_ids.name", "ilike", term))
                if has_color_name:
                    or_parts.append(Domain("color_name", "ilike", term))
                if has_color_names:
                    or_parts.append(Domain("color_names", "ilike", term))
                if has_color_code:
                    or_parts.append(Domain("color_code", "ilike", term))
                if has_color_id:
                    or_parts.append(Domain("color_id.name", "ilike", term))
                if "color_recipe_id" in self._fields:
                    or_parts.append(Domain("color_recipe_id.name", "ilike", term))
                term_domains.append(Domain.OR(or_parts))

            parts.append(Domain.AND(term_domains))

        # Domain final
        domain = Domain.AND(parts) if parts else Domain([])

        # _search acepta Domain y es el patrón usado en core Odoo 19
        ids = self._search(domain, limit=limit, order="batch_date desc, id desc")
        records = self.browse(ids)

        # Reordenar preferido arriba si aplica
        if prefer_id and prefer_id in ids:
            pref = records.filtered(lambda r: r.id == prefer_id)
            if pref:
                records = pref + (records - pref)

        # Post-reorder extra: exact match “normalizado” por name (opcional)
        if query and records:
            q_norm = re.sub(r"[\s\-_/]+", "", query_terms[0] if query_terms else query).upper()
            def norm(s): return re.sub(r"[\s\-_/]+", "", (s or "")).upper()
            exact = records.filtered(lambda r: norm(r.name) == q_norm)
            if exact:
                records = exact + (records - exact)

        state_map = dict(self._fields["state"].selection) if "state" in self._fields else {}

        res = []
        for rec in records:
            partner = ""
            if has_partner_m2o and rec.partner_id:
                partner = rec.partner_id.display_name
            elif has_partner_m2m and rec.partner_ids:
                partner = ", ".join(rec.partner_ids.mapped("display_name"))

            color = ""
            if has_color_code and rec.color_code:
                color = rec.color_code
                if has_color_name and rec.color_name:
                    color = f"{color} - {rec.color_name}"
                elif has_color_names and rec.color_names:
                    color = f"{color} - {rec.color_names}"
            elif has_color_name and rec.color_name:
                color = rec.color_name
            elif has_color_names and rec.color_names:
                color = rec.color_names
            elif has_color_id and rec.color_id:
                color = rec.color_id.display_name

            mrwo = rec.mrwo_id.display_name if "mrwo_id" in self._fields and rec.mrwo_id else ""
            st = rec.state if "state" in self._fields else False

            warning = ""
            if caller_production:
                foreign = (rec.wo_roll_ids.production_id
                           - caller_production)
                if foreign:
                    warning = _(
                        "Contiene rollos fabricados en otra OF: %s"
                    ) % ", ".join(foreign.mapped("name"))

            res.append({
                "id": rec.id,
                # display_name: las partidas por producto de un lote de teñido
                # comparten el número y se distinguen por el producto.
                "name": rec.display_name or rec.name or "",
                "batch_date": rec.batch_date or "",
                "total_weight": rec.total_weight,
                "state": st,
                "state_label": state_map.get(st, st or ""),
                "partner_id": partner,
                "color": color,
                "mrwo": mrwo,
                "warning": warning,
            })

        return res

    # ------------------------------------------------------------------
    # Pesado de rollos terminados (Operaciones → Pesado de rollos)
    # ------------------------------------------------------------------
    def get_weighable_products(self):
        """Productos de los rollos crudos de la partida (para el selector
        del diálogo de pesado)."""
        self.ensure_one()
        return [{'id': p.id, 'name': p.display_name}
                for p in self.wo_roll_ids.mapped('product_id')]

    def get_weighable_rolls(self, product_id):
        """Rollos CRUDOS de la partida para el producto (selector del diálogo
        de pesado): permite decir QUÉ rollo se está pesando y heredar su
        talla. SOLO rectilíneos (rollos con talla) — en telas el crudo no se
        mapea 1:1 con el terminado y el selector no aplica. Excluye los ya
        enlazados a un rollo terminado."""
        self.ensure_one()
        rolls = self.wo_roll_ids.filtered(
            lambda r: r.size_id and r.product_id.id == int(product_id))
        used = self.env['mrp.production.roll'].search(
            [('wo_roll_id', 'in', rolls.ids)]).wo_roll_id
        result = []
        for roll in rolls - used:
            label = roll.name or ''
            if roll.size_id:
                label += ' · Talla %s' % (roll.size_id.size or '')
            if roll.quantity:
                label += ' · %s und' % roll.quantity
            result.append({'id': roll.id, 'name': label})
        return result

    def _roll_lot_name(self, roll_num):
        self.ensure_one()
        return '%s-%03d' % (self.name, int(roll_num))

    def _next_roll_lot_vals(self, production, roll_num):
        """Lote del rollo terminado: <partida>-<N° rollo de Acabado>. El N°
        lo teclea/escanea el pesador; si ya existe el lote, el rollo ya fue
        pesado (se repesa por Resolver observado, no por Pesar)."""
        self.ensure_one()
        name = self._roll_lot_name(roll_num)
        if self.env['stock.lot'].search_count(
                [('name', '=', name), ('product_id', '=', production.product_id.id)]):
            raise UserError(_('El rollo N° %(num)s ya fue pesado (lote %(lot)s).',
                              num=int(roll_num), lot=name))
        # Color del lote (sale en el sticker): receta de la partida, o de la OF.
        recipe = self.color_recipe_id or production.color_recipe_id
        return {'name': name, 'product_id': production.product_id.id,
                'color_recipe_id': recipe.id or False}

    # --- hooks para módulos de calidad (idtx_quality_control) ---
    def _get_roll_hold(self, roll_num):
        """Marca "separar para reproceso" de Calidad para ese N° rollo, o False."""
        return False

    def _after_weigh_finished_roll(self, roll):
        return True

    def _after_resolve_observed_roll(self, roll):
        return True

    def get_roll_num_info(self, roll_num):
        """Info para el diálogo al teclear el N° de rollo: si ya se pesó y si
        Calidad pidió separarlo."""
        self.ensure_one()
        try:
            roll_num = int(roll_num)
        except (TypeError, ValueError):
            return {'valid': False}
        if roll_num <= 0:
            return {'valid': False}
        lot = self.env['stock.lot'].search([('name', '=', self._roll_lot_name(roll_num))], limit=1)
        return {
            'valid': True,
            'lot': lot.name if lot else False,
            'weighed': bool(lot),
            'hold': self._get_roll_hold(roll_num),
        }

    def get_reweigh_rolls(self):
        """Rollos observados a los que Calidad ya dio grado final y que
        vuelven del área de reproceso: pendientes de REPESAR."""
        self.ensure_one()
        rolls = self.env['mrp.production.roll'].search(
            [('batch_id', '=', self.id), ('lot_id', '!=', False),
             ('reweigh_pending', '=', True), ('quality_released', '=', False)],
            order='roll_num, id')
        return [{
            'id': r.id,
            'grade': r.quality_grade,
            'name': '%s · grado %s · %.2f kg · %s%s' % (
                r.lot_id.name, r.quality_grade or '?', r.net_weight,
                r._quality_observation_label(),
                (' · ' + r.quality_note) if r.quality_note else ''),
        } for r in rolls]

    def get_observed_pending_grade(self):
        """Observados sin grado final todavía: Calidad debe calificarlos en
        "Rollos Observados" antes de que Pesado los repese."""
        self.ensure_one()
        rolls = self.env['mrp.production.roll'].search(
            [('batch_id', '=', self.id), ('lot_id', '!=', False),
             ('quality_state', '=', 'observed')], order='roll_num, id')
        return [{'id': r.id, 'name': '%s · %s%s' % (
            r.lot_id.name, r._quality_observation_label(),
            (' · ' + r.quality_note) if r.quality_note else '')} for r in rolls]

    def _read_roll_weight(self, scale, manual_weight):
        """Peso del diálogo (balanza en vivo o manual) o relectura del
        servidor de la balanza IP. Devuelve (peso, mensaje_error)."""
        peso = None
        if manual_weight not in (None, False, ''):
            peso = round(float(manual_weight), 2)
        if peso is None:
            if not scale or not scale.ip:
                return None, _('Sin balanza seleccionada ni peso válido.')
            resp = requests.get('http://%s:5001/peso' % scale.ip, timeout=3)
            resp.raise_for_status()
            data = resp.json()
            if data.get('ok') and data.get('peso') is not None:
                peso = round(float(data['peso']), 2)
            else:
                return None, _('Sin comunicación con la balanza.')
        if not peso or peso <= 0:
            return None, _('No se obtuvo un peso válido.')
        return peso, ''

    # ------------------------------------------------------------------
    # Liberación a almacén: traslado interno Pesado → destino por grado
    # ------------------------------------------------------------------
    finished_roll_ids = fields.One2many(
        'mrp.production.roll', 'batch_id', string='Rollos terminados',
        domain=[('lot_id', '!=', False)])
    roll_releasable_count = fields.Integer(
        'Rollos por liberar', compute='_compute_roll_release_counts')
    release_picking_ids = fields.Many2many(
        'stock.picking', string='Recepciones de almacén', compute='_compute_roll_release_counts')
    release_picking_count = fields.Integer(compute='_compute_roll_release_counts')

    @api.depends('finished_roll_ids.quality_state', 'finished_roll_ids.quality_released',
                 'finished_roll_ids.reweigh_pending', 'finished_roll_ids.release_picking_id')
    def _compute_roll_release_counts(self):
        for batch in self:
            rolls = batch.finished_roll_ids
            batch.roll_releasable_count = len(batch._releasable_rolls())
            pickings = rolls.release_picking_id
            batch.release_picking_ids = pickings
            batch.release_picking_count = len(pickings)

    def _releasable_rolls(self):
        """Rollos pesados con grado final, ya repesados si venían de
        reproceso, y aún no liberados a almacén."""
        self.ensure_one()
        return self.finished_roll_ids.filtered(
            lambda r: r.quality_grade and not r.quality_released and r.lot_id
            and not r.reweigh_pending)

    def _roll_warehouse(self, production):
        warehouse = production.picking_type_id.warehouse_id \
            or production.location_dest_id.warehouse_id
        if not warehouse:
            raise UserError(_('La OF %s no tiene almacén (tipo de operación sin almacén).')
                            % production.name)
        return warehouse

    def action_release_rolls(self):
        """Libera los rollos calificados: crea la RECEPCIÓN de almacén (un
        traslado interno por grado desde la ubicación de pesado hacia
        Existencias / Saldo / Mermas) con un lote por rollo ya reservado.
        El almacenero valida el traslado al recibir físicamente los rollos.
        Los observados (sin grado) no se liberan: siguen en Pesado."""
        self.ensure_one()
        rolls = self._releasable_rolls()
        if not rolls:
            raise UserError(_('La partida %s no tiene rollos calificados pendientes de liberar.')
                            % self.name)
        pickings = self.env['stock.picking']
        missing, already = [], []
        now = fields.Datetime.now()
        # agrupar por almacén, grado y ubicación de origen → un traslado por destino
        groups = {}
        for roll in rolls:
            warehouse = self._roll_warehouse(roll.production_id)
            src = self._roll_stock_location(roll, warehouse)
            if not src:
                missing.append(roll.lot_id.name)
                continue
            dest = warehouse._get_roll_dest_location(roll.quality_grade)
            if src == dest:
                # Rollo del flujo anterior que ya está en su destino: se da
                # por recibido sin traslado.
                roll.write({'quality_released': True, 'quality_release_date': now})
                already.append(roll.lot_id.name)
                continue
            groups.setdefault((warehouse.id, roll.quality_grade, src.id), []).append(roll)
        released_by_picking = {}
        for (warehouse_id, grade, src_id), ok_rolls in groups.items():
            warehouse = self.env['stock.warehouse'].browse(warehouse_id)
            src = self.env['stock.location'].browse(src_id)
            dest = warehouse._get_roll_dest_location(grade)
            # Reusar la recepción PENDIENTE de la misma partida/grado/destino:
            # si aún no se validó, se agregan los rollos como líneas; si ya se
            # validó (done) o no hay, se crea una nueva.
            picking = self._find_open_release_picking(warehouse, grade, src, dest)
            if not picking:
                picking = self.env['stock.picking'].create({
                    'picking_type_id': warehouse.int_type_id.id,
                    'location_id': src.id,
                    'location_dest_id': dest.id,
                    'origin': self.name,
                    'company_id': warehouse.company_id.id,
                    'roll_release_batch_id': self.id,
                    'roll_release_grade': grade,
                    'user_id': False,
                    'note': _('Recepción de rollos grado %(grade)s de la partida %(batch)s.',
                              grade=grade, batch=self.name),
                })
            moves = {}
            for roll in ok_rolls:
                product = roll.lot_id.product_id
                move = moves.get(product.id)
                if not move:
                    # reutilizar el movimiento abierto del producto en el picking
                    move = picking.move_ids.filtered(
                        lambda m: m.product_id.id == product.id
                        and m.state not in ('done', 'cancel'))[:1]
                    if not move:
                        move = self.env['stock.move'].create({
                            'product_id': product.id,
                            'product_uom_qty': 0,
                            'product_uom': product.uom_id.id,
                            'location_id': src.id,
                            'location_dest_id': dest.id,
                            'picking_id': picking.id,
                            'picking_type_id': picking.picking_type_id.id,
                            'company_id': picking.company_id.id,
                            'origin': self.name,
                            'procure_method': 'make_to_stock',
                        })
                    moves[product.id] = move
                move.product_uom_qty += roll.net_weight
            picking.action_confirm()
            # una línea por rollo NUEVO con su lote exacto (los rollos ya
            # liberados en el mismo picking conservan sus líneas).
            for roll in ok_rolls:
                move = moves[roll.lot_id.product_id.id]
                self.env['stock.move.line'].create({
                    'move_id': move.id,
                    'picking_id': picking.id,
                    'product_id': roll.lot_id.product_id.id,
                    'product_uom_id': move.product_uom.id,
                    'lot_id': roll.lot_id.id,
                    'quantity': roll.net_weight,
                    'location_id': src.id,
                    'location_dest_id': dest.id,
                })
            # quitar las líneas auto SIN lote que crea la auto-asignación desde
            # la ubicación virtual (los rollos van con su lote exacto).
            picking.move_line_ids.filtered(lambda ml: not ml.lot_id).unlink()
            self.env['mrp.production.roll'].browse([r.id for r in ok_rolls]).write({
                'quality_released': True,
                'quality_release_date': now,
                'release_picking_id': picking.id,
            })
            pickings |= picking
            released_by_picking.setdefault(picking.id, []).extend(
                r.lot_id.name for r in ok_rolls)

        # Bitácora en la partida: qué se liberó, qué ya estaba y qué falta.
        lines = [_('%(pick)s → %(dest)s (grado %(grade)s): %(lots)s',
                   pick=p.name, dest=p.location_dest_id.display_name, grade=p.roll_release_grade,
                   lots=', '.join(released_by_picking.get(p.id, []))) for p in pickings]
        if already:
            lines.append(_('Ya estaban en su destino, dados por recibidos: %s') % ', '.join(already))
        if missing:
            lines.append(_('SIN stock disponible, no liberados: %s') % ', '.join(missing))
        self.message_post(body=Markup('<b>%s</b><br/>%s') % (
            _('Liberación a almacén'), Markup('<br/>').join(escape(l) for l in lines)))

        if missing:
            self.env['bus.bus']._sendone(self.env.user.partner_id, 'simple_notification', {
                'title': _('Rollos sin stock'),
                'message': _('No se liberaron (sin stock disponible): %s') % ', '.join(missing),
                'type': 'warning', 'sticky': True,
            })
        if not pickings:
            if already:
                return {
                    'type': 'ir.actions.client', 'tag': 'display_notification',
                    'params': {'title': _('Rollos ya en su destino'),
                               'message': _('Se dieron por recibidos: %s') % ', '.join(already),
                               'type': 'success', 'sticky': False,
                               'next': {'type': 'ir.actions.act_window_close'}},
                }
            raise UserError(_('Ningún rollo tiene stock disponible para liberar: %s')
                            % ', '.join(missing))
        action = self.env['ir.actions.act_window']._for_xml_id('stock.action_picking_tree_all')
        action['domain'] = [('id', 'in', pickings.ids)]
        if len(pickings) == 1:
            action['views'] = [(self.env.ref('stock.view_picking_form').id, 'form')]
            action['res_id'] = pickings.id
        return action

    def _find_open_release_picking(self, warehouse, grade, src, dest):
        """Recepción de rollos de esta partida/grado/destino aún NO validada
        (para agregarle más rollos); vacío si no hay o ya se validó (done)."""
        self.ensure_one()
        return self.env['stock.picking'].search([
            ('roll_release_batch_id', '=', self.id),
            ('roll_release_grade', '=', grade),
            ('picking_type_id', '=', warehouse.int_type_id.id),
            ('location_id', '=', src.id),
            ('location_dest_id', '=', dest.id),
            ('state', 'not in', ('done', 'cancel')),
        ], order='id desc', limit=1)

    def _roll_stock_location(self, roll, warehouse):
        """Ubicación ORIGEN de la recepción del rollo:
        - Flujo actual: el rollo no tiene stock → sale de la ubicación virtual
          de pesado (producción). La recepción crea el stock al validarse.
        - Rollos del flujo anterior que ya tienen quant interno (p.ej. un B en
          Existencias): sale de esa ubicación (traslado interno real)."""
        internal = self.env['stock.quant'].search([
            ('lot_id', '=', roll.lot_id.id), ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0)]).filtered(lambda q: q.available_quantity > 0)
        if internal:
            return internal[0].location_id
        return warehouse._get_roll_location('weigh')

    def action_view_release_pickings(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('stock.action_picking_tree_all')
        action['domain'] = [('roll_release_batch_id', '=', self.id)]
        action['context'] = {'create': False}
        return action

    def _print_roll_sticker(self, roll, scale, print_sticker):
        """Imprime el sticker; nunca tumba el pesado. Devuelve aviso o ''."""
        if not print_sticker:
            return ''
        printer_ip = scale.printer_ip if scale else (
            self.env.company.zpl_printer_ip if self.env.company.is_printer else False)
        if not printer_ip:
            return ''
        try:
            roll._print_zpl_to_network(roll.create_zpl(), printer_ip)
        except Exception as e:
            return _(' (sticker NO impreso: %s — usa Reimprimir)') % e
        return ''

    def action_weigh_finished_roll(self, product_id, scale_id=False, manual_weight=None,
                                   print_sticker=True, wo_roll_id=False, roll_num=False,
                                   observed=False, observation=False, note=False):
        """Pesa un rollo TERMINADO de la partida identificado por el N° de
        rollo de Acabado: crea el rollo, su lote (<partida>-NNN) y —por
        ahora— su quant inmediato. La calidad se decide aquí: CONFORME →
        grado A; OBSERVADO (motivo + detalle) → se pesa igual, sticker
        OBSERVADO y queda retenido hasta que se resuelva con repesado."""
        self.ensure_one()
        try:
            scale = self.env['scale.registry'].browse(int(scale_id)) if scale_id else False
            product = self.wo_roll_ids.mapped('product_id').filtered(
                lambda p: p.id == int(product_id))
            if not product:
                return {'status': 'danger',
                        'message': _('El producto no pertenece a los rollos de la partida.')}
            production = self.wo_roll_ids.filtered(
                lambda r: r.product_id == product).production_id[:1]
            if not production:
                return {'status': 'danger',
                        'message': _('La partida no tiene OF para el producto elegido.')}
            try:
                roll_num = int(roll_num or 0)
            except (TypeError, ValueError):
                roll_num = 0
            if roll_num <= 0:
                return {'status': 'danger', 'message': _('Indica el N° de rollo (Acabado).')}
            if observed and observation not in ('stain', 'decontaminate', 'reprocess', 'other'):
                return {'status': 'danger', 'message': _('Indica el motivo de la observación.')}

            # Rollo crudo elegido (opcional): trazabilidad y talla heredada.
            wo_roll = self.env['mrp.workorder.roll'].browse(int(wo_roll_id)) \
                if wo_roll_id else self.env['mrp.workorder.roll']
            if wo_roll and wo_roll not in self.wo_roll_ids:
                return {'status': 'danger',
                        'message': _('El rollo elegido no pertenece a la partida.')}

            peso, err = self._read_roll_weight(scale, manual_weight)
            if err:
                return {'status': 'danger', 'message': err}

            lot = self.env['stock.lot'].create(self._next_roll_lot_vals(production, roll_num))
            roll_vals = {
                'production_id': production.id,
                'batch_id': self.id,
                'lot_id': lot.id,
                'quantity': 1,
                'gross_weight': peso,
                'net_weight': peso,
                'weighed_date': fields.Datetime.now(),
                'wo_roll_id': wo_roll.id or False,
                'size_id': wo_roll.size_id.id or False,
                'roll_num': roll_num,
                'quality_user_id': self.env.uid,
                'quality_date': fields.Datetime.now(),
            }
            # Calificación previa de Calidad para este N° de rollo (grado o
            # "separar"); Pesado no elige grado: sin marca previa entra como A.
            mark = self._get_roll_hold(roll_num) or {}
            if observed or mark.get('observed'):
                roll_vals.update({
                    'quality_observation': observation if observed else mark.get('reason'),
                    'quality_note': ((note or '').strip() if observed else (mark.get('note') or '')) or False,
                })
            else:
                roll_vals['quality_grade'] = mark.get('grade') or 'A'
                if mark.get('note'):
                    roll_vals['quality_note'] = mark['note']
            roll = self.env['mrp.production.roll'].create(roll_vals)
            lot.roll_id = roll
            production._sync_qty_producing_from_production_rolls()
            self._after_weigh_finished_roll(roll)

            # El rollo pesado NO es stock todavía: queda solo como registro
            # (rollo + lote). Igual que la mercadería en una ubicación de
            # proveedor, entra a stock recién cuando almacén VALIDA el picking
            # de recepción (action_release_rolls → validar). Así un observado
            # puede volver a producción o a otra partida sin haber sido stock.
            print_warning = self._print_roll_sticker(roll, scale, print_sticker)
            if roll.quality_observation:
                msg = _('Rollo %(lot)s pesado como OBSERVADO (%(reason)s): %(peso).2f kg — separar para reproceso',
                        lot=lot.name, reason=roll._quality_observation_label(), peso=peso)
            else:
                msg = _('Rollo %(lot)s pesado: %(peso).2f kg · grado %(grade)s (partida %(batch)s)',
                        lot=lot.name, peso=peso, grade=roll.quality_grade, batch=self.name)
            return {'status': 'success', 'peso': peso, 'lot': lot.name,
                    'observed': bool(roll.quality_observation), 'grade': roll.quality_grade,
                    'message': msg + print_warning}
        except Exception as e:
            return {'status': 'danger', 'message': _('Error: %s') % e}

    def action_reweigh_roll(self, roll_id, scale_id=False, manual_weight=None,
                            print_sticker=True, note=False):
        """REPESA un rollo observado que vuelve del área de reproceso y al que
        Calidad ya dio grado final (el grado NO se elige aquí). Actualiza el
        peso, quita el pendiente de repesado, reimprime el sticker con el
        grado. El rollo sigue sin ser stock hasta la recepción de almacén."""
        self.ensure_one()
        try:
            roll = self.env['mrp.production.roll'].browse(int(roll_id))
            if not roll.exists() or roll.batch_id != self:
                return {'status': 'danger', 'message': _('El rollo no pertenece a la partida.')}
            if roll.quality_released:
                return {'status': 'danger',
                        'message': _('El rollo %s ya fue liberado a almacén.') % roll.lot_id.name}
            if not roll.reweigh_pending:
                if roll.quality_state == 'observed':
                    return {'status': 'danger', 'message': _(
                        'El rollo %s sigue observado: Calidad debe darle el grado final antes de repesarlo.'
                    ) % roll.lot_id.name}
                return {'status': 'danger',
                        'message': _('El rollo %s no está pendiente de repesado.') % roll.lot_id.name}
            scale = self.env['scale.registry'].browse(int(scale_id)) if scale_id else False
            peso, err = self._read_roll_weight(scale, manual_weight)
            if err:
                return {'status': 'danger', 'message': err}

            old_weight = roll.net_weight
            vals = {'gross_weight': peso, 'net_weight': peso, 'reweigh_pending': False,
                    'resolved_weight_date': fields.Datetime.now()}
            note = (note or '').strip()
            if note:
                vals['quality_note'] = ('%s · %s' % (roll.quality_note, note)) if roll.quality_note else note
            roll.write(vals)
            roll.production_id._sync_qty_producing_from_production_rolls()
            self._after_resolve_observed_roll(roll)

            # Sin quant que ajustar: el rollo no es stock hasta la recepción;
            # el peso repesado se usará en el picking de liberación.
            print_warning = self._print_roll_sticker(roll, scale, print_sticker)
            return {'status': 'success', 'peso': peso, 'lot': roll.lot_id.name, 'grade': roll.quality_grade,
                    'message': _('Rollo %(lot)s repesado: grado %(grade)s · %(peso).2f kg (antes %(old).2f kg)',
                                 lot=roll.lot_id.name, grade=roll.quality_grade, peso=peso,
                                 old=old_weight) + print_warning}
        except Exception as e:
            return {'status': 'danger', 'message': _('Error: %s') % e}
