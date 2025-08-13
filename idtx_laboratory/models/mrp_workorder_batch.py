# -*- coding: utf-8 -*-

from odoo import api, Command, fields, models, _
from odoo.exceptions import UserError

class MrpWorkorderBatch(models.Model):
    _name = 'mrp.workorder.batch'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Mrp Workorder Batch'

    name = fields.Char('Name', required=True, copy=False, readonly=False, default=lambda self: _('New'))
    batch_date = fields.Date('Batch Date', required=True, default=lambda self: fields.Date.context_today(self))
    # production_type = fields.Selection([
    #     ('dyeing', 'Dyeing'),
    #     ('weaving', 'Weaving'),
    #     ('finishing', 'Finishing'),       
    # ], string='production_type')
    mrp_workcenter_operation_id = fields.Many2one('mrp.routing.workcenter.operation', string='Operation')
    workcenter_operation_id_domain = fields.Char(compute='_compute_workcenter_operation_id_domain')
    wo_roll_ids = fields.Many2many('mrp.workorder.roll', string='Batch Rolls')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('batch', 'Batch'),
        ('unbuild', 'Unbuild'),
    ], string='State', default='draft')

    #=== CRUD METHODS ===#

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _("New")) == _("New"):
                seq_date = fields.Datetime.context_timestamp(
                    self, fields.Datetime.to_datetime(vals['batch_date'])
                ) if 'batch_date' in vals else None
                vals['name'] = self.env['ir.sequence'].with_company(vals.get('company_id')).next_by_code(
                    'mrp.workorder.batch', sequence_date=seq_date) or _("New")

        return super().create(vals_list)
    
    @api.onchange('wo_roll_ids')
    def _onchange_wo_roll_ids(self):
        if not self.wo_roll_ids:
            self.mrp_workcenter_operation_id = False
    
    def clear_rolls(self):
        self.wo_roll_ids = [Command.clear()]
        self.mrp_workcenter_operation_id = False
    
    def create_batch(self):
        if any(roll.in_batch for roll in self.wo_roll_ids):
            raise UserError(_('Some rolls are in other batch, please select rolls again.'))
        for roll in self.wo_roll_ids:
            roll.in_batch = True
        self.state = 'batch'

    def unbuild_batch(self):
        for roll in self.wo_roll_ids:
            roll.in_batch = False
        self.state = 'unbuild'

    def rebuild_batch(self):
        if any(roll.in_batch for roll in self.wo_roll_ids):
            raise UserError(_('Some rolls are in other batch, can\'t rebuild batch.'))
        for roll in self.wo_roll_ids:
            roll.in_batch = True
        self.state = 'batch'

    @api.depends('wo_roll_ids')
    def _compute_workcenter_operation_id_domain(self):
        operations = self.env['mrp.routing.workcenter.operation']
        for roll in self.wo_roll_ids:
            if not operations:
                operations += roll.workorder_id.production_id.workorder_ids.mrwo_id
            else:
                operations &= roll.workorder_id.production_id.workorder_ids.mrwo_id
        self.workcenter_operation_id_domain = str([('id','in',operations.ids),('is_weaving','=',False)])