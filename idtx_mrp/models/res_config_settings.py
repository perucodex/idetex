from odoo import fields, models
from odoo.exceptions import UserError
import socket
import ipaddress

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    is_printer = fields.Boolean(related='company_id.is_printer', readonly=False)
    zpl_printer_ip = fields.Char(related='company_id.zpl_printer_ip', readonly=False)
    weaving_weight_per_roll = fields.Float(related='company_id.weaving_weight_per_roll', readonly=False)
    weaving_default_efficiency = fields.Float(related='company_id.weaving_default_efficiency', readonly=False)

    def test_zpl_printer_ip(self):
        if self.zpl_printer_ip and self.is_printer:
            self._print_zpl_to_network(self.create_zpl(), self.zpl_printer_ip)

    def create_zpl(self):
        zpl_code = f"""^XA
                    ^PW600
                    ^LL600
                    ^CI28

                    ^FO20,30
                    ^A0N,40,40
                    ^FDPRODUCTO PRUEBA DE IMPRESION^FS

                    ^FO20,100
                    ^BQN,2,10
                    ^FDLA,CODIGO DE PRUEBA DE IMPRESION^FS

                    ^FO300,110
                    ^A0N,22,22
                    ^FDCódigo: OTCUDORPOGIDOC^FS

                    ^FO300,135
                    ^A0N,22,22
                    ^FDColor: [COLOR PRUEBA]^FS

                    ^FO300,160
                    ^A0N,28,28
                    ^FDNOMBRE DE COLOR^FS

                    ^FO300,195
                    ^A0N,28,28
                    ^FDLote: LOTE DE PRODUCTO^FS

                    ^FO380,235
                    ^A0N,30,30
                    ^FDPeso^FS

                    ^FO330,285
                    ^A0N,60,60
                    ^FD30.99 kg^FS

                    ^FO80,375
                    ^A0N,22,22
                    ^FDROLLONRO^FS

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
            raise UserError("No se pudo imprimir (verificá IP): %s" % e)