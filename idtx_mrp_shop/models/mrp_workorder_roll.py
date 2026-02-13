from odoo import models

class MrpWorkorderRoll(models.Model):
    _inherit = "mrp.workorder.roll"

    def action_reprint_qr(self):
        if self.env.company.is_printer:
            self.workorder_id._print_zpl_to_network(self.workorder_id.create_zpl(self), self.env.company.zpl_printer_ip)