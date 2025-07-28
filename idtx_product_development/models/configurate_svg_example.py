from odoo import models, fields, api

class ConfigurateSvgExample(models.Model):
    _name = 'configurate.svg.example'
    _description = 'Models SVG Configurate'

    name = fields.Char(string="Name SVG", required=True)
    svg_content = fields.Text(string="Content SVG", required=True)
    
    svg_preview = fields.Html(string="Preview", sanitize=False,compute='_compute_svg_preview')

    @api.depends('svg_content')
    def _compute_svg_preview(self):
        for record in self:
            if record.svg_content:
                record.svg_preview = record.svg_content
            else:
                record.svg_preview = False