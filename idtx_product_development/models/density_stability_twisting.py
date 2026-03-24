from odoo import models, fields, api, _

class DensityStabilityTwisting(models.Model):
    _name = 'density.stability.twisting'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Density Stability Twisting Data'

    name = fields.Char('Name', required=True, default=lambda self: _('New'), copy=False)
    density = fields.Float('Density')
    width = fields.Float('Width')
    width_shrinkage_from = fields.Float('Width Shrinkage From')
    width_shrinkage_to = fields.Float('Width Shrinkage To')
    length_shrinkage_from = fields.Float('Length Shrinkage From')
    length_shrinkage_to = fields.Float('Length Shrinkage To')
    tilt_wash = fields.Float('Tilt Wash')
    twist = fields.Float('Twist')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done'),
    ], string='State', default='draft', tracking=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('density.stability.twisting') or _('New')
        return super().create(vals_list)
    
    def mark_done(self):
        self.state = 'done'

    def mark_draft(self):
        self.state = 'draft'