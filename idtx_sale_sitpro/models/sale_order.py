import dbf
from odoo import models, api, _
from odoo.exceptions import UserError

class SaleOrder(models.Model):
    _inherit = "sale.order"
    
    def action_confirm(self):
        res = super().action_confirm()
        if self.company_id.is_company_produce and any(l.is_weaving for l in self.order_line):
            # Obtener datos de configuración
            file_cab = '/mnt/fox/sit06/DBF/vta_cab_pedido.dbf'
            file_det = '/mnt/fox/sit06/DBF/vta_det_pedido.dbf'
            # Datos de cabecera
            values = {
                'name': '222',
            }
            self.insert_record(file_cab, values)
            for line in self.order_line:
                # Datos de detalle
                values = {
                    'name': line.product_id.name,
                }
                self.insert_record(file_det, values)
        return res

    @api.model
    def insert_record(self, filename, values):
        try:
            # codepage/codificación depende de tu DBF (muy común cp1252 en ES)
            table = dbf.Table(filename, codepage="cp1252")
            table.open(mode=dbf.READ_WRITE)
            # IMPORTANTE: los nombres de campos suelen ir en MAYÚSCULAS
            normalized = {k.upper(): v for k, v in values.items()}
            # Inserta el registro
            table.append(normalized)
        except Exception as e:
            raise UserError(_("Error insertando en DBF: %s") % str(e))
        finally:
            try:
                table.close()
            except Exception:
                pass
        return True
