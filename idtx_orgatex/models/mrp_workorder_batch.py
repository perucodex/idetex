import logging
import re

from markupsafe import Markup

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MrpWorkorderBatch(models.Model):
    """Envío de la receta de la partida a ORGATEX (sistema de teñido).

    La receta que se manda es la de la SUB-RECETA seleccionada en la partida
    (combinación de lotes de hilo), con sus procesos y factores ya ajustados
    por hilado — la misma fuente del reporte 'Receta de Tinte'.
    """
    _inherit = ['mrp.workorder.batch', 'orgatex.connection.mixin']

    orgatex_dyelot = fields.Char(
        'Dyelot ORGATEX', copy=False, readonly=True, index=True,
        help='Número con el que la partida quedó registrada en ORGATEX '
             '(dígitos de la partida + cantidad de reprocesos).')
    orgatex_machine_id = fields.Many2one(
        'maintenance.equipment', string='Máquina ORGATEX', copy=False,
        domain="[('orgatex_machine_no', '!=', False)]",
        help='Máquina de teñido en la que corre la partida. Debe estar '
             'homologada con ORGATEX.')
    orgatex_state = fields.Selection([
        ('pending', 'No enviada'),
        ('sent', 'Enviada'),
        ('error', 'Error'),
    ], string='Estado ORGATEX', default='pending', copy=False, readonly=True)
    orgatex_sent_date = fields.Datetime('Enviada a ORGATEX', copy=False, readonly=True)
    orgatex_message = fields.Char('Detalle ORGATEX', copy=False, readonly=True)

    # ------------------------------------------------------------------
    # Datos de la partida en formato ORGATEX
    # ------------------------------------------------------------------
    def _orgatex_dyelot_number(self):
        """Dyelot = dígitos del nombre de la partida + cantidad de reprocesos,
        con la partida rellenada a 6 dígitos (WB00046 con 0 reprocesos ->
        '0000460'). Es la convención de TEXPLUS (3326053 = partida 332605,
        reproceso 3): el importador espera SIEMPRE 7 dígitos — los dyelots de
        6 en la tabla son los nativos de ORGATEX espejados, no importados."""
        self.ensure_one()
        digitos = re.sub(r'\D', '', self.name or '')
        if not digitos:
            raise UserError(_(
                'La partida %s no tiene dígitos en su nombre: ORGATEX solo '
                'acepta números como dyelot.') % self.name)
        return '%s%s' % (digitos.zfill(6), self.reprocess_count or 0)

    def _orgatex_header_vals(self, data):
        """Cabecera (Dyelots). Los textos van recortados al ancho de columna
        de ORGATEX (varchar(20)); si no, SQL Server rechaza el INSERT.

        Protocolo del host de ORGATEX (verificado observando en vivo las
        inserciones de TEXPLUS, ago-2026): la fila entra con ImportState=4
        (solicitud de importación) y SIN DyelotRefNo/State/RecipeTransferState
        — todos esos los pone el servicio al procesarla (asigna el correlativo
        de trabajo, crea el batch en la base ORGATEX y pasa ImportState a 10,
        o deja 20 + ImportError si la receta no valida). Anunciar otro
        ImportState hace que el servicio busque un batch inexistente y
        rechace con ImportError=8002."""
        self.ensure_one()

        def corta(valor, largo):
            return (valor or '').strip()[:largo] or None

        partner = self.partner_ids[:1]
        cliente = ' '.join(filter(None, [partner.ref, partner.name])) if partner else ''
        productos = data['rolls'].mapped('product_id')[:1]
        articulo = ' '.join(filter(None, [productos.default_code, productos.name])) \
            if productos else ''
        vals = {
            'Dyelot': self._orgatex_dyelot_number(),
            'ReDye': 0,
            'Machine': self.orgatex_machine_id.orgatex_machine_no,
            'ProcedureNo': 0,
            'ProgramCreationType': 1,   # receta creada por sistema externo
            'RecipeSystem': 2,          # 2 = receta de host externo
            'ImportState': 4,           # 4 = solicitud: el servicio la importa
            'ImportError': 0,
            'RecipeState': 40,
            'RecipeError': 0,
            'Color': 0,
            'ProcessType1': 0,
            'ProcessType2': 0,
            'TypeOfProcedureNo': 0,
            'RecipeTransferError': 0,
            'EmissionCalcError': 0,
            'FlagBatchWeight': 0,
            'FlagLiquorAmount': 0,
            'WeightState': 0,
            'SuppressAutoPrint': 0,
            'RecalcRecipeMode': 0,
            'CalcRecipeId': 0,
            'Customer': corta(cliente, 20),
            'Article': corta(articulo, 20),
            'ColourNo': corta(self.color_code, 20),
            'ColourDescript': corta(self.color_name, 20),
            # RecipeNo referencia la tabla Recipes de ORGATEX, que solo tiene
            # la receta genérica '1234' (la que manda TEXPLUS en todos sus
            # dyelots). La receta real viaja en las líneas.
            'RecipeNo': '1234',
            'Weight': data['kilos'],
            'Length': data['meters'],   # metros lineales: Longitud (Cuerda) en planta
            'LiquorRatio': data['rb'],
            'LiquorQuantity': data['volume'],
        }
        vals.update({'Parameter%s' % i: 0.0 for i in range(5, 21)})
        return vals

    def _orgatex_machine_parameters(self, cur, data):
        """Parámetros de partida que dependen del TIPO de máquina.

        Cada grupo de máquinas de ORGATEX muestra los slots Parameter5-20
        como campos distintos (config en GBC_TC_BatchParameter de la base
        ORGATEX): el mismo slot es 'Humedad residual' en una Thies y
        'Tipo H2o Salmuera' en una Danitech, así que hay que llenar el slot
        correcto según el grupo (Machines.MGroupNo) de la máquina elegida."""
        cur.execute('SELECT MGroupNo FROM Machines WHERE MachineNo = ?',
                    self.orgatex_machine_id.orgatex_machine_no)
        fila = cur.fetchone()
        grupo = (fila and fila[0]) or 0
        kilos, metros = data['kilos'], data['meters']
        fac_abs = data['fac_abs'] or 0.0
        params = {}
        if grupo == 1:
            # Thies iMaster: Humedad residual [%] (la Longitud Cuerda [m]
            # sale de la columna Length de la cabecera).
            params['Parameter15'] = fac_abs * 100.0
        elif grupo in (2, 9, 10):
            # Danitech (2) y Brazzoli (9/10): Absorción [l/kg] y Peso Tejido
            # [gr/mt lineal] (este último solo lo muestra la pantalla
            # Brazzoli, pero se llena igual en Danitech).
            params['Parameter13'] = fac_abs
            if metros:
                params['Parameter5'] = kilos * 1000.0 / metros
        elif 3 <= grupo <= 8:
            # MCS/MS: Absorción [:1] y LT baño 2 [l] = litros de baño libres
            # (volumen total menos lo que absorbe la tela: kilos × fac.abs).
            params['Parameter17'] = fac_abs
            params['Parameter9'] = max(data['volume'] - kilos * fac_abs, 0.0)
        return params

    def _orgatex_lines(self, data):
        """Procesos (Dyelot_Procedure) y químicos (Dyelot_Recipe).

        Las cantidades salen del MISMO cálculo del reporte Receta de Tinte
        (g/L sobre el volumen, % sobre los kilos, tablas CF resueltas), pero
        ORGATEX las quiere en KILOS."""
        self.ensure_one()
        procedimientos, recetas = [], []
        counter = 0
        sin_homologar_proc, sin_codigo_prod = [], []
        for indice, proceso in enumerate(data['processes'], start=1):
            base = proceso['process'].base_process_id
            if not base.orgatex_treatment_no:
                sin_homologar_proc.append('%s %s' % (base.code or '', base.name or ''))
            else:
                # El slot 1 del programa está RESERVADO al tratamiento 1
                # ('Comenzar Tintura'): en 2000 dyelots importados ninguno
                # lleva otro tratamiento en TreatmentCnt=1, y los que no
                # traen ese paso arrancan en 2 (p.ej. 3311902). Poner un
                # tratamiento cualquiera en el 1 hace fallar el import.
                procedimientos.append({
                    'TreatmentCnt': indice + 1,
                    'TreatmentNo': base.orgatex_treatment_no,
                })
            for linea in proceso['lines']:
                producto = linea['line'].product_id
                codigo = (producto.default_code or '').strip()
                if not codigo:
                    sin_codigo_prod.append(producto.name)
                    continue
                counter += 1
                kilos = (linea['grams'] or 0.0) / 1000.0
                recetas.append({
                    'CorrectionNumber': 0,
                    # CallOff = N° de llamado de dosificación de la línea, el
                    # mismo del reporte Receta de Tinte: acumulativo entre
                    # procesos y compartido por los productos de un mismo
                    # ingreso a máquina (igual numeran los dyelots TEXPLUS).
                    'CallOff': linea['order'],
                    'Counter': counter,
                    'ProductName': (producto.name or '')[:50],
                    'ProductShortName': codigo[:20],
                    'ProductCode': codigo[:30],
                    'Amount': kilos,
                    'AmountPerMachine': kilos,
                    'Unit': 'kg',
                    'KindOfStation': 2,
                    # Producción deja NULL para químicos y 1 para colorantes.
                    'KindOfProduct': 1 if producto.is_colorant else None,
                    'State': 0,
                    'SpecificWeight': 1.0,
                    'NoOfStation': 0,
                })
        if sin_homologar_proc:
            raise UserError(_(
                'Estos procesos de la receta no están homologados con un '
                'tratamiento de ORGATEX:\n- %s\n\nHomológalos en '
                'Laboratorio > Procesos Base (campo N° Tratamiento ORGATEX).'
            ) % '\n- '.join(sin_homologar_proc))
        if sin_codigo_prod:
            raise UserError(_(
                'Estos productos de la receta no tienen código interno y '
                'ORGATEX los identifica por código:\n- %s'
            ) % '\n- '.join(sin_codigo_prod))
        if not recetas:
            raise UserError(_('La receta no tiene líneas de químicos que enviar.'))
        return procedimientos, recetas

    # ------------------------------------------------------------------
    # Envío
    # ------------------------------------------------------------------
    def action_send_to_orgatex(self):
        self.ensure_one()
        if not self.recipe_lot_id:
            raise UserError(_(
                'La partida no tiene sub-receta seleccionada: elígela antes '
                'de enviarla a ORGATEX.'))
        if self.recipe_lot_id.state != 'validated':
            raise UserError(_(
                'La sub-receta %s no está validada por laboratorio.')
                % self.recipe_lot_id.display_name)
        if not self.orgatex_machine_id:
            raise UserError(_(
                'Selecciona la máquina de teñido (homologada con ORGATEX) '
                'antes de enviar la receta.'))
        if not self._orgatex_write_enabled():
            raise UserError(_(
                'La escritura hacia ORGATEX está deshabilitada en este '
                'servidor (parámetro idtx_orgatex.enabled).'))

        data = self._get_dye_report_data()
        if not data['kilos']:
            raise UserError(_('La partida no tiene peso: ORGATEX lo necesita '
                              'para calcular las cantidades.'))
        if not data['rb']:
            raise UserError(_('La sub-receta no tiene relación de baño: sin '
                              'ella no se puede calcular el volumen.'))
        cabecera = self._orgatex_header_vals(data)
        procedimientos, recetas = self._orgatex_lines(data)
        dyelot = cabecera['Dyelot']

        conn = self._orgatex_connect()
        cur = conn.cursor()
        try:
            cabecera.update(self._orgatex_machine_parameters(cur, data))
            # (Dyelot, ReDye) es índice ÚNICO en ORGATEX: un reenvío reemplaza
            # lo anterior en vez de reventar con violación de clave.
            cur.execute('SELECT ImportState, DyelotRefNo, State FROM Dyelots '
                        'WHERE Dyelot = ? AND ReDye = 0', dyelot)
            fila = cur.fetchone()
            if fila:
                # State >= 25 = la partida ya se cargó en el controlador de la
                # máquina (o ya corre): la receta ya no se toca desde Odoo.
                # Mientras solo exista el batch en oficina (10/20) el reenvío
                # es válido: se re-importa como reintento.
                if (fila[2] or 0) >= 25:
                    raise UserError(_(
                        'La partida %(dl)s ya está cargada en la máquina en '
                        'ORGATEX (estado %(st)s): no se puede reemplazar su '
                        'receta desde Odoo.', dl=dyelot, st=fila[2]))
                # Si el servicio ya le había asignado su número de trabajo
                # (DyelotRefNo), se conserva: así el reintento re-importa al
                # MISMO batch, igual que hace TEXPLUS (ImportState=4 de nuevo
                # manteniendo el RefNo).
                if fila[1]:
                    cabecera['DyelotRefNo'] = fila[1]
                for tabla in ('Dyelot_Recipe', 'Dyelot_Procedure', 'Dyelots'):
                    cur.execute(f'DELETE FROM {tabla} WHERE Dyelot = ? AND ReDye = 0', dyelot)

            columnas = ', '.join(cabecera)
            marcas = ', '.join(['?'] * len(cabecera))
            cur.execute(f'INSERT INTO Dyelots ({columnas}) VALUES ({marcas})',
                        list(cabecera.values()))

            for linea in procedimientos:
                cur.execute(
                    'INSERT INTO Dyelot_Procedure (Dyelot, ReDye, TreatmentCnt, TreatmentNo) '
                    'VALUES (?, ?, ?, ?)',
                    dyelot, 0, linea['TreatmentCnt'], linea['TreatmentNo'])

            for linea in recetas:
                cols = ', '.join(['Dyelot', 'ReDye'] + list(linea))
                marks = ', '.join(['?'] * (len(linea) + 2))
                cur.execute(f'INSERT INTO Dyelot_Recipe ({cols}) VALUES ({marks})',
                            [dyelot, 0] + list(linea.values()))

            conn.commit()
        except UserError:
            conn.rollback()
            raise
        except Exception as exc:
            conn.rollback()
            _logger.exception('ORGATEX: fallo al insertar el dyelot %s', dyelot)
            self.write({'orgatex_state': 'error',
                        'orgatex_message': str(exc)[:250]})
            raise UserError(_('ORGATEX rechazó la receta de %(dl)s:\n%(err)s',
                              dl=dyelot, err=exc))
        finally:
            cur.close()
            conn.close()

        self.write({
            'orgatex_dyelot': dyelot,
            'orgatex_state': 'sent',
            'orgatex_sent_date': fields.Datetime.now(),
            'orgatex_message': _('%(p)s procesos, %(q)s químicos',
                                 p=len(procedimientos), q=len(recetas)),
        })
        # Markup para que el chatter renderice el HTML; los valores se
        # interpolan vía Markup.__mod__, que los escapa.
        self.message_post(body=Markup(_(
            'Receta enviada a ORGATEX como dyelot <b>%(dl)s</b> en la máquina '
            '%(maq)s: %(p)s procesos y %(q)s químicos (sub-receta %(sub)s, '
            '%(kg).2f kg, RB 1:%(rb)s).')) % {
                'dl': dyelot, 'maq': self.orgatex_machine_id.orgatex_machine_no,
                'p': len(procedimientos), 'q': len(recetas),
                'sub': self.recipe_lot_id.display_name,
                'kg': data['kilos'], 'rb': data['rb']})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _('Receta enviada a ORGATEX'),
                'message': _('Dyelot %(dl)s en %(maq)s: %(p)s procesos, '
                             '%(q)s químicos.',
                             dl=dyelot, maq=self.orgatex_machine_id.orgatex_machine_no,
                             p=len(procedimientos), q=len(recetas)),
                'sticky': False,
            },
        }

    def action_preview_orgatex_payload(self):
        """Vista previa de lo que se enviaría (sin tocar ORGATEX): sirve para
        revisar cantidades y homologaciones antes del envío real."""
        self.ensure_one()
        if not self.recipe_lot_id:
            raise UserError(_('La partida no tiene sub-receta seleccionada.'))
        data = self._get_dye_report_data()
        cabecera = dict(self._orgatex_header_vals(data),
                        Machine=self.orgatex_machine_id.orgatex_machine_no or '—')
        procedimientos, recetas = self._orgatex_lines(data)
        # Markup para que el chatter renderice el HTML; los valores dinámicos
        # (códigos/nombres de producto) se escapan al interpolar con %.
        fila = Markup(
            '<tr><td>%s</td><td>%s</td><td>%s</td><td class="text-end">%.4f</td>'
            '<td>%s</td></tr>')
        lineas = Markup('').join(
            fila % (r['CallOff'], r['ProductCode'],
                    r['ProductName'], r['Amount'], r['Unit'])
            for r in recetas)
        cuerpo = Markup(_(
            '<b>Vista previa del envío a ORGATEX</b><br/>'
            'Dyelot <b>%(dl)s</b> · máquina %(maq)s · %(kg).2f kg · '
            'RB 1:%(rb)s · volumen %(vol).1f L<br/>'
            'Procesos: %(procs)s'
            '<table class="table table-sm"><tr><th>Paso</th><th>Código</th>'
            '<th>Producto</th><th>Cantidad</th><th>Unidad</th></tr>%(lineas)s</table>')) % {
            'dl': cabecera['Dyelot'], 'maq': cabecera['Machine'],
            'kg': data['kilos'], 'rb': data['rb'], 'vol': data['volume'],
            'procs': ', '.join('%s→T%s' % (p['TreatmentCnt'], p['TreatmentNo'])
                               for p in procedimientos),
            'lineas': lineas}
        self.message_post(body=cuerpo)
        return True
