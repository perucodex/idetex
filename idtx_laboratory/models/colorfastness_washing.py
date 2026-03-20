from odoo import models, fields, api, _

class ColorfastnessWashing(models.Model):
    _name = 'colorfastness.washing'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Colorfastness to Washing'

    name = fields.Char('Name', required=True, default=lambda self: _('New'), copy=False)
    color_change_degree = fields.Float('Color Change Degree')
    migration_acetate = fields.Float('Acetate')
    migration_cotton = fields.Float('Cotton')
    migration_nylon = fields.Float('Nylon')
    migration_polyester = fields.Float('Polyester')
    migration_acrylic = fields.Float('Acrylic')
    migration_wool = fields.Float('Wool')
    colorfastness_to_dry_rubbing = fields.Float('Dry')
    colorfastness_to_wet_rubbing = fields.Float('Wet')
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