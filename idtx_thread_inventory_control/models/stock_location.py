from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class StockLocation(models.Model):
    _inherit = "stock.location"

    is_thread_main_location = fields.Boolean(string="Almacén Principal de Hilo")
    is_thread_production_location = fields.Boolean(string="Almacén de Producción de Hilo")
    is_thread_second_quality_location = fields.Boolean(string="Almacén de Hilo 2da Calidad")

    @api.constrains("is_thread_main_location", "company_id")
    def _check_unique_thread_main_location(self):
        self._check_unique_thread_flag("is_thread_main_location",
                                       _("almacén principal de hilo"))

    @api.constrains("is_thread_production_location", "company_id")
    def _check_unique_thread_production_location(self):
        self._check_unique_thread_flag("is_thread_production_location",
                                       _("almacén de producción de hilo"))

    @api.constrains("is_thread_second_quality_location", "company_id")
    def _check_unique_thread_second_quality_location(self):
        self._check_unique_thread_flag("is_thread_second_quality_location",
                                       _("almacén de hilo de 2da calidad"))

    def _check_unique_thread_flag(self, field_name, label):
        for location in self.filtered(field_name):
            domain = [
                ("id", "!=", location.id),
                (field_name, "=", True),
                "|",
                ("company_id", "=", location.company_id.id),
                ("company_id", "=", False),
            ]
            if self.search_count(domain):
                raise ValidationError(_(
                    "Solo puede existir una ubicación marcada como %s por compañía."
                ) % label)

    @api.model
    def _get_thread_main_location(self, company):
        return self.search([
            ("is_thread_main_location", "=", True),
            "|", ("company_id", "=", company.id), ("company_id", "=", False),
        ], limit=1)
