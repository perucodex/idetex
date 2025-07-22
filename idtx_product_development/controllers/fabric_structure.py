# En models/fabric_structure.py (o donde tengas la lógica)
from odoo import http
from odoo.http import request

class FabricLigamentController(http.Controller):

    @http.route('/fabric/ligament/create', type='json', auth='user')
    def create_ligament(self, structure_id, images):
        vals = {'structure_id': structure_id}
        for i, img in enumerate(images[:4]):
            vals[f'image{i+1}'] = img
        new_ligament = request.env['fabric.ligament'].sudo().create(vals)
        return {'id': new_ligament.id}
