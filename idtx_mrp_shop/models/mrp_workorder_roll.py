from odoo import models

class MrpWorkorderRoll(models.Model):
    _inherit = "mrp.workorder.roll"

    def action_reprint_qr(self):
        self.workorder_id._print_zpl_to_network(self.workorder_id.create_zpl(self))