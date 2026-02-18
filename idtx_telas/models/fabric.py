from odoo import models, fields, api

class IdtxFabricComposition(models.Model):
    _name = 'idtx.fabric.composition'
    _description = 'Composición de Tela'
    _order = 'name'

    name = fields.Char(string='Composición', required=True, translate=True, help="Ej. 100% Algodón, 50/50 Poliéster-Algodón")

class IdtxFabricTag(models.Model):
    _name = 'idtx.fabric.tag'
    _description = 'Etiqueta de Tela'
    _order = 'name'

    name = fields.Char('Nombre Etiqueta', required=True, translate=True)
    color = fields.Integer('Índice de Color')

class IdtxFabric(models.Model):
    _name = 'idtx.fabric'
    _description = 'Tela'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'image.mixin']
    _order = 'name'

    # Basic Information
    name = fields.Char(string='Nombre', required=True, tracking=True, translate=True)
    code = fields.Char(string='Referencia Interna', tracking=True)
    barcode = fields.Char(string='Código de Barras', help="EAN/UPC para identificación.")
    active = fields.Boolean('Activo', default=True, help="Si está desmarcado, permite ocultar la tela sin eliminarla.")
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('development', 'Desarrollo'),
        ('sampling', 'Muestreo'),
        ('validated', 'Validado'),
        ('obsolete', 'Obsoleto')
    ], string='Estado', default='draft', tracking=True)

    # Dates & Files
    date_receipt = fields.Date(string='Fecha Recepción')
    date_validation = fields.Date(string='Fecha Validación')
    datasheet_file = fields.Binary(string='Ficha Técnica')
    datasheet_filename = fields.Char(string='Nombre Archivo Ficha')
    
    # Extended Inputs / Comprehensive Showcase
    priority = fields.Selection([
        ('0', 'Normal'),
        ('1', 'Baja'),
        ('2', 'Alta'),
        ('3', 'Muy Alta')], string="Prioridad", default='0')
    tag_ids = fields.Many2many('idtx.fabric.tag', string='Etiquetas')
    kanban_color = fields.Integer('Índice de Color')
    
    care_instructions = fields.Html('Instrucciones de Cuidado', translate=True)
    
    validity_start = fields.Date('Inicio Validez')
    validity_end = fields.Date('Fin Validez')
    last_inspection = fields.Datetime('Última Inspección')
    
    is_sustainable = fields.Boolean('Material Sostenible')
    fabric_grade = fields.Integer('Grado (1-10)')
    video_url = fields.Char('URL Video')
    
    description = fields.Text(string='Descripción', translate=True)
    # image_1920 = fields.Image("Imagen", max_width=1920, max_height=1920) # Given by image.mixin

    # Technical Specifications
    composition_id = fields.Many2one('idtx.fabric.composition', string='Composición')
    gsm = fields.Float(string='Gramaje (GSM)', help="Gramos por metro cuadrado", tracking=True)
    width = fields.Float(string='Ancho (cm)', tracking=True)
    weaving_type = fields.Selection([
        ('plain', 'Tafetán (Plain)'),
        ('twill', 'Sarga (Twill)'),
        ('satin', 'Satén (Satin)'),
        ('knit', 'Punto (Knit)'),
        ('jacquard', 'Jacquard'),
        ('other', 'Otro')
    ], string='Tipo de Tejido', default='plain')
    
    color = fields.Char(string='Color', translate=True)
    pattern = fields.Char(string='Diseño/Patrón', translate=True)
    thread_count = fields.Char(string='Hilos', help="Ej. 200TC")

    # Commercial & Logistics
    partner_id = fields.Many2one('res.partner', string='Proveedor', domain=[('supplier_rank', '>', 0)])
    currency_id = fields.Many2one('res.currency', 'Moneda', default=lambda self: self.env.company.currency_id)
    cost_price = fields.Monetary(string='Precio Costo')
    list_price = fields.Monetary(string='Precio Venta')
    
    stock_qty = fields.Float(string='Cantidad a Mano', default=0.0, help="Inventario manual")
    uom_name = fields.Char(string='Unidad de Medida', default='m', translate=True, help="Ej. m, kg, yd")
