from odoo import models, fields


class IntegrationOrgatexRecipe(models.Model):
    _name = "integration.orgatex.recipe"
    _description = "Dyelot Recipe Detail"

    orgatex_id = fields.Many2one(
        "integration.orgatex",
        ondelete="cascade"
    )

    correction_number = fields.Integer()
    redye = fields.Integer()
    call_off = fields.Integer()
    counter = fields.Integer()
    product_name = fields.Char()
    product_short_name = fields.Char()
    product_code = fields.Char()
    amount = fields.Float()
    amount_per_machine = fields.Float()
    unit = fields.Char()
    kind_of_station = fields.Integer()
    state = fields.Integer()
    specific_weight = fields.Float()
    no_of_station = fields.Integer()
