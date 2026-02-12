from odoo import models, fields


class IntegrationOrgatexProcedure(models.Model):
    _name = "integration.orgatex.procedure"
    _description = "Dyelot Procedure Detail"

    orgatex_id = fields.Many2one(
        "integration.orgatex",
        ondelete="cascade"
    )

    redye = fields.Integer()
    treatment_cnt = fields.Integer()
    treatment_no = fields.Integer()
