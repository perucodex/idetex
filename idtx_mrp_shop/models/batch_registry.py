from odoo import fields, models, api, _, Command
import base64
from pathlib import Path

class BatchRegistry(models.Model):
    _name = 'batch.registry'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Batch Registry'
    _rec_name = 'batch_id'
    
    batch_id = fields.Many2one('mrp.workorder.batch', string='Batch')
    workorder_id = fields.Many2one('mrp.workorder', string='Workorder')
    registry_date = fields.Datetime('Registry Date')
    employee_id = fields.Many2one('hr.employee', string='Employee')
    equipment_id = fields.Many2one('maintenance.equipment', string='Equipment')
    bath_ratio = fields.Integer('Bath ratio')
    color_name = fields.Char('Color Name')
    color_code = fields.Char('Color Code')
    partner_id = fields.Many2one('res.partner', 'Customer')
    abs_factor = fields.Float('Absorption Factor', default=3.0)
    weight = fields.Float(related='batch_id.total_weight', string='Total Weight')
    recipe_salt = fields.Float('Recipe Salt', compute='_compute_recipe_components')
    recipe_carbonate = fields.Float('Recipe Carbonate', compute='_compute_recipe_components')
    recipe_soda = fields.Float('Recipe Soda', compute='_compute_recipe_components')
    total_volume = fields.Float('Total Volume', compute='_compute_volume')
    alkalis_volume = fields.Float('Alkalis Volume')
    dyes_volume = fields.Float('Dyes Volume')
    start_salt = fields.Float('Start Salt', compute='_compute_volume')
    start_brine = fields.Float('Start Brine', compute='_compute_volume')
    salt_qty = fields.Float('Salt Quantity', compute='_compute_volume')
    brine_qty = fields.Float('Brine Quantity', compute='_compute_volume')
    hydrophilicity = fields.Selection([
        ('ok', 'Ok'),
        ('reg', 'Regular'),
        ('bad', 'Bad'),
    ], string='Hydrophilicity')
    peroxide_residual = fields.Selection([
        ('0', '0'),
        ('0.5', '0.5'),
        ('2', '2'),
        ('5', '5'),
        ('10', '10'),
        ('25', '25'),
    ], string='Peroxide Residual')
    antipilling_ph = fields.Float('Anti-pilling pH')
    dye_ph = fields.Float('Dye pH')
    previous_ph = fields.Float('Previous pH')
    neutralized_ph = fields.Float('Neutralized pH')
    hardness_dyeing_water = fields.Float('Hardness Dyeing Water')
    pump_speed = fields.Selection([
        ('600','600'),
        ('700','700'),
        ('800','800'),
        ('900','900'),
        ('950','950'),
        ('1000','1000'),
        ('1050','1050'),
        ('1100','1100'),
        ('1150','1150'),
        ('1200','1200'),
        ('1250','1250'),
        ('1300','1300'),
        ('1350','1350'),
        ('1400','1400'),
        ('50%','50%'),
        ('55%','55%'),
        ('60%','60%'),
        ('65%','65%'),
        ('70%','70%'),
        ('75%','75%'),
        ('80%','80%'),
        ('85%','85%'),
        ('90%','90%'),
        ('95%','95%'),
        ('100%','100%'),
    ], string='Pump Speed')
    reel_speed = fields.Float('Reel Speed Mt/min')
    hydrovary = fields.Selection([
        ('10', '10'),
        ('20', '20'),
        ('30', '30'),
        ('40', '40'),
        ('50', '50'),
        ('60', '60'),
        ('70', '70'),
        ('80', '80'),
        ('90', '90'),
    ], string='Hydrovary')
    rope1 = fields.Float('Rope1')
    rope2 = fields.Float('Rope2')
    rope3 = fields.Float('Rope3')
    rope4 = fields.Float('Rope4')
    rope5 = fields.Float('Rope5')
    rope6 = fields.Float('Rope6')
    salt_measurement = fields.Float('Salt Measurement')
    actual_volume = fields.Float('Actual Volume', compute='_compute_volume')
    water_batches = fields.Selection([
        ('wb1', '3'),
        ('wb2', '3 + 1'),
        ('wb3', '2 + 1'),
    ], string='Water Batches')
    total_tanq_volume = fields.Float('Total Tank Volume', compute='_compute_volume')
    final_volume = fields.Float('Final Volume', compute='_compute_volume')
    volume_variation = fields.Float('Volume Variation', compute='_compute_volume')
    message = fields.Char('Message', compute='_compute_volume')
    ribbon_message = fields.Char('Ribbon Message', compute='_compute_volume')
    add_salt = fields.Float('Textile Salt', compute='_compute_volume')
    add_carbonate = fields.Float('Carbonate', compute='_compute_volume')
    add_soda = fields.Float('Soda', compute='_compute_volume')
    tipo_proceso = fields.Selection([
        ('ISOTERMICA60', 'ISOTERMICA60'),
        ('MIGRACION40-60', 'MIGRACION40-60'),
        ('MIGRACION60-80-60', 'MIGRACION60-80-60'),
        ('MIGRACION80-90-60', 'MIGRACION80-90-60'),
        ('MIGRASALADE160-80-60', 'MIGRASALADE160-80-60'),
    ], string='Tipo de Proceso')
    imagen_proceso = fields.Binary('Imagen Proceso', compute='_compute_imagen_proceso', store=False)
    ph_poly = fields.Float('pH Poly')
    red_wash = fields.Float('Red Wash')
    before_carb = fields.Float('Before Carbonate')
    first_carb = fields.Float('First Carbonate')
    second_carb = fields.Float('Second Carbonate')
    exhaustion = fields.Float('Exhaustion')
    neutralization = fields.Float('Neutralization')
    soaping = fields.Float('Soaping')
    discharge = fields.Float('Discharge')
    notes = fields.Text('Observations')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done'),
        ('rejected', 'Rejected'),
    ], string='state', default='draft', tracking=True)

    @api.depends('tipo_proceso')
    def _compute_imagen_proceso(self):
        for rec in self:
            if rec.tipo_proceso:
                img_path = Path(__file__).parent.parent / f'static/src/images/{rec.tipo_proceso}.jpg'
                if img_path.exists():
                    with img_path.open('rb') as f:
                        rec.imagen_proceso = base64.b64encode(f.read())
                else:
                    rec.imagen_proceso = False
            else:
                rec.imagen_proceso = False

    @api.depends('workorder_id')
    def _compute_recipe_components(self):
        for rec in self:
            prd = rec.workorder_id.production_id
            recipe = prd.color_recipe_id
            salt = 0
            carbonate = 0
            soda = 0
            for crpl in recipe.color_recipe_process_ids.color_recipe_process_line_ids:
                if crpl.product_id.categ_id == self.env.ref('idtx_laboratory.product_categ_4'):
                    salt += crpl.factor
                elif crpl.product_id.categ_id == self.env.ref('idtx_laboratory.product_categ_5'):
                    carbonate += crpl.factor
                elif crpl.product_id.categ_id == self.env.ref('idtx_laboratory.product_categ_6'):
                    soda += crpl.factor
            rec.recipe_salt = salt
            rec.recipe_carbonate = carbonate
            rec.recipe_soda = soda
    
    @api.depends('weight','bath_ratio','abs_factor','equipment_id','salt_measurement','water_batches')
    def _compute_volume(self):
        for rec in self:
            rec.total_volume = rec.weight * rec.bath_ratio
            rec.start_salt = (rec.total_volume - (rec.weight * rec.abs_factor)) - (rec.dyes_volume + 4 * rec.alkalis_volume)
            rec.brine_qty = (rec.recipe_salt * rec.total_volume / 0.33) / 1000
            rec.start_brine = (rec.total_volume - (rec.weight * rec.abs_factor)) - (rec.brine_qty + rec.dyes_volume + 3 * rec.alkalis_volume)
            rec.salt_qty = rec.recipe_salt * rec.total_volume / 1000
            rec.add_soda = 0
            if rec.water_batches:
                if rec.water_batches == 'wb1':
                    rec.total_tanq_volume = 3 * rec.alkalis_volume
                elif rec.water_batches == 'wb2':
                    rec.total_tanq_volume = 3 * rec.alkalis_volume + rec.dyes_volume
                elif rec.water_batches == 'wb3':
                    rec.total_tanq_volume = 2 * rec.alkalis_volume + rec.dyes_volume
            else:
                rec.total_tanq_volume = 0
            if rec.salt_measurement:
                rec.actual_volume = rec.total_volume * rec.recipe_salt / rec.salt_measurement
                rec.final_volume = rec.total_volume * rec.recipe_salt / rec.salt_measurement + rec.total_tanq_volume
                rec.volume_variation = rec.total_volume - rec.final_volume
                if rec.volume_variation > 0:
                    rec.add_salt = 0
                    rec.add_carbonate = 0
                    rec.ribbon_message = 1
                    rec.message = _('Missing water')
                elif rec.volume_variation < 0:
                    rec.add_salt = -(rec.recipe_salt * rec.volume_variation) / 1000
                    rec.add_carbonate = -(rec.recipe_carbonate * rec.volume_variation) / 1000
                    rec.ribbon_message = 2
                    rec.message = _('Add Salt and Alkali')
                else:
                    rec.message = ''
                    rec.add_salt = 0
                    rec.add_carbonate = 0
                    rec.ribbon_message = 0
                    rec.message = ''

            else:
                rec.actual_volume = 0
                rec.final_volume = 0
                rec.volume_variation = 0
                rec.message = ''
                rec.add_salt = 0
                rec.add_carbonate = 0
                rec.ribbon_message = 0
                rec.message = ''
            
    @api.onchange('workorder_id')
    def _onchange_workorder_id(self):
        for rec in self:
            if rec.workorder_id:
                prd = rec.workorder_id.production_id
                recipe = prd.color_recipe_id
                ldl = recipe.lab_dev_line_id
                rec.bath_ratio = ldl.bath_ratio
                rec.color_name = ldl.color_name
                rec.color_code = ldl.color_code
                rec.partner_id = ldl.lab_dev_id.partner_id

    @api.onchange('equipment_id')
    def _onchange_equipment_id(self):
        self.alkalis_volume = self.equipment_id.alkalis_vol
        self.dyes_volume = self.equipment_id.color_vol

    def action_register(self):
        self.registry_date = fields.Datetime.now()
        self.workorder_id.batch_ids = [Command.link(self.id)]
        self.state = 'done'