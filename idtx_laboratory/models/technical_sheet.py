from odoo import models, fields, api, _

class TechnicalSheet(models.Model):
    _name = 'technical.sheet'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Technical Sheet'

    
