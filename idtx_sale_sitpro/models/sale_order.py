import os
import dbf
from odoo import models, api, _
from odoo.exceptions import UserError

class SaleOrder(models.Model):
    _inherit = "sale.order"
    
    def action_confirm(self):
        res = super().action_confirm()
        # if self.company_id.is_company_produce:
        #     # Obtener datos de configuración
        #     folder = '/mnt/fox/sit06/JP_DBF'
        #     db_file_cab = 'vta_cab_pedido.dbf'
        #     db_file_det = 'vta_det_pedido.dbf'
        #     # Datos de cabecera
        #     values = {
        #         'name': '222',
        #     }
        #     self.insert_record(folder, db_file_cab, values)
        #     for line in self.order_line:
        #         # Datos de detalle
        #         values = {
        #             'name': line.product_id.name,
        #         }
        #         self.insert_record(folder, db_file_det, values)
        return res

    @api.model
    def insert_record(self, folder_path, dbf_filename, values):
        dbf_path = os.path.join(folder_path, dbf_filename)
        if not os.path.isfile(dbf_path):
            raise UserError(_("No existe el archivo DBF: %s") % dbf_path)
        try:
            # codepage/codificación depende de tu DBF (muy común cp1252 en ES)
            table = dbf.Table(dbf_path, codepage="cp1252")
            table = dbf.Table(dbf_path, codepage="cp1252")
            table.open()
            fields = table.field_names  # lista de campos
            for f in fields:
                print(f)
            table.close()
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
