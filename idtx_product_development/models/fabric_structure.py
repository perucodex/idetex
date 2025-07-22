from odoo import models, fields, api
import json
import base64

class FabricStructure(models.Model):
    _name = 'fabric.structure'
    _description = 'Fabric Structure'

    name = fields.Char("Name", default="New Drag Area")
    ligament_ids = fields.One2many('fabric.ligament', 'structure_id', string="Ligaments")
    image_palette_ids = fields.Many2many('fabric.image.palette', string="Imágenes Prediseñadas")
    image_palette_data = fields.Text(string="Imágenes JSON", compute="_compute_image_palette_data")

    @api.depends('image_palette_ids.image')
    def _compute_image_palette_data(self):
        for rec in self:
            images_data = []
            for img in rec.image_palette_ids:
                if img.image:
                    # Verificar si es bytes y convertir a string
                    image_base64 = img.image
                    if isinstance(image_base64, bytes):
                        image_base64 = image_base64.decode('utf-8')
                    images_data.append({
                        'id': img.id,
                        'src': image_base64,
                    })
            rec.image_palette_data = json.dumps(images_data)

class FabricLigament(models.Model):
    _name = 'fabric.ligament'
    _description = 'Ligament'
    
    name = fields.Char("Nombre")
    structure_id = fields.Many2one('fabric.structure', string="Structure")
    image1 = fields.Image("Image 1", max_width=64, max_height=64)
    image2 = fields.Image("Image 2", max_width=64, max_height=64)
    image3 = fields.Image("Image 3", max_width=64, max_height=64)
    image4 = fields.Image("Image 4", max_width=64, max_height=64)
    image_preview_html = fields.Html(string="Vista Imágenes", sanitize=False)
    ligament_preview = fields.Char('Ligament Preview', default='')

    @api.onchange('image1', 'image2', 'image3', 'image4')
    def _onchange_image_preview_html(self):
        for rec in self:
            html = '<div style="display:flex">'
            for img in [rec.image1, rec.image2, rec.image3, rec.image4]:
                if img:
                    src = f'data:image/png;base64,{img.decode("utf-8")}'
                    html += f'<img src="{src}" style="width:32px;height:32px;margin-right:2px;" />'
            html += '</div>'
            rec.image_preview_html = html

class FabricImagePalette(models.Model):
    _name = 'fabric.image.palette'
    _description = 'Fabric Predefined Images'

    name = fields.Char("Nombre")
    image = fields.Image("Imagen", max_width=64, max_height=64)
