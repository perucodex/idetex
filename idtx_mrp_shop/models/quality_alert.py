# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
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
    batch_qty = fields.Float(
        'Cantidad de la Partida', related='batch_id.total_weight', readonly=True)
    production_qty = fields.Float(
        'Cantidad de la OF', related='workorder_id.production_id.product_qty',
        readonly=True)
    reposition_qty = fields.Float(
        'Cantidad a Reponer',
        help='Kilos a producir en la OF de reposición. Por defecto, los kilos '
             'de la partida; editable.')

    @api.depends('workorder_id', 'workorder_id.batch_ids')
    def _compute_available_batch_ids(self):
        for rec in self:
            rec.available_batch_ids = rec.workorder_id.batch_ids

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
        return res

    @api.model_create_multi
    def create(self, vals_list):
        alerts = super().create(vals_list)
        # skip_batch_alert_trigger: alertas INFORMATIVAS creadas por código
        # (p.ej. reposición de CUELLOS desde collar.quality.check, que lleva
        # la OT de control de calidad): no deben disparar reproceso ni la OF
        # de reposición automática por kilos.
        if self.env.context.get('skip_batch_alert_trigger'):
            return alerts
        batch_ops = self.env['mrp.workorder'].BATCH_OPERATION_TYPES
        for alert in alerts:
            wo = alert.workorder_id
            if not (alert.batch_id and wo and wo.operation_type in batch_ops):
                continue
            if alert.tipo == 'reproceso':
                alert._trigger_reprocess()
            elif alert.tipo == 'reposicion':
                alert._trigger_reposition()
        return alerts

    def _trigger_reprocess(self):
        """Reabre la operación de la OT y las posteriores ya terminadas de la
        partida, y deja constancia en el hilo de la partida."""
        self.ensure_one()
        wo, batch = self.workorder_id, self.batch_id
        reopened = wo._reprocess_from_here(batch)
        detail = ', '.join(reopened.mapped(lambda w: w.mrwo_id.name or w.display_name)) or wo.mrwo_id.name
        body = Markup('<p>%s</p>') % _(
            'Reproceso disparado por la alerta de calidad %(alert)s '
            '(causa: %(reason)s). Operaciones reabiertas desde %(op)s: %(detail)s.',
            alert=self.name or self.title or '',
            reason=self.reason_id.name or _('sin especificar'),
            op=wo.mrwo_id.name or wo.display_name,
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
