import re

from odoo import _, api, fields, models


class BaseProcess(models.Model):
    """Homologación proceso base (TEXPLUS/Odoo) -> tratamiento ORGATEX.

    Los tratamientos de ORGATEX referencian su equivalente TEXPLUS en el
    comentario (p.ej. 'TRATAMIENTO TEXPLUS N74', 'PLANTILLA 0096 TEXPLUS'),
    así que la homologación inicial se puede sembrar automáticamente y el
    laboratorio completa el resto a mano.
    """
    _inherit = ['base.process', 'orgatex.connection.mixin']

    orgatex_treatment_no = fields.Integer(
        'N° Tratamiento ORGATEX', copy=False, index=True,
        help='Número de tratamiento equivalente en ORGATEX (Treatments). '
             'Es lo que se envía en Dyelot_Procedure al mandar una receta.')
    orgatex_treatment_name = fields.Char(
        'Tratamiento ORGATEX', copy=False, readonly=True,
        help='Nombre del tratamiento en ORGATEX (referencial, se llena al '
             'homologar).')

    @api.model
    def action_match_orgatex_treatments(self):
        """Siembra la homologación leyendo los comentarios de Treatments:
        busca el código del proceso base de Odoo (p.ej. N74, 0096, 405)
        mencionado junto a la palabra TEXPLUS. Solo llena los que están
        vacíos: nunca pisa una homologación hecha a mano."""
        conn = self._orgatex_connect()
        try:
            cur = conn.cursor()
            cur.execute("""SELECT TreatmentNo, TreatmentName,
                                  ISNULL(TreatmentComment1, '') + ' ' + ISNULL(TreatmentComment2, '')
                           FROM Treatments""")
            treatments = cur.fetchall()
            cur.close()
        finally:
            conn.close()

        # Índice de procesos base por código normalizado (sin ceros a la
        # izquierda: TEXPLUS escribe '0096' y ORGATEX '96', y viceversa).
        procesos = self.search([('code', '!=', False)])
        por_codigo = {}
        for proc in procesos:
            clave = (proc.code or '').strip().upper()
            por_codigo.setdefault(clave, proc)
            por_codigo.setdefault(clave.lstrip('0') or clave, proc)

        # El código TEXPLUS va PEGADO a la palabra TEXPLUS/EXPLUS/TEXPLUX
        # ('PLANTILLA 0096 TEXPLUS', 'TRATAMIENTO TEXPLUS N74', 'TEXPLUSS 405').
        # Exigir esa adyacencia evita emparejar cualquier número suelto del
        # comentario con un proceso homónimo.
        adyacente = re.compile(
            r'(?:([A-Z]?\d{2,5})\s*[-,]?\s*\w*EXPLU\w*)|(?:\w*EXPLU\w*\s+([A-Z]?\d{2,5}))')
        emparejados = 0
        for treatment_no, treatment_name, comentario in treatments:
            texto = (comentario or '').upper()
            if 'EXPLU' not in texto:   # TEXPLUS / EXPLUS / TEXPLUX (hay de todo)
                continue
            tokens = [t for pareja in adyacente.findall(texto) for t in pareja if t]
            for token in tokens:
                proc = por_codigo.get(token) or por_codigo.get(token.lstrip('0'))
                if proc and not proc.orgatex_treatment_no:
                    proc.write({
                        'orgatex_treatment_no': treatment_no,
                        'orgatex_treatment_name': (treatment_name or '').strip(),
                    })
                    emparejados += 1
                    break
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _('Homologación de tratamientos'),
                'message': _('%(n)s procesos homologados automáticamente '
                             '(de %(t)s tratamientos ORGATEX). El resto se '
                             'completa a mano.',
                             n=emparejados, t=len(treatments)),
                'sticky': False,
            },
        }


class MaintenanceEquipment(models.Model):
    """Homologación máquina de tintorería Odoo -> máquina ORGATEX."""
    _inherit = ['maintenance.equipment', 'orgatex.connection.mixin']

    orgatex_machine_no = fields.Char(
        'N° Máquina ORGATEX', size=4, copy=False, index=True,
        help='Código de la máquina en ORGATEX (Machines.MachineNo, 4 '
             'caracteres: MC29, BZ34, IM03...). Sin él la partida no se '
             'puede enviar a ORGATEX.')

    @api.model
    def action_show_orgatex_machines(self):
        """Lista las máquinas disponibles en ORGATEX (ayuda para homologar)."""
        conn = self._orgatex_connect()
        try:
            cur = conn.cursor()
            cur.execute("""SELECT MachineNo, MachineName, MinWeight, MaxWeight
                           FROM Machines ORDER BY MachineNo""")
            filas = cur.fetchall()
            cur.close()
        finally:
            conn.close()
        detalle = '\n'.join(
            '%s — %s (%s-%s kg)' % (m[0], (m[1] or '').strip(), m[2], m[3])
            for m in filas)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'info',
                'title': _('Máquinas en ORGATEX (%s)') % len(filas),
                'message': detalle,
                'sticky': True,
            },
        }
