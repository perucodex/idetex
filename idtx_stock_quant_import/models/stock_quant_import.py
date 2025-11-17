import base64, io
from odoo import api, fields, models, _
from odoo.fields import Command
from openpyxl import load_workbook
from odoo.exceptions import UserError
import xlrd

class StockQuantImport(models.Model):
    _name = 'stock.quant.import'
    _description = 'Stock Quant Import'
    _order = 'date desc'

    name = fields.Char('Reference', default='New', readonly=True, copy=False)
    date = fields.Date(default=fields.Date.context_today, required=True)
    location_id = fields.Many2one('stock.location', string='Location')
    file = fields.Binary(string='Excel File', required=True, attachment=True)
    filename = fields.Char()
    state = fields.Selection([('draft', 'Draft'), ('done', 'Done')],
                             default='draft', string='Status', copy=False)

    line_ids = fields.One2many('stock.quant.import.line',
                               'import_id', string='Lines', readonly=True)

    # ------------------------------------------------------------------
    # Botón principal
    # ------------------------------------------------------------------
    def action_validate(self):
        StockQuant = self.env['stock.quant']
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only draft imports can be validated.'))
            if not rec.file:
                raise UserError(_('Please upload an Excel file.'))

            raw = base64.b64decode(rec.file)
            ext = (rec.filename or '').lower().split('.')[-1]

            if ext == 'xlsx':
                try:
                    wb = load_workbook(io.BytesIO(raw), read_only=True)
                    ws = wb.active
                    header = {cell.value: idx for idx, cell in enumerate(next(ws.iter_rows(max_row=1)), 1)}
                    rows = list(ws.iter_rows(min_row=2, values_only=True))
                except Exception as e:
                    raise UserError(_('Error reading .xlsx: %s') % str(e))

            elif ext == 'xls':
                try:
                    book = xlrd.open_workbook(file_contents=raw)
                    ws = book.sheet_by_index(0)
                    header = {ws.cell_value(0, col): col + 1 for col in range(ws.ncols)}
                    rows = [
                        [ws.cell_value(r, c) for c in range(ws.ncols)]
                        for r in range(1, ws.nrows)
                    ]
                except Exception as e:
                    raise UserError(_('Error reading .xls: %s') % str(e))
            else:
                raise UserError(_('Only .xls or .xlsx files are allowed.'))

            # ws = wb.active

            # Cabecera mínima: location, product_code, qty
            # header = {cell.value: idx for idx, cell in enumerate(next(ws.iter_rows(max_row=1)), 1)}
            for col in ('product_code', 'product_name', 'refe_interna', 'qty', 'ident_lote', 'lot', 'color', 'color_name'):
                if col not in header:
                    raise UserError(_('Column %s not found in Excel sheet.') % col)

            # rows = list(ws.iter_rows(min_row=2, values_only=True))
            if not rows:
                raise UserError(_('The sheet is empty.'))

            # Cachear ubicaciones y productos
            # Location = self.env['stock.location']
            Product = self.env['product.product']
            Color = self.env['color.recipe']
            LabDev = self.env['lab.dev']
            Analysis = self.env['product.analysis']

            # Borrar líneas previas (por si re-validan)
            rec.line_ids.unlink()

            for row in rows:
                # location_name = row[header['location'] - 1]
                product_code = row[header['product_code'] - 1]
                product_name = row[header['product_name'] - 1]
                refe_interna = row[header['refe_interna'] - 1]
                qty = row[header['qty'] - 1]
                ident_lote = row[header['ident_lote'] - 1]
                lot_name = row[header['lot'] - 1]
                color_code = row[header['color'] - 1]
                color_name = row[header['color_name'] - 1]

                if not (product_code and qty):
                    continue

                # location = Location.search([('complete_name', '=', location_name)], limit=1)
                # if not location:
                #     raise UserError(_('Location %s not found.') % location_name)

                product = Product.search([('default_code', '=', product_code)], limit=1)
                if not product:
                    # raise UserError(_('Product %s not found.') % product_code)
                    pf = self.env['product.family'].search([('code','=', product_code[:2])])
                    pa = self.env['product.appearance'].search([('code','=', product_code[7:9])])
                    pb = self.env['product.fiber'].search([('code','=', product_code[4:5])])
                    pt = self.env['product.title'].search([('code','=', product_code[2:4])])
                    gauge_id = self.env['product.gauge'].search([('code','=', product_code[5:7])])
                    width = product_code[9:12]
                    density = product_code[12:15]
                    analysis = Analysis.create({
                        'partner_id': self.env.company.partner_id.id,
                        'product_description': product_name,
                        'product_family_id': pf.id,
                        'product_appearance_id': pa.id,
                        'product_fiber_id': pb.id,
                        'product_title_id': pt.id,
                        'gauge_id': gauge_id.id,
                        'density': density,
                        'width': width,
                        'standard_width': width,
                        'product_code': product_code,
                    })
                    analysis.action_product()
                    product = analysis.product_id
                    product.available_in_pos = True
                color = Color.search([('color_code','=', color_code)], limit=1)
                if not color:
                    # raise UserError(_('Color code %s not found') % color_code)
                    cpt = self.env['color.process.type'].search([('code','=',color_code[:2])])
                    cr = self.env['color.range'].search([('code','=',color_code[2:3])])
                    ci = self.env['color.intensity'].search([('code','=',color_code[3:4])])
                    labdev = LabDev.create({
                        'partner_id': self.env.company.partner_id.id, 
                        'lab_dev_line_ids': [
                            Command.create({
                                'product_id':product.id,
                                'color_name': color_name,
                                'color_process_type_id': cpt.id,
                                'color_range_id': cr.id,
                                'color_intensity_id': ci.id,
                                'color_code': color_code,
                                'color_recipe_ids': [Command.create({'state': 'approved',})],
                            }),
                        ]
                    })
                    color = labdev.lab_dev_line_ids.color_recipe_ids
                
                # Crear batch
                batch = self.env['mrp.workorder.batch'].create({
                    'name': ident_lote,
                    'state': 'batch',
                })

                # Crear rollo
                roll = self.env['mrp.production.roll'].create({
                    'batch_id': batch.id,
                    'name': refe_interna,
                    'product_id': product.id,
                    'quantity': 1,
                    'gross_weight': qty,
                    'net_weight': qty,
                })

                # Crear lote
                lot = self.env['stock.lot'].create({
                    'name': lot_name,
                    'product_id': product.id,
                    'color_recipe_id': color.id,
                    'roll_id': roll.id,
                })

                roll.lot_id = lot

                # Crear quant
                quant = StockQuant.create({
                    'product_id': product.id,
                    'location_id': rec.location_id.id,
                    'inventory_quantity': float(qty),
                    'lot_id': lot.id
                })
                quant.action_apply_inventory()

                # Línea de auditoría
                self.env['stock.quant.import.line'].create({
                    'import_id': rec.id,
                    'quant_id': quant.id,
                    'location_id': rec.location_id.id,
                    'product_id': product.id,
                    'quantity': float(qty),
                })

            rec.state = 'done'
        return True

    # ------------------------------------------------------------------
    # Secuencia
    # ------------------------------------------------------------------
    @api.model
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('stock.quant.import') or 'New'
        return super().create(vals_list)


class StockQuantImportLine(models.Model):
    _name = 'stock.quant.import.line'
    _description = 'Stock Quant Import Line'

    import_id = fields.Many2one('stock.quant.import', ondelete='cascade')
    quant_id = fields.Many2one('stock.quant', string='Quant', readonly=True)
    location_id = fields.Many2one('stock.location', readonly=True)
    product_id = fields.Many2one('product.product', readonly=True)
    quantity = fields.Float(digits='Product Unit of Measure', readonly=True)