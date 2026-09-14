# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.fields import Command
from odoo.exceptions import UserError
from odoo.tools import float_compare


class MrpRollReception(models.Model):
    """Recepción de rollos CRUDOS que envía el cliente para una OF de SERVICIO
    sin operación de tejido. Una recepción = una entrega (guía de remisión).
    Al confirmar crea los rollos como mrp.workorder.roll (origen 'customer',
    sin OT, colgados de la OF) y desde ahí siguen el flujo normal: partida,
    teñido/acabado, pesado del terminado (que es donde nace el stock)."""
    _name = 'mrp.roll.reception'
    _description = 'Recepción de rollos del cliente'
    _inherit = ['mail.thread']
    _order = 'received_date desc, id desc'

    name = fields.Char('Número', readonly=True, copy=False, default=lambda self: _('Nuevo'))
    production_id = fields.Many2one(
        'mrp.production', string='Orden de Fabricación', required=True, ondelete='restrict',
        index=True, tracking=True,
        domain="[('production_type', '=', 'service'), ('state', 'in', ('confirmed', 'progress', 'to_close'))]")
    company_id = fields.Many2one(related='production_id.company_id', store=True)
    product_tmpl_id = fields.Many2one(related='production_id.product_tmpl_id', string='Producto')
    production_qty = fields.Float(related='production_id.product_qty', string='Cantidad de la OF')
    production_uom_id = fields.Many2one(related='production_id.product_uom_id')
    # Dueño de la tela. Se propone desde la OF cuando el módulo de ventas
    # textil está instalado (mrp.production.partner_id); si no, se elige.
    partner_id = fields.Many2one(
        'res.partner', string='Cliente', required=True, compute='_compute_partner_id',
        store=True, readonly=False, precompute=True, tracking=True)
    guide_number = fields.Char('Guía de remisión', required=True, tracking=True)
    guide_date = fields.Date('Fecha de guía')
    carrier = fields.Char('Transportista')
    plate = fields.Char('Placa')
    received_date = fields.Datetime('Fecha de recepción', default=fields.Datetime.now, required=True)
    received_by_id = fields.Many2one('hr.employee', string='Recibido por')
    note = fields.Text('Observaciones')
    line_ids = fields.One2many('mrp.roll.reception.line', 'reception_id', string='Rollos', copy=True)
    roll_ids = fields.One2many('mrp.workorder.roll', 'reception_id', string='Rollos creados')
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('received', 'Recibida'),
        ('cancel', 'Cancelada'),
    ], default='draft', required=True, tracking=True, index=True)
    declared_qty = fields.Integer('Rollos', compute='_compute_totals')
    declared_weight = fields.Float('Kg según guía', compute='_compute_totals')
    received_weight = fields.Float('Kg en planta', compute='_compute_totals')
    weight_diff = fields.Float('Diferencia', compute='_compute_totals')
    production_received_weight = fields.Float('Kg acumulados en la OF', compute='_compute_totals')
    qty_warning = fields.Char(compute='_compute_totals')
    # Ayuda: la guía suele traer solo el total -> N filas con peso promedio.
    generate_count = fields.Integer('Rollos a generar')
    generate_weight = fields.Float('Peso promedio (kg)')
    generate_ref_start = fields.Char(
        'Ref. inicial del cliente',
        help='Referencia del cliente del primer rollo generado, p.ej. A1; las '
             'siguientes filas continúan A2, A3... (se incrementa el número final). '
             'Vacío deja las referencias en blanco.')

    @api.depends('production_id')
    def _compute_partner_id(self):
        for rec in self:
            prod = rec.production_id
            partner = prod.partner_id if prod and 'partner_id' in prod._fields else False
            rec.partner_id = partner or rec.partner_id

    @api.depends('line_ids.declared_weight', 'line_ids.gross_weight', 'production_id',
                 'state', 'roll_ids.gross_weight')
    def _compute_totals(self):
        for rec in self:
            lines = rec.line_ids
            rec.declared_qty = len(lines)
            rec.declared_weight = sum(lines.mapped('declared_weight'))
            if rec.state == 'received':
                rec.received_weight = sum(rec.roll_ids.mapped('gross_weight'))
            else:
                rec.received_weight = sum(l.gross_weight or l.declared_weight for l in lines)
            rec.weight_diff = rec.received_weight - rec.declared_weight
            prod = rec.production_id
            others = prod.wo_roll_ids.filtered(
                lambda r: r.origin == 'customer' and r.reception_id != rec) if prod else prod.wo_roll_ids
            total = sum(others.mapped('gross_weight')) + (rec.received_weight if rec.state != 'cancel' else 0.0)
            rec.production_received_weight = total
            warning = False
            if prod and prod.product_qty:
                tol = (prod.company_id.roll_reception_tolerance or 0.0) / 100.0
                if float_compare(total, prod.product_qty * (1 + tol), precision_digits=2) > 0:
                    warning = _(
                        'Los kilos recibidos en la OF (%(total).2f) superan su cantidad (%(qty).2f%(tol)s).',
                        total=total, qty=prod.product_qty,
                        tol=(_(' más %g%% de tolerancia') % (tol * 100)) if tol else '')
            rec.qty_warning = warning

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name') or vals['name'] == _('Nuevo'):
                company = vals.get('company_id')
                if not company and vals.get('production_id'):
                    company = self.env['mrp.production'].browse(vals['production_id']).company_id.id
                vals['name'] = self.env['ir.sequence'].with_company(company).next_by_code(
                    'mrp.roll.reception') or _('Nuevo')
        return super().create(vals_list)

    def unlink(self):
        if any(rec.state == 'received' for rec in self):
            raise UserError(_('Una recepción recibida no se elimina: cancélala primero.'))
        return super().unlink()

    # ------------------------------------------------------------------
    def action_confirm(self):
        """Crea los rollos crudos del cliente y deja la recepción en Recibida."""
        Roll = self.env['mrp.workorder.roll']
        created = Roll
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('La recepción %s ya fue procesada.') % rec.name)
            prod = rec.production_id
            if prod.state in ('draft', 'cancel', 'done'):
                raise UserError(_('La OF %s debe estar confirmada o en progreso para recibir rollos.') % prod.name)
            lines = rec.line_ids.sorted(lambda l: (l.sequence, l.id))
            if not lines:
                raise UserError(_('Agrega al menos un rollo.'))
            refs = [l.customer_roll_ref.strip() for l in lines if l.customer_roll_ref and l.customer_roll_ref.strip()]
            dups = sorted({r for r in refs if refs.count(r) > 1})
            if dups:
                raise UserError(_('Referencias de cliente repetidas en la recepción: %s') % ', '.join(dups))
            base_seq = len(prod.wo_roll_ids)
            vals_list = []
            for i, line in enumerate(lines, 1):
                weight = line.gross_weight or line.declared_weight
                if float_compare(weight, 0.0, precision_digits=2) <= 0:
                    raise UserError(_('El rollo %s no tiene peso.') % (line.customer_roll_ref or i))
                vals_list.append({
                    'production_id': prod.id,
                    'workorder_id': False,
                    'origin': 'customer',
                    'reception_id': rec.id,
                    'partner_id': rec.partner_id.id,
                    'customer_roll_ref': (line.customer_roll_ref or '').strip() or False,
                    'declared_weight': line.declared_weight,
                    'gross_weight': weight,
                    'net_weight': weight,
                    'location_note': line.location_note,
                    'reception_note': line.reception_note,
                    'employee_id': rec.received_by_id.id,
                    'roll_start': rec.received_date,
                    'roll_end': rec.received_date,
                    'sequence': base_seq + i,
                })
            rolls = Roll.with_context(skip_roll_option_check=True).create(vals_list)
            for line, roll in zip(lines, rolls):
                line.roll_id = roll
            rec.state = 'received'
            prod.message_post(body=_(
                'Recepción %(name)s (guía %(guide)s): %(n)s rollos del cliente, %(kg).2f kg.',
                name=rec.name, guide=rec.guide_number, n=len(rolls),
                kg=sum(rolls.mapped('gross_weight'))))
            created |= rolls
        # La impresión es un paso aparte (botón "Imprimir stickers"); al recibir
        # se cierra el diálogo y listo (JP, 10-sep-2026).
        return {'type': 'ir.actions.act_window_close'}

    def action_cancel(self):
        """Cancela la recepción y elimina sus rollos. No se permite si algún
        rollo ya se usó en una partida que NO está en borrador (JP, 10-sep-2026):
        una partida en borrador todavía no es un proceso real, así que solo se
        le quita el rollo. Tampoco si el rollo ya fue pesado (terminado) o
        transferido a otra OT, porque hay datos aguas abajo."""
        Batch = self.env['mrp.workorder.batch']
        for rec in self:
            rolls = rec.roll_ids
            active = Batch.search([('wo_roll_ids', 'in', rolls.ids), ('state', '!=', 'draft')])
            if active:
                detail = '\n'.join(
                    '- %s (partida %s, %s)' % (
                        roll.name, batch.name,
                        dict(batch._fields['state']._description_selection(self.env)).get(batch.state, batch.state))
                    for batch in active for roll in (batch.wo_roll_ids & rolls))
                raise UserError(_(
                    'No se puede cancelar la recepción: hay rollos usados en partidas '
                    'que ya no están en borrador:\n%s') % detail)
            busy = rolls.filtered(lambda r: r.state in ('finished', 'transferred'))
            if busy:
                raise UserError(_(
                    'No se puede cancelar la recepción: hay rollos terminados o '
                    'transferidos: %s') % ', '.join(busy.mapped('name')))
            drafts = Batch.search([('wo_roll_ids', 'in', rolls.ids), ('state', '=', 'draft')])
            if drafts:
                drafts.write({'wo_roll_ids': [Command.unlink(r.id) for r in rolls]})
                rolls.write({'in_batch': False})
            rec.line_ids.write({'roll_id': False})
            rolls.unlink()
            rec.state = 'cancel'
        return True

    def action_draft(self):
        for rec in self:
            if rec.state != 'cancel':
                raise UserError(_('Solo una recepción cancelada vuelve a borrador.'))
            rec.state = 'draft'
        return True

    def action_print_stickers(self):
        rolls = self.roll_ids
        if not rolls:
            raise UserError(_('La recepción no tiene rollos creados.'))
        return rolls.reprint()


class MrpRollReceptionLine(models.Model):
    _name = 'mrp.roll.reception.line'
    _description = 'Rollo recibido del cliente'
    _order = 'sequence, id'

    reception_id = fields.Many2one('mrp.roll.reception', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=10)
    customer_roll_ref = fields.Char('Ref. del cliente')
    declared_weight = fields.Float('Peso guía (kg)')
    gross_weight = fields.Float('Peso planta (kg)', help='Si queda en cero se toma el peso de la guía.')
    location_note = fields.Char('Ubicación')
    reception_note = fields.Char('Observación')
    roll_id = fields.Many2one('mrp.workorder.roll', string='Rollo', readonly=True, ondelete='set null')
    roll_name = fields.Char(related='roll_id.name', string='N° interno')
    roll_state = fields.Selection(related='roll_id.state', string='Estado del rollo')
