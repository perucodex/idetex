from odoo import fields, models

class ControlApariencia(models.Model):
    _name = "qc.appearance"
    _description = "Control de Apariencia"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char('Name')
    mrp_workcenter_id = fields.Many2one('mrp.workcenter', string='MRP Workcenter')
    is_printing = fields.Selection(related='mrp_workcenter_id.operation_type')
    defect_ids = fields.One2many('qc.appearance.defect', 'apariencia_id', string='Defects')

class ControlAparienciaDefecto(models.Model):
    _name = "qc.appearance.defect"
    _description = "Defectos Apariencia (Maestro)"
    _order = "name asc, id asc"

    apariencia_id = fields.Many2one('qc.appearance', string='Apariencia', required=True, ondelete='cascade')
    sequence = fields.Integer('sequence')
    name = fields.Char(string="Defecto", required=True, index=True)
    is_active = fields.Boolean(string="Activo", default=True)
    is_hueco = fields.Boolean(string="¿Es Hueco?", default=False)
    type_printing = fields.Selection([
        ('digital', 'Digital'),
        ('rotary', 'Rotary'),
        ('both', 'Both'),
    ], string='Printing Type', default='digital')