from odoo import _, models, fields, api
from odoo.exceptions import UserError
import socket
import ipaddress

class MrpWorkorderRoll(models.Model):
    _name = "mrp.workorder.roll"
    _description = 'Mrp Workorder Roll'

    workorder_id = fields.Many2one('mrp.workorder', string='Workorder')
    # Trazabilidad de transferencia entre OTs con DOS registros del mismo rollo:
    #  - En la OT de ORIGEN: el registro original, estado 'transferido'. SIGUE
    #    contando su consumo (se tejió ahí). Guarda `dest_workorder_id`.
    #  - En la OT de DESTINO: una COPIA, estado 'recibido'. NO cuenta consumo
    #    (no se tejió ahí). Guarda `transfer_origin_roll_id` (el original).
    transfer_state = fields.Selection([
        ('transferido', 'Transferido'),
        ('recibido', 'Recibido'),
    ], string='Estado de Transferencia', readonly=True, copy=False, index=True)
    dest_workorder_id = fields.Many2one(
        'mrp.workorder', string='Transferido a (OT)', readonly=True, copy=False, index=True,
        help='OT a la que se transfirió el rollo (registro de origen).')
    transfer_origin_roll_id = fields.Many2one(
        'mrp.workorder.roll', string='Rollo de Origen (Transferencia)',
        readonly=True, copy=False, ondelete='cascade', index=True,
        help='Registro original (en la OT de tejido) del cual este rollo '
             'recibido es copia.')
    is_transferred = fields.Boolean(
        'Transferido', compute='_compute_is_transferred', store=True)
    sequence = fields.Integer('Sequence')
    name = fields.Char('Number')
    product_id = fields.Many2one(related='workorder_id.product_id.product_tmpl_id')
    uom_id = fields.Many2one(related='workorder_id.product_id.product_tmpl_id.uom_id')
    quantity = fields.Integer('Quantity')
    gross_weight = fields.Float('Gross Weight')
    net_weight = fields.Float('Net Weight')
    in_batch = fields.Boolean('in_batch?', default=False)
    new_weight = fields.Float('Split new weight')
    equipment_id = fields.Many2one('maintenance.equipment', string='Equipment')
    employee_id = fields.Many2one('hr.employee', string='Employee')
    roll_start = fields.Datetime('Start Date')
    roll_end = fields.Datetime('End Date')
    option_id = fields.Many2one('mrp.workorder.option', string='Option')
    equipment_ids = fields.Many2many(related='option_id.equipment_ids')
    employee_ids = fields.Many2many(related='option_id.employee_ids')
    current_batch_id = fields.Many2one(
        'mrp.workorder.batch', string='Partida Actual',
        compute='_compute_current_batch_id',
        help='Partida activa (no dividida/desarmada) en la que vive el rollo hoy.')
    # Lotes de hilado con los que se tejió el rollo: snapshot tomado de la
    # opción de la tejedora al crear el rollo (los lotes de la opción pueden
    # cambiar después; el rollo conserva los suyos). copy=True: un rollo
    # dividido hereda los lotes del original. Lo usan las partidas para
    # validar la sub-receta de la combinación de lotes en laboratorio.
    thread_lot_ids = fields.Many2many(
        'stock.lot', 'wo_roll_thread_lot_rel', 'roll_id', 'lot_id',
        string='Lotes de Hilo', copy=True)

    @api.depends('transfer_state')
    def _compute_is_transferred(self):
        for roll in self:
            roll.is_transferred = bool(roll.transfer_state)

    def action_revert_transfer(self):
        """Revierte transferencias (devuelve los rollos a su OT original): borra
        los registros RECIBIDOS y quita el estado 'transferido' de los
        originales. Sirve seleccionando el original (transferido) o la copia
        (recibido). Bloquea si algún rollo está en una partida activa."""
        Roll = self.env['mrp.workorder.roll']
        originals = Roll
        for roll in self:
            if roll.transfer_state == 'recibido' and roll.transfer_origin_roll_id:
                originals |= roll.transfer_origin_roll_id
            elif roll.transfer_state == 'transferido':
                originals |= roll
        if not originals:
            raise UserError(_(
                'Selecciona rollos transferidos o recibidos para revertir la '
                'transferencia.'))
        copies = Roll.search([('transfer_origin_roll_id', 'in', originals.ids)])
        blocked = (originals | copies).filtered(lambda r: r.current_batch_id)
        if blocked:
            raise UserError(_(
                'No se puede revertir la transferencia: hay rollos en una '
                'partida activa (estado "Partida"):\n%s'
            ) % '\n'.join('- %s (partida %s)' % (r.name, r.current_batch_id.name)
                          for r in blocked))
        copies.unlink()
        originals.write({'transfer_state': False, 'dest_workorder_id': False})
        return True

    def _compute_current_batch_id(self):
        Batch = self.env['mrp.workorder.batch']
        for roll in self:
            roll.current_batch_id = Batch.search(
                [('wo_roll_ids', 'in', roll.id), ('state', '=', 'batch')], limit=1)

    def reprint(self):
        # self.ensure_one()
        return {
            'type': 'ir.actions.client',
            'tag': 'print_zpl_ip',
            "params": {
                "record_ids": self.ids,
            }
        }
        # for rec in self:
        #     rec._print_zpl_to_network(rec.create_zpl(), self.env.company.zpl_printer_ip)

    #=== CRUD METHODS ===#

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Respeta un nombre provisto (p.ej. la copia RECIBIDA conserva el
            # mismo número del rollo original); genera secuencia solo si falta.
            if not vals.get('name'):
                vals['name'] = self.env['ir.sequence'].with_company(vals.get('company_id')).next_by_code('mrp.workorder.roll')
            # Snapshot de los lotes de hilo desde la opción de la tejedora.
            if not vals.get('thread_lot_ids') and vals.get('option_id'):
                option = self.env['mrp.workorder.option'].browse(vals['option_id'])
                lot_ids = option.option_line_ids.filtered('lot_id').mapped('lot_id').ids
                if lot_ids:
                    vals['thread_lot_ids'] = [(6, 0, lot_ids)]
        return super().create(vals_list)
    
    def unlink(self):
        roll_names = ''
        for rec in self:
            if rec.in_batch:
                roll_names += rec.name + '\n'
        if roll_names:
            raise UserError(_('Can\'t delete a roll that is in a batch process.\nRolls:\n%s') %roll_names)
        return super().unlink()

    def create_zpl(self):
        self.ensure_one()
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url') #"https://odoo.gestionidtx.com/rollo"
        url = f"{base_url}/rollo/datos/{self.id}"
        zpl_code = f"""^XA
                    ^PW600
                    ^LL600
                    ^CI28

                    ^FO20,30
                    ^A0N,40,40
                    ^FD{self.product_id.name}^FS

                    ^FO20,100
                    ^BQN,2,8.5
                    ^FDLA,{url}^FS

                    ^FO300,110
                    ^A0N,22,22
                    ^FDCódigo: {self.product_id.default_code}^FS

                    ^FO300,135
                    ^A0N,22,22
                    ^FDRollo: {self.name}^FS

                    ^FO300,160
                    ^A0N,22,22
                    ^FDPeso: {self.gross_weight}^FS

                    ^FO300,185
                    ^A0N,22,22
                    ^FDPeso Neto: {self.net_weight} kg^FS

                    ^FO300,210
                    ^A0N,22,22
                    ^FDMaquina: {self.equipment_id.name}^FS

                    ^FO300,235
                    ^A0N,22,22
                    ^FDUsuario: {self.employee_id.name}^FS

                    ^XZ"""
        return zpl_code
        
    def _print_zpl_to_network(self, zpl_code, printer_ip, port=9100):
        """Envía ZPL a impresora por socket TCP/IP."""
        try:
            # 1. Validar IP
            ip = str(ipaddress.ip_address(printer_ip.strip()))
            # 2. Enviar
            with socket.create_connection((ip, port), timeout=5) as sock:
                sock.sendall(zpl_code.encode('utf-8'))
        except (socket.error, UnicodeError, ValueError) as e:
            raise UserError("No se pudo imprimir: %s" % e)
        

    def print_zpl_with_ip(self, printer_ip):
        for rec in self:
            try:
                ipaddress.ip_address(printer_ip)
                rec.ensure_one()
                rec._print_zpl_to_network(rec.create_zpl(), printer_ip)
            except (socket.error, UnicodeError, ValueError) as e:
                raise UserError("No se pudo imprimir: %s" % e)
        return True