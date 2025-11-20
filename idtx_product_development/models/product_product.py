from odoo import api, models, _
from odoo.exceptions import ValidationError

class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.model
    def _get_gs1_prefix(self):
        """Devuelve el prefijo GS1 de 7 dígitos (configurable por empresa)."""
        # Puedes cambiarlo por un campo en res.company si lo deseas
        return '7751234'

    # @api.model
    # def _gs1_check_digit(self, gtin_13):
    #     """Calcula el dígito de control GS1."""
    #     if len(gtin_13) != 13 or not gtin_13.isdigit():
    #         raise ValueError("GTIN-13 debe ser 13 dígitos numéricos")
    #     total = sum(int(d) * (1 if idx % 2 == 0 else 3) for idx, d in enumerate(gtin_13))
    #     return str((10 - (total % 10)) % 10)
    
    @api.model
    def _gs1_check_digit(self, gtin_13):
        if len(gtin_13) != 13 or not gtin_13.isdigit():
            raise ValueError("GTIN-13 debe ser 13 dígitos numéricos")
        code = list(gtin_13.zfill(18)[::-1])  # reverse
        code.pop()                          # elimina el último dígito (check)
        evensum = 0
        oddsum = 0
        for i, digit in enumerate(code):
            if i % 2 == 0:
                evensum += int(digit)
            else:
                oddsum += int(digit)
        total = evensum * 3 + oddsum
        return str((10 - (total % 10)) % 10)

    @api.model
    def _generate_unique_gs1(self):
        """Genera un GTIN-14 único dentro del prefijo."""
        prefix = self._get_gs1_prefix()
        # Buscamos el último correlativo usado
        last = self.search([('barcode', '=like', prefix + '%')],
                           order='barcode desc', limit=1)
        if last and last.barcode:
            # Extraemos los 6 dígitos después del prefijo
            last_seq = int(last.barcode[7:13])
            new_seq = last_seq + 1
        else:
            new_seq = 1
        # Limitamos a 6 dígitos (999 999)
        if new_seq > 999999:
            raise ValidationError(_('GS1 sequence exhausted. Contact admin.'))
        seq_str = f'{new_seq:06d}'
        base = prefix + seq_str  # 13 dígitos
        check = self._gs1_check_digit(base)
        return base + check  # 14 dígitos

    @api.model
    def create(self, vals):
        product = super().create(vals)
        if product.product_tmpl_id.is_weaving and not product.barcode:
            product.barcode = self._generate_unique_gs1()
            product.product_tmpl_id.barcode = product.barcode
        return product

    def write(self, vals):
        res = super().write(vals)
        for product in self:
            if product.product_tmpl_id.is_weaving and not product.barcode:
                product.barcode = self._generate_unique_gs1()
                product.product_tmpl_id.barcode = product.barcode
        return res