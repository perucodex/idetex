from odoo import models, fields, Command

class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    lab_dev_id = fields.Many2one('lab.dev', string='Lab Dev')

    # def action_confirm(self):
    #     res = super().action_confirm()

    #     LabDev = self.env['lab.dev']
    #     today = fields.Date.context_today(self)

    #     # Agrupar líneas por product_template_id
    #     product_map = {}
    #     for line in self.order_line:
    #         product = line.product_template_id
    #         # Mas adelante unificar con desarrollo de producto si la operacion de la bom_ids del producto tiene una
    #         # operación con un flag que indique que lleva procesos y entonces es necesario una ld ej:
    #         # if product not in product_map and product.bom_ids.process_ids.tiene_flag:
    #         if product not in product_map:
    #             # Crear una sola lab.dev por producto
    #             lab_dev = LabDev.create({
    #                 # 'product_color_id': line.product_color_id.id,
    #                 'sale_order_id': self.id,
    #                 'product_id': product.id,
    #                 'lab_dev_date': today,
    #             })
    #             product_map[product] = lab_dev
    #         # Asociar la lab.dev a cada línea que tenga ese producto
    #         line.lab_dev_id = product_map[product]
    #         # Crear el detalle de las líneas
    #         line.lab_dev_id.lab_dev_line_ids.create({
    #             'lab_dev_id': line.lab_dev_id.id,
    #             'product_color_id': line.product_color_id.id,
    #         })

    #     return res

    def action_confirm(self):
        res = super().action_confirm()

        LabDev = self.env['lab.dev']
        today = fields.Date.context_today(self)
        # Crear una sola lab.dev para la orden
        lab_dev = LabDev.create({
            'lab_dev_date': today,
            'sale_order_id': self.id,
            'lab_dev_line_ids': [Command.create({
                 'product_id': line.product_id.id,
                 'color_name': line.product_color_id.name,
            }) for line in self.order_line]
        })

        self.lab_dev_id = lab_dev

        return res
