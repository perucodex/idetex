from odoo import models, fields, api
import statistics

class ControlPedidoLine(models.Model):
    _inherit = "control.pedido.line"
    
    design_image = fields.Image(string='Design Image', attachment=True)
    printing_type = fields.Selection([
        ('digital', 'Digital'),
        ('rotary', 'Rotary')
    ], string='Printing Type')
    # Digital printing
    pass_qty = fields.Integer('Number of Passes')
    printing_direction = fields.Selection([
        ('uni', 'Unidirectional'),
        ('bi', 'Bidirectional'),
    ], string='Printing Direction', default='uni')
    width_print = fields.Float('Print Width (max 1.80 meters)')
    digital_color_management = fields.Text('Color management, resolution, profiles (MatchPrint and Inedit software)')
    digital_paste_recipe = fields.Text('Pasting recipe with transparent bath at around pH 10.5 (alkaline)')
    digital_dye_steam_process = fields.Text('Digital printing with dye/colorant steamed from 102 °C to 104 °C')
    digital_pigment_polymerized_process = fields.Text('Digital printing with polymerized pigment from 150 °C to 160 °C')
    digital_wash_speed_mts_min = fields.Float('Digital Washing Speed (m/min)')
    digital_wash_temp_per_bath_c = fields.Float('Digital Washing Temperature per Bath (°C)')
    # Rotary printing
    printing_speed_m_min = fields.Float('Printing Speed (m/min)')
    cylinder_number_per_color = fields.Char('Cylinder Number (per color)')
    magnetic_bar_pressure_kg = fields.Float('Magnetic Bar Pressure Inside Cylinder (kg)')
    bar_number_diameter = fields.Char('Bar Number (diameter)')
    drying_temperature_c = fields.Float('Drying Temperature (°C)')
    fabric_tension_steamer = fields.Float('Fabric Tension (steamer)')
    steam_pressure_steamer = fields.Float('Steam Pressure (steamer)')
    steaming_temperature_c = fields.Float('Steaming Temperature (°C)')
    steaming_time_m_min = fields.Float('Steaming Time (m/min)')
    washing_speed_m_min = fields.Float('Rotary Washing Speed (m/min)')
    washing_temperature_per_bath_c = fields.Float('Rotary Washing Temperature per Bath (°C)')
    inlet_roller_pressure_bar = fields.Float('Roller Pressure at Inlet (bar)')
    bath_ph = fields.Float('Bath pH')
    printing_point = fields.Float(string="Printing Point", digits=(16, 2), compute='_compute_printing_point', store=True)

    def _filter_lines(self, for_printing=False):
        if for_printing:
            return self.apariencia_line_ids.filtered(lambda l: l.type_deffect == 'printing')
        return self.apariencia_line_ids.filtered(lambda l: l.type_deffect == 'quality')

    @api.depends('apariencia_line_ids')
    def _compute_printing_point(self):
        for rec in self:
            filtered_lines = rec._filter_lines(True)
            points = 0
            width = statistics.mean([roll.width for roll in filtered_lines]) if filtered_lines else 0
            meters = sum([roll.meters for roll in filtered_lines]) if filtered_lines else 0
            for roll in filtered_lines:
                for tamano in roll.defecto_line_ids.tamano_defecto_ids:
                    points += int(tamano.print_size)
            rec.printing_point = ((points * 100) / (width * meters)) if width and meters else 0