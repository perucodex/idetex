# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from markupsafe import Markup


class QualityAlert(models.Model):
    _inherit = 'quality.alert'

    # La alerta de calidad es el motivo (obligatorio) de una acción sobre una
    # partida. Según `tipo`:
    #   - Reproceso: reabre esta operación y las posteriores ya terminadas de la
    #     partida ("reprocesar desde este punto hacia adelante").
    #   - Reposición: la tela está muy dañada y no se puede reprocesar; crea una
    #     OF nueva (misma data, en Borrador) que arranca desde la primera OT.
    # Reutiliza reason_id (causa raíz) + description.
    tipo = fields.Selection([
        ('reproceso', 'Reproceso'),
        ('reposicion', 'Reposición'),
    ], string='Tipo', default='reproceso', required=True,
        help='Reproceso: reabre la operación y las posteriores de la partida. '
             'Reposición: crea una OF nueva (la tela ya no se puede reprocesar).')
    batch_id = fields.Many2one(
        'mrp.workorder.batch', string='Partida',
        help='Partida sobre la que se actúa. Reproceso: se reabre desde esta '
             'operación. Reposición: se crea una OF nueva por sus kilos.')
    available_batch_ids = fields.Many2many(
        'mrp.workorder.batch', compute='_compute_available_batch_ids',
        string='Partidas de la OT')
    # Reproceso PARCIAL (JP, 18-sep-2026): rollos de la partida que van al
    # reproceso (por defecto todos). Si queda alguno fuera, al aprobar se
    # separan a una partida nueva con el mismo número ("· Reproceso N") que se
    # lleva el reproceso y esta alerta; la original sigue con el resto.
    roll_ids = fields.Many2many(
        'mrp.workorder.roll', 'quality_alert_roll_rel', 'alert_id', 'roll_id',
        string='Rollos a reprocesar',
        help='Por defecto todos los rollos de la partida. Desmarca los que no '
             'se reprocesan: al aprobar se separan los marcados a una partida de '
             'reproceso con el mismo número.')
    available_roll_ids = fields.Many2many(
        'mrp.workorder.roll', compute='_compute_available_roll_ids',
        string='Rollos de la partida')
    # Punto de inicio del reproceso. Por defecto la OT donde se crea la alerta,
    # pero puede ser una operación ANTERIOR de la misma OF (p.ej. la alerta se
    # detecta en la 8va operación y la tela debe volver desde la 2da): se
    # reabren esa y todas las posteriores que la partida ya procesó.
    reprocess_from_workorder_id = fields.Many2one(
        'mrp.workorder', string='Reprocesar desde', copy=False,
        help='Operación de la OF desde la cual la partida vuelve a procesarse. '
             'Por defecto la operación donde se crea la alerta; puede elegirse '
             'una anterior: se reabren esa y todas las posteriores que la '
             'partida ya procesó.')
    available_reprocess_workorder_ids = fields.Many2many(
        'mrp.workorder', compute='_compute_available_reprocess_workorder_ids',
        string='Operaciones reprocesables')
    batch_qty = fields.Float(
        'Cantidad de la Partida', related='batch_id.total_weight', readonly=True)
    production_qty = fields.Float(
        'Cantidad de la OF', related='workorder_id.production_id.product_qty',
        readonly=True)
    reposition_qty = fields.Float(
        'Cantidad a Reponer',
        help='Kilos a producir en la OF de reposición. Por defecto, los kilos '
             'de la partida; editable.')
    # Aprobación: el reproceso/reposición ya NO se dispara al crear la
    # alerta sino al APROBARLA (botón visible solo para los grupos
    # "Aprobar reposiciones/reprocesos" de Permisos adicionales).
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('approved', 'Aprobada'),
    ], string='Estado', default='draft', required=True, copy=False,
        tracking=True)
    reposition_production_id = fields.Many2one(
        'mrp.production', string='OF de Reposición', readonly=True,
        copy=False,
        help='Orden de fabricación creada al aprobar la reposición.')

    @api.depends('workorder_id', 'workorder_id.batch_ids')
    def _compute_available_batch_ids(self):
        for rec in self:
            rec.available_batch_ids = rec.workorder_id.batch_ids

    @api.depends('workorder_id', 'batch_id', 'batch_id.registry_ids',
                 'batch_id.parent_batch_id.registry_ids')
    def _compute_available_reprocess_workorder_ids(self):
        """Operaciones de partida de la MISMA OF que la OT de la alerta, desde
        el inicio de la ruta hasta la propia OT de la alerta (inclusive), y que
        la partida (o su linaje de partidas de origen) ya procesó. Tejeduría
        nunca entra."""
        WO = self.env['mrp.workorder']
        batch_ops = WO.BATCH_OPERATION_TYPES
        for rec in self:
            wo = rec.workorder_id
            wos = wo.production_id.workorder_ids  # en orden de ruta
            if not wo or wo not in wos:
                rec.available_reprocess_workorder_ids = WO
                continue
            upto = wos[:wos.ids.index(wo.id) + 1].filtered(
                lambda w: w.operation_type in batch_ops)
            if rec.batch_id:
                done_mrwo = rec.batch_id._get_lineage_registered_mrwo()
                upto = upto.filtered(lambda w: w == wo or w.mrwo_id in done_mrwo)
            rec.available_reprocess_workorder_ids = upto

    @api.onchange('workorder_id', 'batch_id', 'tipo')
    def _onchange_reprocess_from_workorder(self):
        """Por defecto se reprocesa desde la OT de la alerta; si la elección
        actual dejó de ser válida (cambió la partida/OT) se vuelve al default."""
        for rec in self:
            available = rec.available_reprocess_workorder_ids
            if rec.reprocess_from_workorder_id not in available:
                rec.reprocess_from_workorder_id = (
                    rec.workorder_id if rec.workorder_id in available else False)

    @api.constrains('reprocess_from_workorder_id', 'workorder_id')
    def _check_reprocess_from_workorder(self):
        batch_ops = self.env['mrp.workorder'].BATCH_OPERATION_TYPES
        for rec in self:
            start, wo = rec.reprocess_from_workorder_id, rec.workorder_id
            if not start or start == wo:
                continue
            if not wo or start.production_id != wo.production_id:
                raise ValidationError(_(
                    '"Reprocesar desde" (%(start)s) debe ser una operación de '
                    'la misma OF que la operación de la alerta (%(wo)s).',
                    start=start.display_name,
                    wo=wo.display_name if wo else '-'))
            if start.operation_type not in batch_ops:
                raise ValidationError(_(
                    'No se puede reprocesar desde %(start)s: no es una '
                    'operación de partida (teñido/acabado/estampado/calidad).',
                    start=start.display_name))

    @api.depends('batch_id', 'batch_id.wo_roll_ids')
    def _compute_available_roll_ids(self):
        for rec in self:
            rec.available_roll_ids = rec.batch_id.wo_roll_ids

    @api.onchange('batch_id')
    def _onchange_batch_rolls(self):
        """Al elegir la partida, todos sus rollos quedan marcados para reprocesar."""
        for rec in self:
            rec.roll_ids = [(6, 0, rec.batch_id.wo_roll_ids.ids)]

    def _partial_reprocess_rolls(self):
        """Rollos elegidos SI son un subconjunto estricto de la partida; vacío
        si el reproceso es de la partida completa (todos o ninguno marcado)."""
        self.ensure_one()
        rolls = self.roll_ids & self.batch_id.wo_roll_ids
        if not rolls or rolls == self.batch_id.wo_roll_ids:
            return self.env['mrp.workorder.roll']
        return rolls

    @api.onchange('batch_id', 'tipo')
    def _onchange_batch_reposition_qty(self):
        """Por defecto la cantidad a reponer = kilos de la partida (editable)."""
        for rec in self:
            if rec.batch_id and not rec.reposition_qty:
                rec.reposition_qty = rec.batch_id.total_weight

    @api.constrains('reason_id', 'tipo', 'batch_id')
    def _check_reprocess_reason(self):
        """No se puede reprocesar/reponer una partida sin causa raíz."""
        for rec in self:
            if rec.batch_id and not rec.reason_id:
                accion = 'reponer' if rec.tipo == 'reposicion' else 'reprocesar'
                raise ValidationError(_(
                    'Debes indicar la Causa Raíz para %(accion)s la partida %(batch)s.',
                    accion=accion, batch=rec.batch_id.name))

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        wo_id = res.get('workorder_id') or self.env.context.get('default_workorder_id')
        if wo_id and 'batch_id' in fields_list and not res.get('batch_id'):
            batches = self.env['mrp.workorder'].browse(wo_id).batch_ids
            # Autoselección solo si la OT procesa una única partida.
            if len(batches) == 1:
                res['batch_id'] = batches.id
        if res.get('batch_id') and 'reposition_qty' in fields_list and not res.get('reposition_qty'):
            res['reposition_qty'] = self.env['mrp.workorder.batch'].browse(res['batch_id']).total_weight
        if wo_id and 'reprocess_from_workorder_id' in fields_list and not res.get('reprocess_from_workorder_id'):
            res['reprocess_from_workorder_id'] = wo_id
        return res

    @api.model_create_multi
    def create(self, vals_list):
        alerts = super().create(vals_list)
        # skip_batch_alert_trigger: alertas INFORMATIVAS creadas por código
        # (p.ej. reposición de CUELLOS desde collar.quality.check, cuya OF
        # la crea la propia pantalla): nacen APROBADAS para que no muestren
        # el botón de aprobar ni puedan re-disparar nada.
        if self.env.context.get('skip_batch_alert_trigger'):
            alerts.write({'state': 'approved'})
        # El reproceso/reposición ya no se dispara aquí: requiere aprobación
        # explícita (action_approve) de un usuario autorizado.
        return alerts

    _APPROVE_GROUPS = {
        'reposicion': 'idtx_mrp_shop.group_quality_approve_reposition',
        'reproceso': 'idtx_mrp_shop.group_quality_approve_reprocess',
    }

    def action_approve(self):
        """Aprueba la alerta y RECIÉN ahí ejecuta la acción sobre la partida:
        reposición → crea la OF de reposición; reproceso → reabre la
        operación de la OT y las posteriores ya terminadas."""
        batch_ops = self.env['mrp.workorder'].BATCH_OPERATION_TYPES
        for alert in self:
            if alert.state != 'draft':
                raise UserError(_(
                    'La alerta %s ya está aprobada.') % (alert.name or ''))
            group = self._APPROVE_GROUPS.get(alert.tipo)
            if not group or not self.env.user.has_group(group):
                raise AccessError(_(
                    'No tienes el permiso "Aprobar %(tipo)s (alertas de '
                    'calidad)" (Permisos adicionales del usuario).',
                    tipo='reposiciones' if alert.tipo == 'reposicion'
                    else 'reprocesos'))
            wo = alert.workorder_id
            if not (alert.batch_id and wo and wo.operation_type in batch_ops):
                raise UserError(_(
                    'La alerta %s no tiene partida y OT de una operación de '
                    'partida (teñido/acabado/estampado/calidad): no hay nada '
                    'que aprobar.') % (alert.name or ''))
            start = alert._get_reprocess_start_workorder()
            if alert.tipo == 'reproceso' and start.operation_type not in batch_ops:
                raise UserError(_(
                    'La alerta %(alert)s no se puede aprobar: "Reprocesar '
                    'desde" (%(start)s) no es una operación de partida.',
                    alert=alert.name or '', start=start.display_name))
            if alert.tipo == 'reposicion':
                new = alert._trigger_reposition()
                alert.reposition_production_id = new
                body = _(
                    'Reposición APROBADA por %(user)s: se creó la OF '
                    '%(prod)s.', user=self.env.user.name, prod=new.name)
            else:
                # Reproceso PARCIAL: los rollos marcados se separan a una
                # partida nueva (mismo número · Reproceso N) que se lleva el
                # reproceso y esta alerta.
                partial = alert._partial_reprocess_rolls()
                original = alert.batch_id
                if partial:
                    new_batch = original._split_for_reprocess(partial, alert=alert)
                    alert.batch_id = new_batch
                alert._trigger_reprocess()
                body = _(
                    'Reproceso APROBADO por %(user)s: se reabrieron las '
                    'operaciones de la partida %(batch)s desde %(op)s.',
                    user=self.env.user.name, batch=alert.batch_id.display_name,
                    op=start.mrwo_id.name or start.display_name)
                if partial:
                    body += _(' Reproceso parcial: %(n)s rollo(s) separados de %(orig)s.',
                              n=len(partial), orig=original.display_name)
            alert.state = 'approved'
            alert.message_post(body=Markup('<p>%s</p>') % body)
        return True

    def _get_reprocess_start_workorder(self):
        """OT desde la que arranca el reproceso: la elegida en "Reprocesar
        desde" o, por defecto, la OT donde se creó la alerta."""
        self.ensure_one()
        return self.reprocess_from_workorder_id or self.workorder_id

    def _trigger_reprocess(self):
        """Reabre la operación de inicio (por defecto la OT de la alerta; puede
        ser una anterior de la ruta) y las posteriores que la partida ya
        procesó, y deja constancia en el hilo de la partida."""
        self.ensure_one()
        wo, batch = self.workorder_id, self.batch_id
        start = self._get_reprocess_start_workorder()
        reopened = start._reprocess_from_here(batch)
        detail = ', '.join(reopened.mapped(lambda w: w.mrwo_id.name or w.display_name)) or start.mrwo_id.name
        if start != wo:
            origin = _(', detectada en %(wo)s', wo=wo.mrwo_id.name or wo.display_name)
        else:
            origin = ''
        body = Markup('<p>%s</p>') % _(
            'Reproceso disparado por la alerta de calidad %(alert)s '
            '(causa: %(reason)s%(origin)s). Operaciones reabiertas desde '
            '%(op)s: %(detail)s.',
            alert=self.name or self.title or '',
            reason=self.reason_id.name or _('sin especificar'),
            origin=origin,
            op=start.mrwo_id.name or start.display_name,
            detail=detail,
        )
        batch.message_post(body=body)

    def _trigger_reposition(self):
        """Crea una OF de reposición (tela dañada que no se puede reprocesar):
        misma data, en Borrador, desde la primera OT, enlazada a la OF de origen
        y a la línea de venta (que pasa a apuntar a la nueva OF)."""
        self.ensure_one()
        wo, batch = self.workorder_id, self.batch_id
        production = wo.production_id
        qty = self.reposition_qty or batch.total_weight or production.product_qty
        return production._create_reposition(batch, qty, alert=self)
