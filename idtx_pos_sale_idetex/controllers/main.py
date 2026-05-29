# -*- coding: utf-8 -*-

from odoo.addons.point_of_sale.controllers.main import PosController

class IdtxPosController(PosController):

    def _get_pos_service_worker(self):
        """
        Hereda el método que sirve el Service Worker al navegador y modifica
        su cuerpo en memoria antes de responder al cliente.
        
        Esto permite añadir la regla de bypass para descargas de PDFs ('download')
        de forma dinámica y elegante, sin alterar el archivo del core de Odoo.
        """
        body = super()._get_pos_service_worker()
        
        target_str = 'url.includes("web/dataset")'
        if target_str in body and 'url.includes("download")' not in body:
            # Insertamos el bypass de descarga antes de la exclusión original
            body = body.replace(
                target_str,
                'url.includes("download") ||\n        url.includes("web/dataset")'
            )
        return body
