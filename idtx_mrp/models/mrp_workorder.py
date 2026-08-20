import math
import re

from odoo import _, models, fields, api
from odoo.exceptions import UserError

# Mapea el nombre del centro de trabajo REAL (de la OT, p.ej. de FULL PIMA)
# al departamento HR donde viven las máquinas (de IDETEX). Se usa departamento
# en vez de mrp.workcenter porque un equipo de IDETEX no puede apuntar al
# centro de trabajo de otra compañía sin romper check_company — ver
# [[project_workcenter_check_company]]. Departamento sí es único (no hay
# copias homónimas por compañía), así que no hace falta crear ni tocar
# ningún mrp.workcenter para este emparejamiento.
_WORKCENTER_DEPT_KEYWORDS = {
    'TEJEDURIA':  ['TEJED', 'TEJID'],
    'TINTORERIA': ['TINTOR', 'TINTE'],
}


def _department_ids_for_workcenter_name(env, wc_name):
    """IDs de hr.department cuyo nombre coincide con el área de "wc_name"
    (p.ej. "TEJEDURIA" -> departamento "Tejeduría")."""
    kws = _WORKCENTER_DEPT_KEYWORDS.get((wc_name or '').upper(), [])
    if not kws:
        return []
    Dept = env['hr.department'].sudo()
    dept_ids = set()
    for kw in kws:
        dept_ids.update(Dept.search([('name', 'ilike', kw)]).ids)
    return list(dept_ids)


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    mrwo_id = fields.Many2one('mrp.routing.workcenter.operation', string='Operation LAB')
    operation_type = fields.Selection(related='mrwo_id.operation_type')
    roll_ids = fields.One2many('mrp.workorder.roll', 'workorder_id', string='Weaving Rolls')
    batch_ids = fields.Many2many('mrp.workorder.batch', string='Batchs')
    equipment_ids = fields.Many2many('maintenance.equipment', string='Equipments')
    option_ids = fields.One2many('mrp.workorder.option', 'workorder_id', string='Options')

    # --- Estimación de tiempo de tejido (TEJIDO CRUDO) ---
    estimated_rate_kg_h = fields.Float(
        'Producción Estimada (kg/h)', compute='_compute_weaving_aggregate',
        digits=(16, 2),
        help="Suma de la producción estimada de todas las máquinas de las opciones (corren en paralelo).")
    estimated_roll_count = fields.Integer(
        'Rollos Estimados', compute='_compute_weaving_aggregate',
        help="Cantidad de rollos = techo(kg a producir / peso estimado por rollo de la OT).")
    weaving_estimate_warning = fields.Char(
        'Aviso de Estimación', compute='_compute_weaving_aggregate',
        help="Motivo por el que no se pudo estimar la duración (datos faltantes).")
    produced_roll_count = fields.Integer(
        'Cantidad de rollos producidos', compute='_compute_produced_roll_count',
        help="Rollos que cuentan como producción de esta OT (excluye los "
             "transferidos a otra OT).")

    @api.depends('roll_ids', 'roll_ids.transfer_state')
    def _compute_produced_roll_count(self):
        for wo in self:
            wo.produced_roll_count = len(wo.roll_ids.filtered(
                lambda r: r.transfer_state != 'transferido'))

    # Planificación de rollos: peso estimado por rollo (editable) y la cantidad
    # de rollos a producir que se deriva de él (kilos a producir / peso, techo).
    estimated_weight_per_roll = fields.Float(
        'Peso Estimado por Rollo', digits=(16, 2),
        compute='_compute_estimated_weight_per_roll', store=True, readonly=False,
        help="Peso estimado de cada rollo (kg). Editable; se inicializa con el "
             "valor de la configuración de la empresa. Base para la cantidad de "
             "rollos a producir.")
    rolls_to_produce_summary = fields.Char(
        'Cantidad de Rollos a Producir',
        compute='_compute_rolls_to_produce_summary',
        help="Rollos completos del peso estimado más un rollo final con el "
             "sobrante (kilos a producir ÷ peso estimado). Ej.: 500 kg / 22 kg "
             "= 22 rollos de 22 kg + 1 rollo de 16 kg.")
    rolls_pending_message = fields.Char(
        'Rollos Pendientes', compute='_compute_rolls_pending_message',
        help="Rollos que faltan por tejer (plan menos los ya tejidos), "
             "indicando el rollo del sobrante si aún falta.")

    @api.depends('company_id')
    def _compute_estimated_weight_per_roll(self):
        # Editable-computado: inicializa desde la config de la empresa; una vez
        # con valor (por defecto o editado por el usuario) no lo pisa.
        for wo in self:
            if not wo.estimated_weight_per_roll:
                wo.estimated_weight_per_roll = (
                    wo.company_id.weaving_weight_per_roll or 0.0)

    @api.depends('qty_production', 'estimated_weight_per_roll', 'operation_type')
    def _compute_rolls_to_produce_summary(self):
        # Composición de rollos a tejer: N rollos COMPLETOS del peso estimado y
        # un último rollo con el sobrante (no se redondea el peso hacia arriba;
        # el resto va en un rollo más pequeño).
        for wo in self:
            summary = ''
            peso = wo.estimated_weight_per_roll
            qty = wo.qty_production or 0.0
            if wo.operation_type == 'weaving' and peso > 0 and qty > 0:
                full = int(qty // peso)
                remainder = qty - full * peso
                peso_s = '%.2f' % peso
                if remainder < 1e-6:
                    summary = _('%(n)s rollos de %(w)s kg', n=full, w=peso_s)
                elif full == 0:
                    summary = _('1 rollo de %(r)s kg', r='%.2f' % remainder)
                else:
                    summary = _('%(n)s rollos de %(w)s kg + 1 rollo de %(r)s kg',
                                n=full, w=peso_s, r='%.2f' % remainder)
            wo.rolls_to_produce_summary = summary

    @api.depends('qty_production', 'estimated_weight_per_roll', 'operation_type',
                 'roll_ids', 'roll_ids.transfer_state')
    def _compute_rolls_pending_message(self):
        # Rollos que faltan = plan (rollos completos + rollo del sobrante) menos
        # los ya tejidos (produced_roll_count, que descuenta transferidos).
        for wo in self:
            msg = ''
            peso = wo.estimated_weight_per_roll
            qty = wo.qty_production or 0.0
            if wo.operation_type == 'weaving' and peso > 0 and qty > 0:
                full = int(qty // peso)
                remainder = qty - full * peso
                has_rem = remainder > 1e-6
                planned_total = full + (1 if has_rem else 0)
                woven = wo.produced_roll_count
                pending = planned_total - woven
                if pending <= 0:
                    extra = woven - planned_total
                    if extra > 0:
                        msg = _(
                            'Producción de rollos completa: %(w)s tejidos '
                            '(%(e)s adicional(es) sobre los %(p)s planificados).',
                            w=woven, e=extra, p=planned_total)
                    else:
                        msg = _(
                            'Producción de rollos completa: se tejieron los '
                            '%(p)s rollos planificados.', p=planned_total)
                else:
                    remaining_full = max(0, full - woven)
                    parts = []
                    if remaining_full > 0:
                        unidad = _('rollo') if remaining_full == 1 else _('rollos')
                        parts.append('%(n)s %(u)s de %(w)s kg' % {
                            'n': remaining_full, 'u': unidad, 'w': '%.2f' % peso})
                    if has_rem:
                        parts.append(_('1 rollo de %(r)s kg', r='%.2f' % remainder))
                    msg = _(
                        'Faltan por tejer %(detail)s (de %(p)s planificados, '
                        '%(w)s ya tejidos).',
                        detail=' + '.join(parts), p=planned_total, w=woven)
            wo.rolls_pending_message = msg

    # ------------------------------------------------------------------
    # Cálculo de tiempo de tejido de punto en máquinas circulares.
    # Producción por CONSUMO DE HILO (no necesita pasadas/cm ni gramaje):
    #   tex_fibra = cabos * 590.5 / Ne   (título Ne del maestro de hilados)
    #   g/vuelta  = N(agujas) * F(alimentadores) * Σ_fibras(long_malla_mm * tex / 1e6)
    #   kg/h (1 máq) = RPM * eficiencia * g/vuelta * 60 / 1000
    #   tiempo(min)  = kg_totales / Σ(kg/h de cada máquina) * 60
    # long_malla viene de la ficha técnica (analysis.fiber.length, mm); el
    # título/cabos del hilo viene del producto de hilo (fiber.product_template_id,
    # campos thread_titulo_id/thread_cabos_id de idtx_thread_codigo).
    # weave_type (tubular/open) NO afecta el peso tejido por vuelta.
    # Nota: se asume sistema Ne (algodón); hilos filamento (denier) no se cubren.
    # ------------------------------------------------------------------
    def _get_weaving_analysis(self):
        """Ficha técnica (product.analysis) del producto de la OT, o recordset
        vacío. Acceso defensivo: no rompe si idtx_product_development no está."""
        self.ensure_one()
        if 'product.analysis' not in self.env:
            return None
        Analysis = self.env['product.analysis']
        tmpl = self.product_id.product_tmpl_id
        if tmpl and 'analysis_id' in tmpl._fields and tmpl.analysis_id:
            return tmpl.analysis_id
        return Analysis.browse()

    @api.model
    def _first_int(self, value):
        """Primer entero contenido en un texto ('030'->30, '30/1'->30)."""
        if value is None:
            return 0
        m = re.search(r'\d+', str(value))
        return int(m.group()) if m else 0

    def _fiber_tex(self, fiber):
        """Densidad lineal del hilo de la fibra en tex (g/1000 m).
        Título (Ne, algodón) y cabos desde el producto de hilo: tex = cabos*590.5/Ne."""
        tmpl = fiber.product_template_id
        if not tmpl or 'thread_titulo_id' not in tmpl._fields:
            return 0.0
        titulo = tmpl.thread_titulo_id
        ne = self._first_int(titulo.code or titulo.name) if titulo else 0
        if ne <= 0:
            return 0.0
        plies = self._first_int(tmpl.thread_cabos_id.code) if tmpl.thread_cabos_id else 0
        return (plies or 1) * 590.5 / ne

    def _weaving_g_per_revolution(self, analysis):
        """Gramos de tela tejidos por una vuelta completa de la máquina."""
        if not analysis:
            return 0.0
        N = analysis.needles or 0
        F = analysis.feeders or 0
        if not (N and F):
            return 0.0
        wdata = analysis.weaving_data_ids[:1]
        if not wdata:
            return 0.0
        g_per_loop = 0.0
        for fiber in wdata.fiber_ids:
            sl_mm = fiber.length or 0.0
            tex = self._fiber_tex(fiber)
            if sl_mm > 0 and tex > 0:
                g_per_loop += sl_mm * tex / 1.0e6
        return N * F * g_per_loop

    @api.depends('operation_type', 'qty_production',
                 'option_ids', 'option_ids.estimated_rate_kg_h',
                 'option_ids.weaving_estimate_warning',
                 'estimated_weight_per_roll')
    def _compute_weaving_aggregate(self):
        for wo in self:
            wo.estimated_rate_kg_h = 0.0
            wo.estimated_roll_count = 0
            wo.weaving_estimate_warning = False
            if wo.operation_type != 'weaving':
                continue
            wo.estimated_rate_kg_h = sum(wo.option_ids.mapped('estimated_rate_kg_h'))
            # Cantidad de rollos = techo(kg a producir / peso estimado por rollo
            # de la OT), no de la configuración de la empresa.
            per_roll = wo.estimated_weight_per_roll or 0.0
            qty = wo.qty_production or 0.0
            if per_roll > 0 and qty > 0:
                wo.estimated_roll_count = int(math.ceil(qty / per_roll))
            warnings = [w for w in wo.option_ids.mapped('weaving_estimate_warning') if w]
            if not wo.option_ids:
                wo.weaving_estimate_warning = _("Crea una opción con máquinas para estimar el tiempo.")
            elif warnings:
                wo.weaving_estimate_warning = warnings[0]

    @api.depends('operation_id', 'workcenter_id', 'qty_producing', 'qty_production',
                 'operation_type', 'option_ids', 'option_ids.estimated_rate_kg_h')
    def _compute_duration_expected(self):
        # Comportamiento estándar para todas (capacidad de la operación, etc.).
        super()._compute_duration_expected()
        # Para tejido, sobreescribimos con la estimación por producción cuando
        # hay un ritmo calculable; si no, queda el valor estándar.
        for wo in self.filtered(lambda w: w.operation_type == 'weaving' and w.state not in ('done', 'cancel')):
            rate = sum(wo.option_ids.mapped('estimated_rate_kg_h'))
            qty = wo.qty_production or 0.0
            if rate > 0 and qty > 0:
                wo.duration_expected = qty / rate * 60.0

    @api.onchange('mrwo_id')
    def _onchange_mrwo_id(self):
        for rec in self:
            rec.workcenter_id = rec.mrwo_id.workcenter_id
            rec.name = rec.mrwo_id.name

    # Operaciones que procesan PARTIDAS (no rollos sueltos): su cantidad
    # producida es el peso de los rollos de sus partidas que pertenecen a
    # la propia OF (las partidas pueden combinar rollos de varias OFs).
    BATCH_OPERATION_TYPES = ('dyeing', 'finishing', 'printing', 'quality')

    def _get_textile_rolls(self):
        """Rollos ACTUALES que esta operación de partida cuenta como
        procesados. Fuente ÚNICA usada por `_get_textile_produced_qty` (cantidad
        producida) y por `_compute_progress` (% de avance) para que no diverjan.

        - Resuelve divisiones: una partida dividida ya no tiene rollos propios
          sino en sus sub-partidas -> `origin_roll_ids` (propios + descendientes).
        - El union de recordset DEDUPLICA: si están anexadas la partida madre y
          una sub-partida, el rollo no se cuenta dos veces; un reproceso (misma
          partida re-registrada) no suma de más (solo el estado actual).
        - EXCLUYE partidas con reproceso PENDIENTE en esta operación: aún no
          fueron (re)producidas aquí, así el avance baja al reabrir y se
          recupera al re-registrar. Guarda de campo para no romper idtx_mrp
          instalado sin idtx_mrp_shop.
        - Filtra a los rollos de la propia OF (las partidas pueden combinar
          rollos de varias OFs).
        """
        self.ensure_one()
        rolls = self.env['mrp.workorder.roll']
        for batch in self.batch_ids:
            if (self.mrwo_id and 'pending_reprocess_mrwo_ids' in batch._fields
                    and self.mrwo_id in batch.pending_reprocess_mrwo_ids):
                continue
            rolls |= batch.origin_roll_ids
        return rolls.filtered(
            lambda roll: roll.workorder_id and roll.workorder_id.production_id == self.production_id)

    def _get_textile_produced_qty(self):
        self.ensure_one()
        if self.operation_type == 'weaving':
            # AVANCE/producción = salida de esta OT: EXCLUYE los TRANSFERIDOS
            # (el origen ya no los produce, se fueron a otra OT) e INCLUYE los
            # RECIBIDOS (el destino sí los produce). El consumo va al revés.
            weaving_rolls = self.roll_ids.filtered(lambda r: r.transfer_state != 'transferido')
            if getattr(self, 'weave_type', False) == 'rect':
                return float(sum(weaving_rolls.mapped('quantity')))
            total_weight = float(sum(weaving_rolls.mapped('gross_weight')))
            return total_weight or float(sum(weaving_rolls.mapped('quantity')))
        if self.operation_type in self.BATCH_OPERATION_TYPES:
            batch_rolls = self._get_textile_rolls()
            total_weight = float(sum(batch_rolls.mapped('gross_weight')))
            if total_weight > 0:
                return total_weight
            return float(sum(batch_rolls.mapped('quantity')))
        return 0.0

    def _sync_textile_qty_produced(self):
        for workorder in self.filtered(lambda wo: wo.operation_type in (('weaving',) + wo.BATCH_OPERATION_TYPES) and wo.state not in ('done', 'cancel')):
            workorder.qty_produced = workorder._get_textile_produced_qty()

    def write(self, vals):
        # Máquinas de las OTs de TEJIDO cuyo estado cambia: se resincronizan
        # tras el write (ejecutando <-> operativa según OTs en progreso). Cubre
        # los cambios de estado que no pasan por button_start/button_finish.
        equipos_a_resync = self.env['maintenance.equipment']
        if 'state' in vals:
            equipos_a_resync = self.filtered(
                lambda wo: wo.workcenter_id.operation_type == 'weaving'
            ).option_ids.equipment_ids
        # El core aborta el write si llega qty_produced sobre una OT ya cerrada.
        # Pasa al guardar el formulario de una OT terminada (reenvía el campo) y
        # al reabrir OTs por reproceso (contexto skip_textile_qty): en ambos
        # casos el valor es irrelevante, así que se descarta en vez de romper.
        skip_qty = self.env.context.get('skip_textile_qty')
        if 'qty_produced' in vals:
            cerradas = self.filtered(lambda wo: wo.state in ('done', 'cancel'))
            if cerradas:
                vals_sin_qty = {k: v for k, v in vals.items() if k != 'qty_produced'}
                abiertas = self - cerradas
                res = super(MrpWorkorder, cerradas).write(vals_sin_qty)
                if abiertas:
                    res = abiertas.write(vals) and res
                if equipos_a_resync:
                    self._resync_equipment_state(equipos_a_resync)
                return res
        if (not skip_qty and 'state' in vals
                and vals['state'] in ('progress', 'done')
                and self.filtered(lambda wo: wo.operation_type in (('weaving',) + wo.BATCH_OPERATION_TYPES))):
            result = True
            for workorder in self:
                current_vals = dict(vals)
                produced_qty = workorder._get_textile_produced_qty()
                # Solo se inyecta en OTs que aún se pueden tocar: en una OT ya
                # cerrada el core rechazaría el campo.
                if (produced_qty > 0 and workorder.state not in ('done', 'cancel')
                        and (vals['state'] == 'done' or 'qty_produced' not in current_vals)):
                    current_vals['qty_produced'] = produced_qty
                result = super(MrpWorkorder, workorder).write(current_vals) and result
        else:
            result = super().write(vals)

        if 'state' in vals:
            equipos_a_resync = self.filtered(
                lambda wo: wo.workcenter_id.operation_type == 'weaving'
            ).option_ids.equipment_ids
            if equipos_a_resync:
                self._resync_equipment_state(equipos_a_resync)
        return result

    def unlink(self):
        for rec in self:
            if rec.state in ('done','progress'):
                raise UserError(_('You can\'t delete a workorder in state %s') % dict(rec._fields['state'].selection).get(rec.state, rec.state))
        return super().unlink()
    
    def button_reopen(self):
        self.ensure_one()
        return self._do_reopen()

    def _do_reopen(self):
        """Reabre la(s) OT(s): borra el descanso registrado, las vuelve a
        'progress' y limpia la fecha de fin. Reutilizable tanto por el botón
        manual (button_reopen) como por el reproceso 'hacia adelante' que
        dispara la alerta de calidad (idtx_mrp_shop)."""
        # skip_textile_qty: al reabrir NO se debe inyectar qty_produced (core
        # prohíbe cambiar la cantidad producida mientras la OT sigue en 'done');
        # la cantidad se recalcula sola cuando la partida se vuelve a registrar.
        for wo in self:
            wo.leave_id.unlink()
            wo.with_context(skip_textile_qty=True).write({
                'state': 'progress',
                'date_finished': False,
            })
        return True
    
    def button_start(self, raise_on_invalid_state=False):
        for wo in self:
            if wo.workcenter_id.operation_type == 'weaving':
                if not wo.option_ids:
                    raise UserError(_('Please create at least one option before starting the workorder.'))
                invalid_options = wo.option_ids.filtered(lambda opt: not opt.employee_ids or not opt.equipment_ids)
                if invalid_options:
                    raise UserError(_('All options must have assigned employees and equipments before starting.'))
                # La orden de trabajo debe estar enlazada a máquinas de su misma
                # área (mismo departamento, p. ej. Tejeduría) y que estén
                # OPERATIVAS: no se puede iniciar con máquinas de otra área ni
                # en otro estado (apagada, malograda, mantenimiento, ejecutando).
                # Se compara por DEPARTAMENTO (no por centro de trabajo) porque
                # las máquinas son de IDETEX y la OT puede ser de otra compañía
                # — ver [[project_workcenter_check_company]].
                all_equipment = wo.option_ids.equipment_ids
                wc_name = wo.workcenter_id.name
                dept_ids = _department_ids_for_workcenter_name(self.env, wc_name)
                wrong_wc = all_equipment.filtered(
                    lambda e: not e.department_id or e.department_id.id not in dept_ids
                )
                if wrong_wc:
                    raise UserError(_(
                        'No se puede iniciar: las siguientes máquinas no pertenecen '
                        'al área "%(wc)s": %(maqs)s',
                        wc=wc_name or '—',
                        maqs=', '.join(wrong_wc.mapped('name')),
                    ))
                not_operativa = all_equipment.filtered(lambda e: e.machine_state != 'operativa')
                if not_operativa:
                    estados = dict(
                        self.env['maintenance.equipment']._fields['machine_state'].selection
                    )
                    detalle = ', '.join(
                        '%s (%s)' % (e.name, estados.get(e.machine_state, e.machine_state or '—'))
                        for e in not_operativa
                    )
                    raise UserError(_(
                        'No se puede iniciar: solo se permiten máquinas en estado '
                        'OPERATIVA. Máquinas no operativas: %s', detalle))
        res = super().button_start(raise_on_invalid_state=raise_on_invalid_state)
        self._set_equipment_running(True)
        self._purge_zero_duration_times()
        return res

    def button_finish(self):
        # El hilo se consume al cerrar TEJIDO (es donde se gasta en la máquina).
        # Si el cierre viene de la liquidación de hilo, allí ya se decidió qué
        # bolsas se usaron, qué volvió a 2da y cuánto fue merma.
        tejido = self.filtered(lambda wo: wo.operation_type == 'weaving')
        res = super().button_finish()
        self._set_equipment_running(False)
        self._purge_zero_duration_times()
        if tejido and not self.env.context.get('skip_weaving_thread_consume'):
            tejido.production_id._consume_woven_thread()
        return res

    def _purge_zero_duration_times(self):
        """Elimina registros de 'Seguimiento de tiempo' VACÍOS (0 min reales:
        date_start == date_end). El flujo estándar de Odoo, al arrancar el
        cronómetro de tejido, crea de más un registro cerrado de duración 0
        (probablemente por el inverse `_set_duration` con un delta ínfimo que,
        tras truncar microsegundos, queda en 0), que se veía como una línea
        DUPLICADA junto al registro real. Un registro de 0 min no aporta a la
        duración total, así que borrarlo no altera el tiempo real registrado.
        Solo se aplica a OT de tejido y nunca toca un cronómetro ABIERTO
        (date_end vacío)."""
        for wo in self.filtered(lambda w: w.workcenter_id.operation_type == 'weaving'):
            phantom = wo.time_ids.filtered(
                lambda t: t.date_start and t.date_end
                and (t.date_end - t.date_start).total_seconds() < 1
            )
            if phantom:
                phantom.sudo().unlink()

    def _set_equipment_running(self, running):
        """Sincroniza el estado de las máquinas de tejido con la ejecución de la OT:
        al INICIAR pasan de 'operativa' a 'ejecutando'; al TERMINAR vuelven de
        'ejecutando' a 'operativa'. No pisa estados manuales (malograda,
        mantenimiento, apagada). Se usa sudo porque el equipo puede ser de otra
        compañía que la OT."""
        for wo in self:
            if wo.workcenter_id.operation_type != 'weaving':
                continue
            equipos = wo.option_ids.equipment_ids.sudo()
            if not equipos:
                continue
            if running:
                equipos.filtered(lambda e: e.machine_state == 'operativa').write(
                    {'machine_state': 'ejecutando'})
            else:
                equipos.filtered(lambda e: e.machine_state == 'ejecutando').write(
                    {'machine_state': 'operativa'})

    @api.model
    def _resync_equipment_state(self, equipos):
        """Recalcula el estado de un conjunto de máquinas de tejido según la
        realidad actual: una máquina está 'ejecutando' si y solo si sigue
        enlazada a al menos una orden de trabajo de tejido EN PROGRESO; en caso
        contrario vuelve a 'operativa'. No pisa los estados fijados a mano
        (malograda, mantenimiento, apagada). Es idempotente, así que puede
        llamarse tras cualquier cambio de asignación de máquinas (quitar/añadir
        equipos en una opción, borrar opciones, etc.). Se usa sudo porque los
        equipos pueden pertenecer a otra compañía que la OT."""
        equipos = equipos.sudo()
        if not equipos:
            return
        Workorder = self.env['mrp.workorder'].sudo()
        for eq in equipos:
            # Solo se autogestiona el par operativa/ejecutando; un estado puesto
            # manualmente (malograda, mantenimiento, apagada) no se toca.
            if eq.machine_state not in ('operativa', 'ejecutando'):
                continue
            en_uso = Workorder.search_count([
                ('state', '=', 'progress'),
                ('workcenter_id.operation_type', '=', 'weaving'),
                ('option_ids.equipment_ids', 'in', eq.id),
            ]) > 0
            objetivo = 'ejecutando' if en_uso else 'operativa'
            if eq.machine_state != objetivo:
                eq.write({'machine_state': objetivo})

class MrpWorkorderOption(models.Model):
    _name = 'mrp.workorder.option'
    _description = 'Workorder Option'

    name = fields.Char('Name')
    workorder_id = fields.Many2one('mrp.workorder', string='Workorder')
    workcenter_id = fields.Many2one(related='workorder_id.workcenter_id', string='Workcenter')
    notes = fields.Text('Notes')
    employee_ids = fields.Many2many('hr.employee', string='Employees')
    equipment_ids = fields.Many2many('maintenance.equipment', string='Equipments')
    option_line_ids = fields.One2many('mrp.workorder.option.line', 'option_id', string='Option Lines')
    available_thread_product_ids = fields.Many2many(
        'product.product',
        compute='_compute_available_thread_products',
        string='Available Thread Products'
    )
    # Máquinas seleccionables: solo las OPERATIVAS del mismo área (mismo
    # departamento, p.ej. Tejeduría) que la orden de trabajo. Se empareja por
    # departamento (no por centro de trabajo) porque las máquinas son de
    # IDETEX y la OT puede ser de otra compañía — ver
    # [[project_workcenter_check_company]].
    available_equipment_ids = fields.Many2many(
        'maintenance.equipment',
        relation='mrp_wo_option_avail_equipment_rel',
        column1='option_id', column2='equipment_id',
        compute='_compute_available_equipment',
        string='Máquinas Disponibles',
    )

    # --- Estimación de tejido por opción ---
    estimated_rate_kg_h = fields.Float(
        'Producción Estimada (kg/h)', compute='_compute_weaving_estimate', digits=(16, 2),
        help="Producción estimada de esta opción (suma de sus máquinas).")
    weight_per_rev_g = fields.Float(
        'Peso por Vuelta (g)', compute='_compute_weaving_estimate', digits=(16, 4),
        help="Gramos de tela tejidos por una vuelta de la máquina, según la ficha técnica.")
    weaving_estimate_warning = fields.Char(
        'Aviso de Estimación', compute='_compute_weaving_estimate')

    # Nota: NO se puede depender de `...product_tmpl_id.analysis_id` porque
    # idtx_mrp carga antes que idtx_product_development (que define analysis_id).
    # El campo es no-almacenado: se recalcula al leerlo, así que basta con
    # depender del producto y de las máquinas/eficiencia.
    @api.depends('equipment_ids', 'equipment_ids.rpm', 'equipment_ids.efficiency',
                 'workorder_id.operation_type', 'workorder_id.product_id',
                 'workorder_id.company_id.weaving_default_efficiency')
    def _compute_weaving_estimate(self):
        for opt in self:
            opt.estimated_rate_kg_h = 0.0
            opt.weight_per_rev_g = 0.0
            opt.weaving_estimate_warning = False
            wo = opt.workorder_id
            if not wo or wo.operation_type != 'weaving':
                continue
            analysis = wo._get_weaving_analysis()
            if not analysis:
                opt.weaving_estimate_warning = _("Sin ficha técnica (análisis) en el producto.")
                continue
            g_rev = wo._weaving_g_per_revolution(analysis)
            if g_rev <= 0:
                opt.weaving_estimate_warning = _("Faltan agujas/alimentadores o datos de hilo en la ficha.")
                continue
            opt.weight_per_rev_g = g_rev
            company = wo.company_id or self.env.company
            default_eff = company.weaving_default_efficiency or 0.0
            rate = 0.0
            machine_without_rpm = False
            for eq in opt.equipment_ids:
                rpm = eq.rpm or 0.0
                if rpm <= 0:
                    machine_without_rpm = True
                    continue
                eff_pct = eq.efficiency if eq.efficiency > 0 else default_eff
                eff = (eff_pct or 0.0) / 100.0
                rate += rpm * eff * g_rev * 60.0 / 1000.0
            opt.estimated_rate_kg_h = rate
            if rate <= 0:
                opt.weaving_estimate_warning = (
                    _("Asigna máquinas con RPM configurado.") if opt.equipment_ids
                    else _("Sin máquinas asignadas."))
            elif machine_without_rpm:
                opt.weaving_estimate_warning = _("Alguna máquina no tiene RPM; no se cuenta en el cálculo.")

    @api.model
    def default_get(self, fields):
        """Cargar líneas con productos is_thread al abrir el formulario"""
        res = super().default_get(fields)
        
        # Si viene workorder_id del contexto o está en los valores por defecto
        workorder_id = res.get('workorder_id') or self.env.context.get('default_workorder_id')
        
        if workorder_id and 'option_line_ids' in fields:
            workorder = self.env['mrp.workorder'].browse(workorder_id)
            if workorder and workorder.production_id:
                production = workorder.production_id
                bom = production.bom_id
                
                if bom:
                    # Obtener componentes del BOM que sean is_thread
                    thread_components = bom.bom_line_ids.filtered(
                        lambda l: l.product_id.product_tmpl_id.is_thread
                    )
                    
                    # Preparar las líneas con formato de one2many (0, 0, {...})
                    lines = []
                    for bom_line in thread_components:
                        lines.append((0, 0, {
                            'product_id': bom_line.product_id.id,
                        }))
                    
                    if lines:
                        res['option_line_ids'] = lines
        
        return res

    @api.depends('workorder_id', 'workorder_id.production_id', 'workorder_id.production_id.bom_id')
    def _compute_available_thread_products(self):
        """Calcular productos is_thread disponibles del BOM de la producción"""
        for record in self:
            if record.workorder_id and record.workorder_id.production_id:
                production = record.workorder_id.production_id
                bom = production.bom_id
                
                if bom:
                    # Obtener componentes del BOM que sean is_thread
                    thread_components = bom.bom_line_ids.filtered(
                        lambda l: l.product_id.product_tmpl_id.is_thread
                    )
                    record.available_thread_product_ids = thread_components.product_id
                else:
                    record.available_thread_product_ids = False
            else:
                record.available_thread_product_ids = False

    @api.depends('workorder_id', 'workorder_id.workcenter_id',
                 'workorder_id.workcenter_id.name')
    def _compute_available_equipment(self):
        """Máquinas OPERATIVAS del mismo área (departamento) que la OT."""
        Equipment = self.env['maintenance.equipment']
        for opt in self:
            wc = opt.workorder_id.workcenter_id
            dept_ids = _department_ids_for_workcenter_name(self.env, wc.name) if wc else []
            if dept_ids:
                opt.available_equipment_ids = Equipment.search([
                    ('active', '=', True),
                    ('department_id', 'in', dept_ids),
                    ('machine_state', '=', 'operativa'),
                ])
            else:
                opt.available_equipment_ids = Equipment.browse()

    @api.model_create_multi
    def create(self, vals_list):
        options = super().create(vals_list)
        # Si se crea una opción CON máquinas sobre una OT de tejido que ya está
        # EN PROGRESO, esas máquinas deben reflejar 'ejecutando'.
        afectadas = options.filtered(
            lambda o: o.equipment_ids
            and o.workorder_id.state == 'progress'
            and o.workorder_id.workcenter_id.operation_type == 'weaving'
        ).equipment_ids
        if afectadas:
            self.env['mrp.workorder']._resync_equipment_state(afectadas)
        return options

    def write(self, vals):
        # Al cambiar las máquinas asignadas hay que resincronizar el estado de
        # las máquinas QUITADAS (vuelven a 'operativa' si ya no las usa ninguna
        # OT en progreso) y de las AÑADIDAS (pasan a 'ejecutando' si la OT está
        # en progreso). Sin esto, quitar una máquina de una OT en curso la dejaba
        # colgada en 'ejecutando'.
        if 'equipment_ids' not in vals:
            return super().write(vals)
        afectadas = self.equipment_ids            # máquinas ANTES del cambio
        res = super().write(vals)
        afectadas |= self.equipment_ids           # ∪ máquinas DESPUÉS del cambio
        self.env['mrp.workorder']._resync_equipment_state(afectadas)
        return res

    def unlink(self):
        for rec in self:
            if any(roll.option_id == rec for roll in rec.workorder_id.roll_ids):
                raise UserError(_('You can\'t delete options of a workorder used in any roll'))
        # Al borrar opciones, sus máquinas deben resincronizarse: si ya no las
        # usa ninguna OT en progreso, vuelven a 'operativa'.
        afectadas = self.equipment_ids
        res = super().unlink()
        self.env['mrp.workorder']._resync_equipment_state(afectadas)
        return res

    @api.constrains('option_line_ids', 'workorder_id')
    def _check_option_lines_complete_unique(self):
        for record in self:
            if not record.workorder_id:
                continue
            required_products = set(record.available_thread_product_ids.ids)
            line_products = set(record.option_line_ids.mapped('product_id').ids)
            if required_products and line_products != required_products:
                missing = required_products - line_products
                extra = line_products - required_products
                if missing:
                    missing_names = self.env['product.product'].browse(list(missing)).mapped('display_name')
                    raise UserError(_(
                        'Missing required thread products: %s'
                    ) % ', '.join(missing_names))
                if extra:
                    extra_names = self.env['product.product'].browse(list(extra)).mapped('display_name')
                    raise UserError(_(
                        'Extra products not allowed: %s'
                    ) % ', '.join(extra_names))

            # Ensure all lines have product and lot
            incomplete = record.option_line_ids.filtered(lambda l: not l.product_id or not l.lot_id)
            if incomplete:
                raise UserError(_('All option lines must have product and lot.'))

            # # Build combination set for this option
            # combo = frozenset((line.product_id.id, line.lot_id.id) for line in record.option_line_ids)

            # # Disallow duplicate combos within the same option
            # if len(combo) != len(record.option_line_ids):
            #     raise UserError(_('Duplicate product/lot pairs are not allowed in the same option.'))

            # # Disallow duplicate combos across options in the same workorder
            # other_options = record.workorder_id.option_ids - record
            # for other in other_options:
            #     other_lines = other.option_line_ids.filtered(lambda l: l.product_id and l.lot_id)
            #     other_combo = frozenset((l.product_id.id, l.lot_id.id) for l in other_lines)
            #     if combo and combo == other_combo:
            #         raise UserError(_('An option with the same product/lot combination already exists.'))
    
class MrpWorkorderOptionLine(models.Model):
    _name = 'mrp.workorder.option.line'
    _description = 'Workorder Option Line'

    option_id = fields.Many2one('mrp.workorder.option', string='Option')
    product_id = fields.Many2one('product.product', string='Product')
    lot_id = fields.Many2one('stock.lot', string='Lot')
    available_lot_ids = fields.Many2many(
        'stock.lot',
        compute='_compute_available_lots',
        string='Available Lots'
    )
    
    @api.onchange('product_id')
    def _onchange_product_id(self):
        """Limpiar lot_id cuando cambia el producto"""
        if self.product_id and self.lot_id:
            if self.lot_id.product_id != self.product_id:
                self.lot_id = False
    
    @api.constrains('product_id', 'lot_id')
    def _check_lot_product_match(self):
        """Validar que el lote corresponda al producto seleccionado"""
        for record in self:
            if record.lot_id and record.product_id:
                if record.lot_id.product_id != record.product_id:
                    raise UserError(
                        _("The selected lot '%s' does not match the product '%s'") 
                        % (record.lot_id.name, record.product_id.name)
                    )
    
    @api.depends(
        'product_id',
        'option_id.workorder_id',
        'option_id.workorder_id.production_id',
        'option_id.workorder_id.production_id.move_raw_ids.move_line_ids.lot_id'
    )
    def _compute_available_lots(self):
        """Lotes disponibles segun producto y produccion del workorder."""
        for record in self:
            if not record.product_id:
                record.available_lot_ids = False
                continue
            workorder = record.option_id.workorder_id
            if not workorder or not workorder.production_id:
                record.available_lot_ids = False
                continue
            production = workorder.production_id
            lots = production.move_raw_ids.filtered(
                lambda m: m.product_id == record.product_id
            ).move_line_ids.lot_id
            record.available_lot_ids = lots