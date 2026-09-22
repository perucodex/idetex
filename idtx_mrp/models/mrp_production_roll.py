from odoo import _, models, fields, api
from odoo.exceptions import UserError, ValidationError
import socket
import ipaddress

class MrpProductionRoll(models.Model):
    _name = "mrp.production.roll"
    _description = 'Mrp Production Roll'

    production_id = fields.Many2one('mrp.production', string='Production')
    sequence = fields.Integer('Sequence')
    batch_id = fields.Many2one('mrp.workorder.batch', string='Batch')
    name = fields.Char('Number')
    product_id = fields.Many2one(related='production_id.product_id.product_tmpl_id')
    uom_id = fields.Many2one(related='production_id.product_id.product_tmpl_id.uom_id')
    lot_id = fields.Many2one('stock.lot', 'Lot')
    quantity = fields.Integer('Quantity', default=1)
    gross_weight = fields.Float('Gross Weight')
    net_weight = fields.Float('Net Weight')
    net_length = fields.Float('Net Length')
    equipment_id = fields.Many2one('maintenance.equipment', string='Equipment')
    employee_id = fields.Many2one('hr.employee', string='Employee')
    # Fecha/hora del PESADO en la pantalla "Pesado de rollos". Además marca
    # que el rollo ya generó su quant al pesarse (no debe volver a generar
    # stock vía Producir de la OF).
    weighed_date = fields.Datetime('Fecha de Pesado', readonly=True, copy=False)
    # Rollo CRUDO que se pesó (elegido en el diálogo de pesado): trazabilidad
    # crudo → terminado; en rectilíneos aporta además la talla.
    wo_roll_id = fields.Many2one(
        'mrp.workorder.roll', string='Rollo de Tejido', ondelete='set null',
        copy=False)
    # N° de rollo que Acabado marca en la partida (1..N). Es el correlativo
    # del lote (<partida>-NNN) y la referencia que usa Calidad antes del pesado.
    roll_num = fields.Integer('N° rollo', copy=False, index=True)

    # --- Calidad del rollo terminado ---
    # El GRADO lo da Calidad por N° de rollo ANTES del pesado (calificación
    # previa); al pesar se copia al rollo (sin marca previa → A). Pesado puede
    # SEPARAR un rollo (observado): se pesa igual, sticker OBSERVADO, va al
    # área de reproceso; Calidad le da el grado final y se repesa SIEMPRE.
    # A → Existencias, B → Saldo, M → Mermas.
    quality_grade = fields.Selection(
        [('A', 'A'), ('B', 'B'), ('M', 'M')], string='Grado', copy=False, index=True,
        help='A: primera (Existencias) · B: segunda (Saldo) · M: merma (Mermas).')
    quality_observation = fields.Selection(
        [('stain', 'Desmanchar'), ('decontaminate', 'Descontaminar'),
         ('reprocess', 'Reprocesar'), ('other', 'Otro')],
        string='Observación', copy=False,
        help='Motivo por el que el rollo se separó para reproceso al pesarlo.')
    quality_note = fields.Char('Detalle', copy=False)
    quality_state = fields.Selection(
        [('pending', 'Sin calificar'), ('observed', 'Observado'),
         ('graded', 'Calificado'), ('released', 'Liberado')],
        string='Estado calidad', compute='_compute_quality_state', store=True, index=True)
    quality_released = fields.Boolean('Liberado a almacén', copy=False, readonly=True)
    quality_release_date = fields.Datetime('Fecha de liberación', copy=False, readonly=True)
    quality_user_id = fields.Many2one('res.users', 'Calificado por', copy=False, readonly=True)
    quality_date = fields.Datetime('Fecha de calificación', copy=False, readonly=True)
    resolved_weight_date = fields.Datetime('Fecha de repesado', copy=False, readonly=True)
    # Rollo observado al que Calidad ya dio grado final: falta repesarlo en
    # la zona de pesado antes de poder liberarlo a almacén.
    reweigh_pending = fields.Boolean('Pendiente de repesar', copy=False, readonly=True, index=True)

    @api.depends('quality_grade', 'quality_observation', 'quality_released')
    def _compute_quality_state(self):
        for roll in self:
            if roll.quality_released:
                roll.quality_state = 'released'
            elif roll.quality_grade:
                roll.quality_state = 'graded'
            elif roll.quality_observation:
                roll.quality_state = 'observed'
            else:
                roll.quality_state = 'pending'

    @api.constrains('quality_grade', 'quality_observation')
    def _check_quality_on_weighed_roll(self):
        for roll in self:
            if (roll.quality_grade or roll.quality_observation) and not roll.lot_id:
                raise ValidationError(_(
                    'El rollo %s no está pesado: la calidad se decide al pesarlo.'
                ) % (roll.name or roll.id))

    def _quality_observation_label(self):
        self.ensure_one()
        labels = dict(self._fields['quality_observation']._description_selection(self.env))
        return labels.get(self.quality_observation, '')

    def _zpl_banner(self):
        """Franja del sticker: OBSERVADO + motivo mientras no tenga grado;
        GRADO B / GRADO M cuando el grado final no es A."""
        self.ensure_one()
        if self.quality_observation and not self.quality_grade:
            return 'OBSERVADO: %s' % self._quality_observation_label().upper()
        if self.quality_grade in ('B', 'M'):
            return 'GRADO %s%s' % (self.quality_grade, (
                ' · ' + self._quality_observation_label().upper()) if self.quality_observation else '')
        return ''

    def reprint(self):
        # OJO: create_zpl(weight) usa gross_weight si weight es 0/falsy; NO
        # pasar rec.quantity (piezas del rollo = 1) o la etiqueta sale "1 kg".
        for rec in self:
            if rec.env.company.is_printer:
                rec._print_zpl_to_network(rec.create_zpl(), self.env.company.zpl_printer_ip)

    #=== CRUD METHODS ===#

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            vals['name'] = self.env['ir.sequence'].with_company(vals.get('company_id')).next_by_code('mrp.production.roll')
        records = super().create(vals_list)
        records.mapped('production_id')._sync_qty_producing_from_production_rolls()
        return records

    def write(self, vals):
        if 'quality_grade' in vals or 'quality_observation' in vals:
            released = self.filtered('quality_released')
            if released:
                raise UserError(_(
                    'Rollos ya liberados a almacén, no se puede cambiar su calificación: %s'
                ) % ', '.join(released.mapped('lot_id.name')))
            if vals.get('quality_grade') or vals.get('quality_observation'):
                vals.setdefault('quality_user_id', self.env.uid)
                vals.setdefault('quality_date', fields.Datetime.now())
        # Grado final sobre un rollo OBSERVADO ya pesado → hay que repesarlo.
        to_reweigh = self.env['mrp.production.roll']
        if vals.get('quality_grade') and not self.env.context.get('skip_reweigh_flag'):
            to_reweigh = self.filtered(lambda r: r.quality_observation and r.lot_id)
        productions = self.mapped('production_id')
        res = super().write(vals)
        if to_reweigh:
            super(MrpProductionRoll, to_reweigh).write({'reweigh_pending': True})
        (productions | self.mapped('production_id'))._sync_qty_producing_from_production_rolls()
        return res

    def unlink(self):
        productions = self.mapped('production_id')
        lots_to_cleanup = self.mapped('lot_id')
        res = super().unlink()

        # Cleanup orphan lots created for rolls when they are not used anywhere else.
        for lot in lots_to_cleanup.exists():
            has_quants = bool(lot.quant_ids) if 'quant_ids' in lot._fields else False
            has_moves = bool(lot.move_line_ids) if 'move_line_ids' in lot._fields else False
            if has_quants or has_moves:
                continue
            lot.unlink()

        productions._sync_qty_producing_from_production_rolls()
        return res
    
    def create_zpl(self, weight=0):
        self.ensure_one()
        weight = self.gross_weight if not weight else weight
        color_block = ""
        if self.lot_id.color_code and self.lot_id.color_code.strip() != "00000000":
            color_block = f"""^FO300,135
                              ^A0N,22,22
                              ^FDColor: [{self.lot_id.color_code}]^FS"""
        zpl_code = f"""^XA
                    ^PW600
                    ^LL600
                    ^CI28

                    ^FO20,30
                    ^A0N,40,40
                    ^FD{(self.product_id.name or self.lot_id.product_id.name)}^FS

                    ^FO20,100
                    ^BQN,2,10
                    ^FDLA,01{(self.product_id.barcode or self.lot_id.product_id.barcode)}3102{str(int(round(weight * 100))).zfill(6)}10{self.lot_id.name}^FS

                    ^FO300,110
                    ^A0N,22,22
                    ^FDCódigo: {(self.product_id.default_code or self.lot_id.product_id.default_code)}^FS

                    {color_block}\
                    ^FO300,160
                    ^A0N,28,28
                    ^FD{self.lot_id.color_name}^FS

                    ^FO300,195
                    ^A0N,{28 if len(self.lot_id.name or '') <= 11 else 23},{28 if len(self.lot_id.name or '') <= 11 else 23}
                    ^FDLote: {self.lot_id.name}^FS
                    {self._zpl_weight_block(weight)}
                    ^FO80,375
                    ^A0N,22,22
                    ^FD{self.name}^FS
                    ^XZ"""
        return zpl_code

    def _zpl_weight_block(self, weight):
        """Columna derecha bajo la partida. La etiqueta mide 600×400 puntos
        (3"×2" a 203 dpi), así que la franja OBSERVADO / GRADO B-M debe caber
        ANTES de los 400 puntos: en esas etiquetas el peso sube (sin la
        palabra "Peso") y debajo van la franja negra y el motivo + detalle."""
        self.ensure_one()
        banner = self._zpl_banner()
        if not banner:
            return f"""
                    ^FO380,235
                    ^A0N,30,30
                    ^FDPeso^FS

                    ^FO330,285
                    ^A0N,60,60
                    ^FD{weight} kg^FS"""
        # Texto corto en la franja; el motivo va aparte para que quepa.
        band = 'OBSERVADO' if not self.quality_grade else 'GRADO %s' % self.quality_grade
        reason = self._quality_observation_label().upper()
        note = (self.quality_note or '').strip()
        line1 = reason if reason else ''
        line2 = note[:30]
        if not line1:
            line1, line2 = line2, ''
        block = f"""
                    ^FO330,232
                    ^A0N,50,50
                    ^FD{weight} kg^FS

                    ^FO300,292
                    ^GB290,42,42^FS
                    ^FO312,299
                    ^A0N,30,30
                    ^FR
                    ^FD{band}^FS"""
        if line1:
            block += f"""
                    ^FO300,345
                    ^A0N,22,22
                    ^FD{line1[:26]}^FS"""
        if line2:
            block += f"""
                    ^FO300,371
                    ^A0N,20,20
                    ^FD{line2}^FS"""
        return block

                    # ^FO300,270
                    # ^A0N,22,22
                    # ^FDMetros: {self.net_length}^FS

                    # ^FO300,295
                    # ^A0N,22,22
                    # ^FDUsuario: {self.create_uid.name}^FS
        
    def _print_zpl_to_network(self, zpl_code, printer_ip, port=9100):
        """Envía ZPL a impresora por socket TCP/IP."""
        try:
            # 1. Validar IP
            ip = str(ipaddress.ip_address(printer_ip.strip()))
            # 2. Enviar
            with socket.create_connection((ip, port), timeout=5) as sock:
                sock.sendall(zpl_code.encode('utf-8'))
        except (socket.error, UnicodeError, ValueError) as e:
            raise UserError("No se pudo imprimir (verificá IP): %s" % e)