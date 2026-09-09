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

    @api.depends('wo_roll_ids.thread_lot_ids', 'color_recipe_id',
                 'color_recipe_id.recipe_lot_ids.lot_ids',
                 'color_recipe_id.recipe_lot_ids.state')
    def _compute_allowed_recipe_lot_ids(self):
        Sub = self.env['color.recipe.lot']
        for batch in self:
            subs = batch.color_recipe_id.recipe_lot_ids.filtered(
                lambda r: r.state == 'validated')
            lots = batch.wo_roll_ids.thread_lot_ids
            if lots:
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
        return super().write(vals)

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
        help='Cantidad de ejecuciones de operación sobre la partida que fueron '
             'reprocesos (2ª vez o más de una misma operación).')
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
            if not recipe:
                msgs.append(_(
                    'No hay receta de color aprobada para la combinación de '
                    'producto(s) %(products)s de la partida: se debe '
                    'desarrollar/aprobar en laboratorio.',
                    products=' + '.join(batch_products.mapped('name'))))
            else:
                uncovered = batch_products - recipe.product_ids
                if uncovered:
                    msgs.append(_(
                        'La receta %(recipe)s no cubre lo(s) producto(s) '
                        '%(products)s de la partida: se requiere una receta '
                        'aprobada para esa combinación de productos.',
                        recipe=recipe.name,
                        products=', '.join(uncovered.mapped('name'))))
            no_lots = rolls.filtered(lambda r: not r.thread_lot_ids)
            if no_lots:
                msgs.append(_(
                    'Rollos sin lotes de hilo registrados: %s. No se puede '
                    'verificar la receta de su combinación de lotes.')
                    % ', '.join(no_lots.mapped('name')))
            lots = rolls.thread_lot_ids
            if recipe and lots:
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
            partners = rec.wo_roll_ids.workorder_id.production_id.sale_order_line_id.order_id.mapped('partner_id')
            rec.partner_ids = [(6, 0, partners.ids)] if partners else [(5, 0, 0)]

    @api.depends('wo_roll_ids', 'child_batch_ids.wo_roll_ids',
                 'wo_roll_ids.workorder_id.production_id.color_recipe_id',
                 'wo_roll_ids.workorder_id.production_id.manual_lab_dev_line_id')
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
            productions = rolls.workorder_id.production_id
            # Color: del Lab Dip del pedido; si no, de la receta de la OF; si
            # no, el color elegido a mano en una OF libre (muestra/piloto).
            line = (productions.sale_order_line_id.lab_dev_line_id
                    or productions.color_recipe_id.lab_dev_line_id
                    or productions.manual_lab_dev_line_id)[:1]
            products = rolls.mapped('product_id')
            recipe = self.env['color.recipe']
            if line and products:
                candidates = line.color_recipe_ids.filtered(
                    lambda r: r.state == 'approved'
                    and not (products - r.product_ids))
                exact = candidates.filtered(
                    lambda r: r._product_key() == tuple(sorted(products.ids)))
                recipe = (exact or candidates.sorted(
                    key=lambda r: (len(r.product_ids), r.id)))[:1]
            if not recipe:
                # Fallback legado: la receta resuelta en las OFs.
                recipe = productions.color_recipe_id[:1]
            rec.color_recipe_id = recipe

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

    @api.depends('registry_ids.reprocess_number')
    def _compute_reprocess_count(self):
        for rec in self:
            rec.reprocess_count = len(
                rec.registry_ids.filtered(lambda r: r.reprocess_number > 1))

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

    def _get_process_tree(self):
        """Árbol genealógico de los procesos (OTs) de la partida según las OFs
        de sus rollos. Mientras las rutas coinciden operación-a-operación es un
        tramo COMPARTIDO (banda con todas las OFs + operaciones); en cuanto
        divergen se ramifica (columnas lado a lado), recursivo, hasta la
        cabecera por OF. Devuelve el nodo raíz anidado:
        {'ofs': [nombres], 'ops': [operaciones], 'branches': [nodos hijos]}."""
        self.ensure_one()
        productions = self.origin_roll_ids.workorder_id.production_id
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
        rolls = self.wo_roll_ids or self.child_batch_ids.wo_roll_ids
        recipe = self.color_recipe_id
        sub = self.recipe_lot_id
        kilos = sum(rolls.mapped('gross_weight'))
        rb = (sub.bath_ratio if sub else 0) or (recipe.bath_ratio if recipe else 0) \
            or (recipe.lab_dev_line_id.bath_ratio if recipe and recipe.lab_dev_line_id else 0)
        fac_abs = (sub.absorption_factor if sub else 0.0) \
            or (recipe.absorption_factor if recipe else 0.0)
        volume = kilos * rb
        products, total_meters = [], 0.0
        for tmpl in rolls.mapped('product_id'):
            p_rolls = rolls.filtered(lambda r: r.product_id == tmpl)
            p_kilos = sum(p_rolls.mapped('gross_weight'))
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
            'productions': rolls.workorder_id.production_id,
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
                foreign = (rec.wo_roll_ids.workorder_id.production_id
                           - caller_production)
                if foreign:
                    warning = _(
                        "Contiene rollos fabricados en otra OF: %s"
                    ) % ", ".join(foreign.mapped("name"))

            res.append({
                "id": rec.id,
                "name": rec.name or "",
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

    def _next_roll_lot_vals(self, production):
        """Lote del rollo terminado: nombre de la partida + correlativo por
        PARTIDA (a diferencia del viejo wizard, que numeraba por OF y podía
        repetir nombre con partidas multi-OF). Salta nombres ya usados."""
        self.ensure_one()
        Lot = self.env['stock.lot']
        n = self.env['mrp.production.roll'].search_count(
            [('batch_id', '=', self.id)]) + 1
        while True:
            name = '%s-%s' % (self.name, str(n).zfill(3))
            if not Lot.search_count([('name', '=', name),
                                     ('product_id', '=', production.product_id.id)]):
                return {'name': name, 'product_id': production.product_id.id}
            n += 1

    def action_weigh_finished_roll(self, product_id, scale_id=False, manual_weight=None,
                                   print_sticker=True, wo_roll_id=False):
        """Pesa un rollo TERMINADO de la partida: crea el rollo con su lote
        (partida+correlativo) y su QUANT de inmediato (modo inventario) — el
        stock ya no nace del botón Producir de la OF. Imprime el sticker en
        la impresora de la balanza (fallback: impresora de la compañía).
        El peso llega del diálogo (balanza en vivo o manual autorizado); si
        no llega, se relee del servidor de la balanza (modo IP)."""
        self.ensure_one()
        try:
            scale = self.env['scale.registry'].browse(int(scale_id)) if scale_id else False
            product = self.wo_roll_ids.mapped('product_id').filtered(
                lambda p: p.id == int(product_id))
            if not product:
                return {'status': 'danger',
                        'message': _('El producto no pertenece a los rollos de la partida.')}
            production = self.wo_roll_ids.filtered(
                lambda r: r.product_id == product).workorder_id.production_id[:1]
            if not production:
                return {'status': 'danger',
                        'message': _('La partida no tiene OF para el producto elegido.')}

            # Rollo crudo elegido (opcional): trazabilidad y talla heredada.
            wo_roll = self.env['mrp.workorder.roll'].browse(int(wo_roll_id)) \
                if wo_roll_id else self.env['mrp.workorder.roll']
            if wo_roll and wo_roll not in self.wo_roll_ids:
                return {'status': 'danger',
                        'message': _('El rollo elegido no pertenece a la partida.')}

            peso = None
            if manual_weight not in (None, False, ''):
                peso = round(float(manual_weight), 2)
            if peso is None:
                if not scale or not scale.ip:
                    return {'status': 'danger',
                            'message': _('Sin balanza seleccionada ni peso válido.')}
                resp = requests.get('http://%s:5001/peso' % scale.ip, timeout=3)
                resp.raise_for_status()
                data = resp.json()
                if data.get('ok') and data.get('peso') is not None:
                    peso = round(float(data['peso']), 2)
                else:
                    return {'status': 'danger',
                            'message': _('Sin comunicación con la balanza.')}
            if not peso or peso <= 0:
                return {'status': 'danger',
                        'message': _('No se obtuvo un peso válido.')}

            lot = self.env['stock.lot'].create(self._next_roll_lot_vals(production))
            roll = self.env['mrp.production.roll'].create({
                'production_id': production.id,
                'batch_id': self.id,
                'lot_id': lot.id,
                'quantity': 1,
                'gross_weight': peso,
                'net_weight': peso,
                'weighed_date': fields.Datetime.now(),
                'wo_roll_id': wo_roll.id or False,
                'size_id': wo_roll.size_id.id or False,
            })
            lot.roll_id = roll
            production._sync_qty_producing_from_production_rolls()

            # Quant INMEDIATO en modo inventario (mismo patrón que
            # idtx_stock_quant_import): el rollo pesado ya es stock.
            quant = self.env['stock.quant'].create({
                'product_id': production.product_id.id,
                'location_id': production.location_dest_id.id,
                'inventory_quantity': peso,
                'lot_id': lot.id,
            })
            quant.action_apply_inventory()

            # El sticker no puede tumbar el pesado: rollo/lote/quant ya
            # existen. SIN fallback entre impresoras (pedido de JP): con
            # balanza se usa SOLO su impresora — si falla, sale el aviso y se
            # Reimprime — así el pesado no se cuelga esperando timeouts. Sin
            # balanza (modo manual) se usa la de la compañía. print_sticker
            # False = pruebas sin gastar etiquetas (checkbox en modo dev).
            print_warning = ''
            if print_sticker:
                printer_ip = scale.printer_ip if scale else (
                    self.env.company.zpl_printer_ip if self.env.company.is_printer else False)
                if printer_ip:
                    try:
                        roll._print_zpl_to_network(roll.create_zpl(), printer_ip)
                    except Exception as e:
                        print_warning = _(' (sticker NO impreso: %s — usa Reimprimir)') % e

            return {'status': 'success', 'peso': peso, 'lot': lot.name,
                    'message': _('Rollo %(lot)s pesado: %(peso).2f kg (partida %(batch)s)',
                                 lot=lot.name, peso=peso, batch=self.name) + print_warning}
        except Exception as e:
            return {'status': 'danger', 'message': _('Error: %s') % e}
