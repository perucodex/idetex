from odoo import models, fields

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
    digital_wash_speed_mts_min = fields.Float('Washing Speed (m/min)')
    digital_wash_temp_per_bath_c = fields.Float('Washing Temperature per Bath (°C)')
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
    washing_speed_m_min = fields.Float('Washing Speed (m/min)')
    washing_temperature_per_bath_c = fields.Float('Washing Temperature per Bath (°C)')
    inlet_roller_pressure_bar = fields.Float('Roller Pressure at Inlet (bar)')
    bath_ph = fields.Float('Bath pH')