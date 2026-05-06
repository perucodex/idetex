from odoo import models, fields, api, _

class ColorfastnessWashing(models.Model):
    _name = 'colorfastness.washing'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Colorfastness to Washing'

    name = fields.Char('Name', required=True, default=lambda self: _('New'), copy=False)
    color_change_degree = fields.Float('Color Change Degree', default=0.04)
    migration_acetate = fields.Float('Acetate', default=0.03)
    migration_cotton = fields.Float('Cotton', default=0.03)
    migration_nylon = fields.Float('Nylon', default=0.03)
    migration_polyester = fields.Float('Polyester', default=0.03)
    migration_acrylic = fields.Float('Acrylic', default=0.03)
    migration_wool = fields.Float('Wool', default=0.03)
    colorfastness_to_dry_rubbing = fields.Float('Dry', default=0.04)
    colorfastness_to_wet_rubbing = fields.Float('Wet', default=0.03)
    light_fastness_light = fields.Float('Luz')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done'),
    ], string='State', default='draft', tracking=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('colorfastness.washing') or _('New')
        return super().create(vals_list)
    
    def mark_done(self):
        self.state = 'done'

    def mark_draft(self):
        self.state = 'draft'