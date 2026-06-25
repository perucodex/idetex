from odoo import fields, models


class MrpWorkcenter(models.Model):
    _inherit = "mrp.workcenter"

    operator_department_id = fields.Many2one(
        "hr.department",
        string="Departamento de Operarios",
        check_company=True,
        help="Departamento de RR.HH. cuyos empleados pueden operar este centro de "
             "trabajo (p. ej. los tintoreros). El shop floor usa este departamento "
             "para listar a quién asignar el batch. Es por compañía: configura el "
             "centro de trabajo de cada empresa con su propio departamento.",
    )
