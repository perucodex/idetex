from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class CollarQualityCheck(models.Model):
    """Control de cuellos y puños (formato papel FULL-SGCC-FO-01).

    Por ROLLO rectilíneo de la partida (que ya trae talla y cantidad desde
    tejeduría) se miden ancho/alto, se cuentan defectos y se clasifica la
    cantidad tejida en 1ras y 2das (el resto es descarte). Las 1ras
    acumuladas de la OF por talla se comparan con las unidades del pedido
    (sale.order.line.size): si faltan, se genera/actualiza una alerta de
    calidad de tipo Reposición (informativa: SIN workorder para no disparar
    la OF automática de tela)."""
    _name = 'collar.quality.check'
    _description = 'Control de Cuellos y Puños'
    _inherit = ['mail.thread']
    _order = 'id desc'

    name = fields.Char(
        'Número', readonly=True, copy=False, default=lambda self: _('Nuevo'))
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('reviewed', 'Revisado'),
    ], string='Estado', default='draft', required=True, copy=False,
        tracking=True)
    # Decisión del auditor cuando hay faltantes: la alerta de reposición (y
    # la eventual OF que salga de ella) solo se genera si aquí dice Sí.
    replenish = fields.Selection([
        ('yes', 'Sí, solicitar reposición'),
        ('no', 'No solicitar'),
    ], string='¿Reposición?', copy=False, tracking=True)
    batch_id = fields.Many2one(
        'mrp.workorder.batch', string='Partida', required=True, index=True)
    available_roll_ids = fields.Many2many(
        'mrp.workorder.roll', compute='_compute_available_rolls',
        string='Rollos Elegibles')
    roll_id = fields.Many2one(
        'mrp.workorder.roll', string='Rollo', required=True,
        ondelete='restrict', tracking=True)
    size_id = fields.Many2one(
        related='roll_id.size_id', string='Talla', store=True)
    qty_total = fields.Integer(
        related='roll_id.quantity', string='Cantidad del Rollo')
    production_id = fields.Many2one(
        related='roll_id.workorder_id.production_id', string='OF', store=True)
    # La línea de venta pertenece a OTRA compañía (la comercial, p.ej.
    # IDETEX) por diseño: se muestra solo su referencia, leída con sudo —
    # un m2o directo revienta con las reglas multiempresa de sale.order.line.
    sale_order_ref = fields.Char(
        'Pedido', compute='_compute_sale_order_ref')

    def _compute_sale_order_ref(self):
        for rec in self:
            sl = rec.production_id.sudo().sale_order_line_id
            rec.sale_order_ref = sl.order_id.name or '' if sl else ''
    check_date = fields.Date(
        'Fecha', default=fields.Date.context_today, required=True)
    user_id = fields.Many2one(
        'res.users', 'Auditor', default=lambda self: self.env.user,
        required=True)

    qty_first = fields.Integer('1ras', tracking=True)
    # 2das = suma de los defectos contados (cada unidad defectuosa es una 2da).
    qty_second = fields.Integer(
        '2das', compute='_compute_qty_second', store=True, tracking=True,
        help='Suma de los defectos contados (F/Aguja + Manchas + Huecos + '
             'Quebraduras + Mordedura).')
    qty_discard = fields.Integer(
        'Descarte', compute='_compute_qty_discard', store=True,
        help='Tejidas del rollo que no pasan a terminado '
             '(cantidad del rollo − 1ras − 2das).')

    # Medidas (formato papel: requerido STD ± tolerancia + 3 muestras, cm).
    # Requerido se precarga de la talla; la TOLERANCIA viene de la ficha
    # técnica (technical.size.line.length_tol/width_tol) y no se edita aquí.
    width_req = fields.Float('Largo Requerido (STD)')
    width_tol = fields.Float(
        related='roll_id.size_id.length_tol', string='Tol. Largo (±)')
    width_1 = fields.Float('Largo Obtenido 1')
    width_2 = fields.Float('Largo Obtenido 2')
    width_3 = fields.Float('Largo Obtenido 3')
    height_req = fields.Float('Alto Requerido (STD)')
    height_tol = fields.Float(
        related='roll_id.size_id.width_tol', string='Tol. Alto (±)')
    height_1 = fields.Float('Alto Obtenido 1')
    height_2 = fields.Float('Alto Obtenido 2')
    height_3 = fields.Float('Alto Obtenido 3')
    measure_warning = fields.Text(
        'Fuera de Tolerancia', compute='_compute_measure_warning')

    # Defectos (conteo de unidades por tipo, como el formato papel)
    defect_needle = fields.Integer('F/Aguja')
    defect_stain = fields.Integer('Manchas')
    defect_hole = fields.Integer('Huecos')
    defect_crack = fields.Integer('Quebraduras')
    defect_bite = fields.Integer('Mordedura')
    comment = fields.Text('Comentarios')

    # Comparación con el pedido (unidades por talla del sale.order.line.size)
    required_qty = fields.Integer(
        'Requerido (Pedido)', compute='_compute_shortage',
        help='Unidades solicitadas de esta talla en la línea del pedido.')
    first_total = fields.Integer(
        '1ras Acumuladas', compute='_compute_shortage',
        help='1ras de TODOS los rollos chequeados de la misma OF y talla.')
    shortage_qty = fields.Integer(
        'Faltante', compute='_compute_shortage',
        help='Requerido − 1ras acumuladas (si es positivo, falta reposición).')
    alert_id = fields.Many2one(
        'quality.alert', string='Alerta de Reposición', readonly=True,
        copy=False)

    _sql_constraints = [
        ('roll_uniq', 'unique(roll_id)',
         'Este rollo ya tiene un control de calidad registrado (edítalo en '
         'lugar de crear otro).'),
    ]

    @api.depends('name', 'batch_id', 'roll_id', 'size_id')
    def _compute_display_name(self):
        for rec in self:
            parts = [rec.name or '', rec.batch_id.name or '',
                     rec.roll_id.name or '']
            if rec.size_id:
                parts.append(rec.size_id.size or '')
            rec.display_name = ' · '.join(p for p in parts if p) or _('Nuevo')

    @api.depends('defect_needle', 'defect_stain', 'defect_hole',
                 'defect_crack', 'defect_bite')
    def _compute_qty_second(self):
        for rec in self:
            rec.qty_second = (rec.defect_needle or 0) + (rec.defect_stain or 0) \
                + (rec.defect_hole or 0) + (rec.defect_crack or 0) \
                + (rec.defect_bite or 0)

    @api.depends('width_req', 'width_tol', 'width_1', 'width_2', 'width_3',
                 'height_req', 'height_tol', 'height_1', 'height_2', 'height_3')
    def _compute_measure_warning(self):
        """Avisa qué muestras quedaron fuera de requerido ± tolerancia (solo
        compara cuando hay requerido y tolerancia definidos en la ficha)."""
        for rec in self:
            issues = []
            for label, req, tol, samples in (
                (_('Largo'), rec.width_req, rec.width_tol,
                 (rec.width_1, rec.width_2, rec.width_3)),
                (_('Alto'), rec.height_req, rec.height_tol,
                 (rec.height_1, rec.height_2, rec.height_3)),
            ):
                if not req or not tol:
                    continue
                for i, value in enumerate(samples, start=1):
                    if value and abs(value - req) > tol:
                        issues.append(_(
                            '%(m)s obtenido %(n)s = %(v).2f fuera de '
                            '%(req).2f ± %(tol).2f',
                            m=label, n=i, v=value, req=req, tol=tol))
            rec.measure_warning = '\n'.join(issues)

    @api.depends('batch_id.wo_roll_ids')
    def _compute_available_rolls(self):
        """Rollos rectilíneos (con talla) de la partida aún sin chequear."""
        for rec in self:
            rolls = rec.batch_id.wo_roll_ids.filtered('size_id')
            checked = self.search(
                [('roll_id', 'in', rolls.ids), ('id', '!=', rec._origin.id)])
            rec.available_roll_ids = rolls - checked.roll_id

    @api.depends('qty_total', 'qty_first', 'qty_second')
    def _compute_qty_discard(self):
        for rec in self:
            rec.qty_discard = (rec.qty_total or 0) - (rec.qty_first or 0) \
                - (rec.qty_second or 0)

    @api.constrains('qty_first', 'qty_second')
    def _check_quantities(self):
        for rec in self:
            if rec.qty_first < 0 or rec.qty_second < 0:
                raise ValidationError(_('1ras y 2das no pueden ser negativas.'))
            if rec.qty_first + rec.qty_second > rec.qty_total:
                raise ValidationError(_(
                    '1ras (%(f)s) + 2das (%(s)s) superan la cantidad del '
                    'rollo %(roll)s (%(t)s).',
                    f=rec.qty_first, s=rec.qty_second,
                    roll=rec.roll_id.name, t=rec.qty_total))

    @api.onchange('batch_id')
    def _onchange_batch_id(self):
        for rec in self:
            if rec.roll_id and rec.roll_id not in rec.available_roll_ids:
                rec.roll_id = False

    @api.onchange('roll_id')
    def _onchange_roll_id(self):
        """Precarga el requerido de medidas desde la talla de la ficha
        técnica (Largo → Ancho, Alto → Alto)."""
        for rec in self:
            size = rec.roll_id.size_id
            if size and not rec.width_req:
                rec.width_req = size.length
            if size and not rec.height_req:
                rec.height_req = size.width

    def _same_group_checks(self):
        """Chequeos de la misma OF y talla (incluye self)."""
        self.ensure_one()
        return self.search([
            ('production_id', '=', self.production_id.id),
            ('size_id', '=', self.size_id.id),
        ])

    @api.depends('size_id', 'production_id', 'qty_first')
    def _compute_shortage(self):
        for rec in self:
            size_name = (rec.size_id.size or '').strip().upper()
            # sudo: la línea de venta es de la compañía comercial (regla
            # multiempresa la oculta al usuario de la productora); aquí solo
            # se LEEN las unidades por talla.
            sale_line = rec.production_id.sudo().sale_order_line_id
            required = sum(
                l.product_qty for l in sale_line.size_qty_ids
                if (l.size or '').strip().upper() == size_name)
            siblings = rec._same_group_checks() if rec.production_id else rec.browse()
            first_total = sum((siblings - rec).mapped('qty_first')) \
                + (rec.qty_first or 0)
            rec.required_qty = required
            rec.first_total = first_total
            rec.shortage_qty = max(0, required - first_total)

    # ------------------------------------------------------------------
    # Alerta de reposición: se crea/actualiza al guardar si faltan 1ras.
    # Informativa (sin workorder_id): NO dispara la OF automática de tela.
    # ------------------------------------------------------------------
    def _sync_replenishment_alert(self):
        Alert = self.env['quality.alert']
        for rec in self:
            if not rec.production_id or not rec.size_id or not rec.required_qty:
                continue
            title = _('Reposición cuellos %(of)s talla %(size)s',
                      of=rec.production_id.name, size=rec.size_id.size or '')
            existing = rec.alert_id or Alert.search(
                [('title', '=', title)], limit=1)
            if rec.shortage_qty <= 0:
                continue
            description = _(
                'Partida %(batch)s · OF %(of)s · Talla %(size)s: el pedido '
                'requiere %(req)s unidades y solo hay %(first)s de 1ras '
                'acumuladas en los rollos chequeados. FALTAN %(short)s '
                'unidades: solicitar reposición.',
                batch=rec.batch_id.name, of=rec.production_id.name,
                size=rec.size_id.size or '', req=rec.required_qty,
                first=rec.first_total, short=rec.shortage_qty)
            # OT de CONTROL DE CALIDAD de la OF (donde se hace este control);
            # fallback: la OT de tejido del rollo. La alerta se crea con
            # skip_batch_alert_trigger porque 'quality' SÍ está en
            # BATCH_OPERATION_TYPES y sin el flag dispararía la OF de
            # reposición automática por kilos (flujo de telas).
            alert_wo = rec.production_id.workorder_ids.filtered(
                lambda w: w.operation_type == 'quality')[:1] \
                or rec.roll_id.workorder_id
            extra = {
                'tipo': 'reposicion',
                'batch_id': rec.batch_id.id,
                'product_tmpl_id': rec.production_id.product_id.product_tmpl_id.id,
                'workorder_id': alert_wo.id,
                # La compañía de la OF (productora): sin esto, el check
                # multiempresa rechaza la alerta si el entorno corre en otra.
                'company_id': rec.production_id.company_id.id,
            }
            if 'workcenter_id' in Alert._fields and alert_wo.workcenter_id:
                extra['workcenter_id'] = alert_wo.workcenter_id.id
            if existing:
                # Backfill: alertas creadas antes pueden no traer OT/partida/
                # tipo — se completan sin pisar lo definido. La OT/centro se
                # corrigen también si quedaron apuntando a tejido (versión
                # anterior de este flujo).
                update_vals = {'description': description}
                for field_name, value in extra.items():
                    if not existing[field_name]:
                        update_vals[field_name] = value
                if existing.workorder_id and \
                        existing.workorder_id.operation_type == 'weaving' \
                        and alert_wo.operation_type == 'quality':
                    update_vals['workorder_id'] = alert_wo.id
                    if 'workcenter_id' in Alert._fields and alert_wo.workcenter_id:
                        update_vals['workcenter_id'] = alert_wo.workcenter_id.id
                existing.write(update_vals)
                rec.alert_id = existing
            else:
                reason = self.env['quality.reason'].search(
                    [('name', '=', 'Cuellos 1ras insuficientes')], limit=1)
                if not reason:
                    reason = self.env['quality.reason'].create(
                        {'name': 'Cuellos 1ras insuficientes'})
                rec.alert_id = Alert.with_context(
                    skip_batch_alert_trigger=True).create(dict(
                        extra, title=title, description=description,
                        reason_id=reason.id))
                rec.message_post(body=_(
                    'Alerta de reposición creada: %s') % title)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == _('Nuevo'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'collar.quality.check') or _('Nuevo')
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Flujo: Borrador → (Revisar: calcula y exige decidir reposición si
    # hay faltantes) → Revisado. La alerta SOLO se crea al revisar con
    # reposición = Sí — nunca automáticamente al guardar.
    # ------------------------------------------------------------------
    def action_review(self):
        for rec in self:
            if rec.state != 'draft':
                continue
            if rec.shortage_qty > 0 and not rec.replenish:
                raise ValidationError(_(
                    'Faltan %(short)s unidades talla %(size)s contra el '
                    'pedido: antes de revisar debes decidir si habrá '
                    'reposición (campo "¿Reposición?").',
                    short=rec.shortage_qty, size=rec.size_id.size or ''))
            if rec.shortage_qty > 0 and rec.replenish == 'yes':
                rec._sync_replenishment_alert()
            rec.state = 'reviewed'

    def action_reset_draft(self):
        self.write({'state': 'draft'})
