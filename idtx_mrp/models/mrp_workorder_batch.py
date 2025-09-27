# -*- coding: utf-8 -*-

from odoo import api, Command, fields, models, _
from odoo.exceptions import UserError

class MrpWorkorderBatch(models.Model):
    _name = 'mrp.workorder.batch'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Mrp Workorder Batch'

    # workorder_id = fields.Many2one('mrp.workorder', string='Workorder')
    sequence = fields.Integer('Sequence')
    name = fields.Char('Name', required=True, copy=False, readonly=False, default=lambda self: _('New'))
    batch_date = fields.Date('Batch Date', required=True, default=lambda self: fields.Date.context_today(self))
    wo_roll_ids = fields.Many2many('mrp.workorder.roll', string='Batch Rolls')
    total_weight = fields.Float('Total', compute='_compute_total_weight')
    mrwo_id = fields.Many2one('mrp.routing.workcenter.operation', string='Last Operation')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('batch', 'Batch'),
        ('unbuild', 'Unbuild'),
    ], string='State', default='draft')

    def _compute_total_weight(self):
        for rec in self:
            if rec.wo_roll_ids:
                rec.total_weight = sum(rec.wo_roll_ids.mapped('gross_weight'))
    
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
    
    def clear_rolls(self):
        self.wo_roll_ids = [Command.clear()]
    
    def create_batch(self):
        if any(roll.in_batch for roll in self.wo_roll_ids):
            raise UserError(_('Some rolls are in other batch, please select rolls again.'))
        for roll in self.wo_roll_ids:
            roll.in_batch = True
        self.state = 'batch'

    def unbuild_batch(self):
        # if self.workorder_id:
        #     raise UserError(_('Can\'t unbild a batch already in use, production %s.') %self.workorder_id.production_id.name)
        for roll in self.wo_roll_ids:
            roll.in_batch = False
        self.state = 'unbuild'

    def rebuild_batch(self):
        if any(roll.in_batch for roll in self.wo_roll_ids):
            raise UserError(_('Some rolls are in other batch, can\'t rebuild batch.'))
        for roll in self.wo_roll_ids:
            roll.in_batch = True
        self.state = 'batch'