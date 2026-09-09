import ipaddress
import socket

from odoo import models, fields, api, _
from odoo.exceptions import UserError

# Las 3 etiquetas de la opción (receta), en orden de impresión. El título
# es "LabDip <opción>" y el tipo (Calidad/Tintorería/Laboratorio) va de
# subtítulo para distinguirlas.
LABEL_KINDS = ('Calidad', 'Tintorería', 'Laboratorio')


class ColorRecipe(models.Model):
    _name = 'color.recipe'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Color Recipe'

    name = fields.Char('Name', copy=False, default=lambda self: _('New'))
    lab_dev_line_id = fields.Many2one('lab.dev.line', string='Lab Dip Line', ondelete='cascade')
    lab_dev_id = fields.Many2one(related='lab_dev_line_id.lab_dev_id')
    available_product_ids = fields.Many2many(
        related='lab_dev_line_id.product_ids', string='Available Products')
    # La receta puede ser de UN producto o de una COMBINACIÓN de productos
    # que se tiñen juntos (p.ej. cuerpo JERSEY + cuello RIB): el correlativo,
    # la aprobación y la resolución de receta trabajan por combinación.
    product_ids = fields.Many2many(
        'product.template', 'color_recipe_product_rel', 'recipe_id', 'product_tmpl_id',
        string='Productos', domain="[('id', 'in', available_product_ids)]")
    color_code = fields.Char(related='lab_dev_line_id.color_code')
    color_name = fields.Char(related='lab_dev_line_id.color_name')
    partner_id = fields.Many2one(related='lab_dev_id.partner_id')
    recipe_date = fields.Date('Recipe Date', default=fields.Date.context_today, copy=False)
    color_recipe_process_ids = fields.One2many('color.recipe.process', 'color_recipe_id', string='Color Recipe Process', copy=True)
    lot_ids = fields.One2many('stock.lot', 'color_recipe_id', string='Lotes')
    # color = fields.Char('Color')
    recipe_color_code = fields.Char('Recipe Color Code', readonly=True, copy=False)
    # last_color_code = fields.Char('Last Color Code')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        index=True,
        required=True
    )
    colorfastness_washing_id = fields.Many2one('colorfastness.washing', string='Solidez al Lavado', ondelete='cascade')
    
    # Related fields for direct editing
    color_change_degree = fields.Float(related='colorfastness_washing_id.color_change_degree', readonly=False, store=True)
    migration_acetate = fields.Float(related='colorfastness_washing_id.migration_acetate', readonly=False, store=True)
    migration_cotton = fields.Float(related='colorfastness_washing_id.migration_cotton', readonly=False, store=True)
    migration_nylon = fields.Float(related='colorfastness_washing_id.migration_nylon', readonly=False, store=True)
    migration_polyester = fields.Float(related='colorfastness_washing_id.migration_polyester', readonly=False, store=True)
    migration_acrylic = fields.Float(related='colorfastness_washing_id.migration_acrylic', readonly=False, store=True)
    migration_wool = fields.Float(related='colorfastness_washing_id.migration_wool', readonly=False, store=True)
    colorfastness_to_dry_rubbing = fields.Float(related='colorfastness_washing_id.colorfastness_to_dry_rubbing', readonly=False, store=True)
    colorfastness_to_wet_rubbing = fields.Float(related='colorfastness_washing_id.colorfastness_to_wet_rubbing', readonly=False, store=True)
    light_fastness_light = fields.Float(related='colorfastness_washing_id.light_fastness_light', readonly=False, store=True)
    state = fields.Selection([
        ('test', 'Test'),
        ('approved', 'Approved'),
    ], string='State', default='test', tracking=True)
    observations = fields.Text('Observaciones')
    absorption_factor = fields.Float(
        'Factor de Absorción (L/kg)', digits=(12, 2),
        help='Litros de baño absorbidos por kilogramo de tela.', default=3.00)
    bath_ratio = fields.Integer(
        'Relación de Baño 1:',
        help='Relación de baño 1:N en litros por kilogramo. '
             'Ej.: ingrese 10 para una relación 1:10 (uno a diez).')
    # Legacy (histórico, ya sin UI): grupos de mezcla reemplazados por
    # recipe_lot_ids (sub-recetas por combinación de lotes).
    mixing_group_ids = fields.One2many('color.recipe.mixing.group', 'color_recipe_id', string='Grupos de Mezcla')
    recipe_lot_ids = fields.One2many(
        'color.recipe.lot', 'color_recipe_id', string='Sub-recetas por Lote')
    location_ids = fields.One2many(
        'color.recipe.location', 'recipe_id', string='Ubicaciones')

    def _find_lot_subrecipe(self, lots):
        """Sub-receta cuya combinación de lotes de hilo coincide EXACTAMENTE
        con `lots` (recordset de stock.lot). Devuelve recordset vacío si la
        combinación no está registrada. Compara contra los lotes REALES de
        cada sub-receta (no contra lot_key almacenado) para ser inmune a
        claves desactualizadas. Puede haber VARIAS sub-recetas con la misma
        combinación (opciones de OF y versiones): se prefiere la validada y
        se ignoran las obsoletas."""
        self.ensure_one()
        key = self.env['color.recipe.lot']._make_lot_key(lots.ids)
        matches = self.recipe_lot_ids.filtered(
            lambda r: r.state != 'obsolete'
            and self.env['color.recipe.lot']._make_lot_key(r.lot_ids.ids) == key)
        return matches.sorted(key=lambda r: (r.state != 'validated', r.id))[:1]

    def _product_key(self):
        """Clave canónica de la combinación de productos de la receta."""
        self.ensure_one()
        return tuple(sorted(self.product_ids.ids))

    @api.onchange('lab_dev_line_id', 'available_product_ids')
    def _onchange_default_single_product(self):
        """Si la línea de Lab Dip tiene un único producto, la receta lo toma
        por defecto. Si tiene varios, se deja en blanco para que el usuario
        elija su combinación. No sobreescribe una selección previa."""
        for rec in self:
            if not rec.product_ids and len(rec.available_product_ids) == 1:
                rec.product_ids = rec.available_product_ids

    @api.constrains('recipe_color_code', 'product_ids', 'lab_dev_line_id')
    def _check_recipe_color_code_unique(self):
        # Respaldo contra duplicados: el correlativo es único por combinación
        # de productos dentro de la línea (la asignación además serializa con
        # un lock FOR UPDATE sobre la línea de Lab Dip).
        for rec in self:
            if not rec.recipe_color_code or not rec.lab_dev_line_id:
                continue
            key = rec._product_key()
            dup = rec.lab_dev_line_id.color_recipe_ids.filtered(
                lambda r: r.id != rec.id
                and r.recipe_color_code == rec.recipe_color_code
                and r._product_key() == key)
            if dup:
                raise UserError(_(
                    'El código %(code)s ya existe para esta combinación de '
                    'productos en la línea de Lab Dip.',
                    code=rec.recipe_color_code))

    #=== CRUD METHODS ===#

    @api.model_create_multi
    def create(self, vals_list):
        # Números ya usados por línea de lab dev (para reutilizar huecos).
        used_by_line = {}
        for vals in vals_list:
            # La receta hereda la empresa de su Lab Dip (puede ser la empresa
            # productiva), de modo que la secuencia y el registro queden en
            # la empresa correcta.
            if vals.get('lab_dev_line_id') and not vals.get('company_id'):
                lab_dev = self.env['lab.dev.line'].browse(vals['lab_dev_line_id']).lab_dev_id
                if lab_dev.company_id:
                    vals['company_id'] = lab_dev.company_id.id

            # Si la línea de Lab Dip tiene un único producto, la receta lo toma
            # por defecto (con varios, el usuario elige la combinación).
            if vals.get('lab_dev_line_id') and not vals.get('product_ids'):
                products = self.env['lab.dev.line'].browse(vals['lab_dev_line_id']).product_ids
                if len(products) == 1:
                    vals['product_ids'] = [(6, 0, products.ids)]

            if vals.get('name', _("New")) == _("New"):
                seq_date = fields.Datetime.context_timestamp(
                    self, fields.Datetime.to_datetime(vals['recipe_date'])
                ) if 'recipe_date' in vals else None
                vals['name'] = self.env['ir.sequence'].with_company(vals.get('company_id')).next_by_code(
                    'color.recipe', sequence_date=seq_date) or _("New")

        records = super().create(vals_list)
        # El correlativo es POR COMBINACIÓN DE PRODUCTOS dentro de la línea
        # de Lab Dip (JERSEY 001,002..., RIB 001,002..., JERSEY+RIB 001...).
        # Se asigna DESPUÉS del create para trabajar con product_ids ya
        # resueltos; la lectura de usados bloquea la línea (FOR UPDATE) para
        # serializar asignaciones concurrentes.
        for rec in records:
            if rec.recipe_color_code or not rec.lab_dev_line_id:
                continue
            prefix = rec.lab_dev_line_id.color_code or ''
            if not prefix:
                continue
            key = (rec.lab_dev_line_id.id, rec._product_key())
            if key not in used_by_line:
                used_by_line[key] = self._get_used_recipe_numbers(
                    rec.lab_dev_line_id.id, prefix, rec._product_key(),
                    exclude_ids=records.ids)
            used = used_by_line[key]
            # Toma el menor correlativo libre (reutiliza huecos).
            n = 1
            while n in used:
                n += 1
            used.add(n)
            rec.recipe_color_code = f'{prefix}-{str(n).zfill(3)}'
        return records
    
    def _check_ready_to_approve(self):
        """Una receta aprobada baja a producción: tiene que poder teñirse.
        Sin procesos, sin colorantes o sin relación de baño no sirve, y el
        error recién aparecería en el Taller (o peor, en la máquina)."""
        self.ensure_one()
        if not self.color_recipe_process_ids:
            raise UserError(_(
                'La receta %s no tiene ningún proceso: agrégalo en la pestaña '
                'Receta Desarrollo antes de aprobarla.', self.name))
        colorant_lines = self.color_recipe_process_ids \
            .color_recipe_process_line_ids.filtered(
                lambda l: l.line_type == 'colorants')
        colorants = colorant_lines.child_ids.filtered(
            lambda c: c.product_id and c.factor > 0)
        if colorant_lines and not colorants:
            raise UserError(_(
                'La receta %s no tiene colorantes con porcentaje mayor a 0: '
                'complétalos en la línea COLORANTES antes de aprobarla.',
                self.name))
        if self.bath_ratio <= 0:
            raise UserError(_(
                'La receta %s no tiene relación de baño: sin ella no se puede '
                'calcular el volumen en el Taller.', self.name))
        if self.absorption_factor <= 0:
            raise UserError(_(
                'La receta %s no tiene factor de absorción mayor a 0.',
                self.name))

    def action_approve(self):
        self.ensure_one()
        # No se puede aprobar la opción (receta) si la solidez al lavado de
        # la línea de desarrollo aún no fue negociada/aprobada con el cliente.
        if self.lab_dev_line_id.colorfastness_state != 'client_approved':
            raise UserError(_('Debe primero aprobar la solidez con el cliente.'))
        self._check_ready_to_approve()
        # Pueden coexistir aprobadas una receta unitaria (JERSEY) y una
        # combinada que incluya el mismo producto (JERSEY+RIB). Lo que NO
        # puede repetirse aprobado es la MISMA combinación exacta.
        key = self._product_key()
        duplicated = self.lab_dev_line_id.color_recipe_ids.filtered(
            lambda cr: cr.id != self.id and cr.state == 'approved'
            and cr.color_name == self.color_name
            and cr._product_key() == key)
        if duplicated:
            raise UserError(_(
                'No se puede aprobar esta receta: la receta %(other)s ya está '
                'aprobada para el color %(color)s con la misma combinación de '
                'producto(s) (%(products)s). Retorne esa receta primero.',
                other=duplicated[:1].name,
                color=self.color_name,
                products=', '.join(self.product_ids.mapped('name')),
            ))
        self.state = 'approved'
        self.lab_dev_line_id.state = 'approved'

    def action_return(self):
        """Retorna esta opción a prueba. La línea de LD solo baja a 'test' si
        NO queda ninguna otra opción aprobada: con varias opciones, retornar
        una no debe borrar la aprobación del color (el pedido de venta lee ese
        estado para pintar el color en verde)."""
        lines = self.lab_dev_line_id
        self.state = 'test'
        for line in lines:
            still_approved = line.color_recipe_ids.filtered(
                lambda cr: cr.state == 'approved')
            line.state = 'approved' if still_approved else 'test'

    # ------------------------------------------------------------------
    # Impresión de etiquetas (impresora de códigos de barras de la empresa)
    # ------------------------------------------------------------------
    def action_print_labels(self):
        """Imprime 3 etiquetas de esta opción (receta) en la impresora de
        códigos de barras configurada en la compañía: una para Calidad, otra
        para Tintorería y otra para Laboratorio."""
        self.ensure_one()
        if self.state != 'approved':
            raise UserError(_('Solo se pueden imprimir etiquetas de una receta aprobada.'))
        # Impresora de la empresa de la receta (multicompañía); si no tiene,
        # la de la compañía activa.
        company = self.company_id or self.env.company
        ip = (company.zpl_printer_ip or '').strip()
        if not ip:
            raise UserError(_(
                'La compañía "%s" no tiene configurada una impresora de '
                'códigos de barras (IP). Configúrala en Ajustes.') % company.name)
        zpl = ''.join(self._build_label_zpl(kind) for kind in LABEL_KINDS)
        self._print_zpl_to_network(zpl, ip)
        return True

    def _build_label_zpl(self, kind):
        self.ensure_one()

        def clean(value, limit=38):
            # ZPL: ^ y ~ son comandos; se recortan para no romper el formato.
            text = (str(value or '')).replace('^', ' ').replace('~', ' ')
            return text[:limit]

        fecha = self.recipe_date.strftime('%d/%m/%Y') if self.recipe_date else ''
        full_code = clean(self.recipe_color_code, 40)
        # El código de receta es "<código de color>-<opción>" (ej.
        # 03726145-003): se separa por el último guion.
        base_code, _sep, option = full_code.rpartition('-')
        if not _sep:
            base_code, option = full_code, ''
        # Centrado del Code128: se fuerza subset B (prefijo ">:") para que el
        # ancho sea determinista (11 módulos por carácter + 35 de arranque/
        # checksum/parada), a BY2 = 2 dots por módulo. Con eso se calcula el
        # margen izquierdo para centrarlo en los 600 dots. (El ^FB con
        # justificación central no centra el barcode en la ZD230.)
        module = 2
        bar_width = (11 * len(full_code) + 35) * module
        bar_x = max(0, (600 - bar_width) // 2)
        return f"""^XA
^CI28
^PW600
^LL420
^FO0,16^A0N,38,38^FB600,1,0,C,0^FD{clean(kind, 18)}^FS
^FO20,62^GB560,3,3^FS
^FO20,74^A0N,38,20^FDCliente: {self.partner_id.name}^FS
^FO20,124^A0N,38,22^FDColor: {self.color_name}^FS
^FO20,168^A0N,80,60^FDCódigo: {base_code}^FS
^FO20,246^A0N,38,38^FDFecha: {fecha}^FS
^FO360,246^A0N,38,38^FDOpción: {option}^FS
^FO{bar_x},298^BY{module}^BCN,66,N,N,N^FD>:{full_code}^FS
^FO0,370^A0N,22,22^FB600,1,0,C,0^FD{full_code}^FS
^XZ"""

    def _print_zpl_to_network(self, zpl_code, printer_ip, port=9100):
        """Envía ZPL a la impresora por socket TCP/IP (mismo patrón que el
        sticker de rollos)."""
        try:
            ip = str(ipaddress.ip_address(printer_ip.strip()))
            with socket.create_connection((ip, port), timeout=5) as sock:
                sock.sendall(zpl_code.encode('utf-8'))
        except (socket.error, UnicodeError, ValueError) as e:
            raise UserError(_('No se pudo imprimir: %s') % e)

    def write(self, vals):
        # Si cambia la combinación de productos de la receta (p.ej. tras
        # "Ajustar receta" y elegir otros productos), el correlativo asignado
        # pertenece a la numeración anterior: se recalcula con la nueva.
        if 'product_ids' in vals:
            keys_before = {rec.id: rec._product_key() for rec in self}
        else:
            keys_before = None
        res = super().write(vals)
        if keys_before is not None:
            changed = self.filtered(lambda r: r._product_key() != keys_before[r.id])
            changed._reassign_recipe_color_code()
        return res

    def _get_used_recipe_numbers(self, lab_dev_line_id, prefix, product_key, exclude_ids=None):
        """Correlativos ya usados por las recetas de la MISMA combinación de
        productos en la línea de Lab Dip. Bloquea la fila de la línea
        (FOR UPDATE) para serializar la asignación entre transacciones
        concurrentes: si dos usuarios graban a la vez, el segundo espera el
        commit del primero y ya ve su número tomado. Lee por SQL (post-lock)
        para no depender del caché del ORM."""
        self.flush_model(['lab_dev_line_id', 'product_ids', 'recipe_color_code'])
        self.env.cr.execute(
            'SELECT id FROM lab_dev_line WHERE id = %s FOR UPDATE',
            (lab_dev_line_id,))
        self.env.cr.execute("""
            SELECT cr.recipe_color_code,
                   COALESCE(array_agg(rel.product_tmpl_id ORDER BY rel.product_tmpl_id)
                            FILTER (WHERE rel.product_tmpl_id IS NOT NULL), '{}')
            FROM color_recipe cr
            LEFT JOIN color_recipe_product_rel rel ON rel.recipe_id = cr.id
            WHERE cr.lab_dev_line_id = %s
              AND cr.recipe_color_code IS NOT NULL
              AND cr.id != ALL(%s)
            GROUP BY cr.id
        """, (lab_dev_line_id, list(exclude_ids or [0])))
        target = list(product_key or [])
        used = set()
        for code, products in self.env.cr.fetchall():
            if products != target:
                continue
            if code.startswith(f'{prefix}-'):
                try:
                    used.add(int(code.rsplit('-', 1)[-1]))
                except ValueError:
                    pass
        return used

    def _reassign_recipe_color_code(self):
        """Reasigna el correlativo del código de receta según la numeración
        de la combinación de productos actual (menor número libre entre las
        recetas de la misma combinación de la línea de Lab Dip)."""
        for rec in self:
            line = rec.lab_dev_line_id
            prefix = line.color_code or ''
            if not line or not prefix:
                continue
            used = self._get_used_recipe_numbers(
                line.id, prefix, rec._product_key(), exclude_ids=rec.ids)
            n = 1
            while n in used:
                n += 1
            new_code = f'{prefix}-{str(n).zfill(3)}'
            if rec.recipe_color_code != new_code:
                rec.recipe_color_code = new_code

    def action_adjust_recipe(self):
        self.ensure_one()
        # skip_recipe_log: los procesos copiados no son cambios del usuario
        # (la bitácora de la receta nueva arranca limpia).
        new_recipe = self.with_context(skip_recipe_log=True).copy()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Adjusted Recipe',
            'view_mode': 'form',
            'res_model': self._name,
            'res_id': new_recipe.id,
            'target': 'current',
        }

    def unlink(self):
        for rec in self:
            if rec.state == 'approved':
                raise UserError(_('Can\'t delete a recipe in approved state.'))
        return super().unlink()