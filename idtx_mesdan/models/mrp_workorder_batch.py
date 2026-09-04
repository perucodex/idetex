# -*- coding: utf-8 -*-
"""Reportes PDF del equipo Mesdan adjuntos a la partida Odoo.

El HMI del Mesdan escribe los PDF en el NAS (subcarpetas MESDAN/AA_MM_DD/) y
Odoo los lee desde un mount NFS del mismo share. El código de partida viaja en
el nombre del archivo (tercer token separado por '_') y se resuelve contra
``mrp.workorder.batch.name``. Odoo nunca borra nada del NAS.
"""
import base64
import logging
import os
import re
import socket
import time

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

PARAM_REPORTS_DIR = 'idtx_mesdan.reports_dir'
PARAM_HOST = 'idtx_mesdan.host'
PARAM_TELNET_USER = 'idtx_mesdan.telnet_user'
PARAM_TELNET_PASSWORD = 'idtx_mesdan.telnet_password'
PARAM_DEFAULTS = {
    PARAM_REPORTS_DIR: '/mnt/nas_mesdan_reports/MESDAN',
    PARAM_HOST: '172.16.64.100',
    PARAM_TELNET_USER: 'root',
    PARAM_TELNET_PASSWORD: '',
}

# Carpetas hijas con formato AA_MM_DD (creadas por el HMI cada día).
_FOLDER_RE = re.compile(r"^\d{2}_\d{2}_\d{2}$")
# Código de partida Odoo: prefijo de letras + dígitos y sufijo opcional de
# sub-partida (WB00057, WB00057-A). El HMI a veces añade texto después
# ('wb00057secado'); ese sufijo se descarta.
_BATCH_RE = re.compile(r"^([A-Za-z]{1,5}\d+(?:-[A-Za-z0-9]+)?)")
# Compatibilidad: partidas escritas solo con dígitos (opcionalmente 'C').
_DIGITS_RE = re.compile(r"^[Cc]?(\d+)")
# Nombre de los PDF del Mesdan.
_REPORT_NAME_RE = re.compile(r"^Rep_.*\.pdf$", re.I)


def _batch_key_from_filename(name):
    """Clave de partida contenida en el nombre del PDF, ya normalizada, o None.

        Rep_None_WB00057_D260616_T1113.pdf   -> 'WB00057'
        Rep_X_wb00057-a_D..._T....pdf        -> 'WB00057-A'
        Rep_None_wb00057secado_D..._T....pdf -> 'WB00057'
        Rep_None_378863_D000100_T0000.pdf    -> '378863'  (solo dígitos)
    """
    if not name.lower().endswith('.pdf'):
        return None
    parts = name.split('_')
    if len(parts) < 4:
        return None
    token = parts[2].strip()
    match = _BATCH_RE.match(token)
    if match:
        return match.group(1).upper()
    match = _DIGITS_RE.match(token)
    if match:
        return match.group(1)
    return None


def _list_date_folders(root):
    """Subcarpetas AA_MM_DD ordenadas de la más reciente a la más antigua.
    Devuelve [] si la raíz no es accesible (NFS sin montar, red caída...)."""
    try:
        entries = os.listdir(root)
    except OSError:
        return []
    return sorted((n for n in entries if _FOLDER_RE.match(n)), reverse=True)


class MrpWorkorderBatch(models.Model):
    _inherit = 'mrp.workorder.batch'

    mesdan_report_count = fields.Integer(
        'Reportes Mesdan', compute='_compute_mesdan_report_count',
        help='PDF del Mesdan adjuntos a esta partida.')

    def _compute_mesdan_report_count(self):
        counts = {}
        if self.ids:
            groups = self.env['ir.attachment'].sudo()._read_group(
                [('res_model', '=', self._name), ('res_id', 'in', self.ids),
                 ('name', '=ilike', 'Rep\\_%.pdf')],
                ['res_id'], ['__count'])
            counts = {res_id: count for res_id, count in groups}
        for rec in self:
            rec.mesdan_report_count = counts.get(rec.id, 0)

    # ------------------------------------------------------------------
    # Configuración
    # ------------------------------------------------------------------
    @api.model
    def _mesdan_param(self, key):
        value = self.env['ir.config_parameter'].sudo().get_param(key)
        return (value if value is not None else PARAM_DEFAULTS.get(key, '')).strip()

    @api.model
    def _mesdan_reports_dir(self):
        return self._mesdan_param(PARAM_REPORTS_DIR) or PARAM_DEFAULTS[PARAM_REPORTS_DIR]

    # ------------------------------------------------------------------
    # Resolución partida <-> archivo
    # ------------------------------------------------------------------
    @api.model
    def _mesdan_find_batch(self, key):
        """Partida cuyo nombre corresponde a la clave del archivo.

        Coincidencia exacta (sin distinguir mayúsculas) por nombre; si la
        clave es solo dígitos, se acepta la partida cuyos dígitos coincidan
        (WB00057 <- '00057' o '57')."""
        if not key:
            return self.browse()
        batch = self.search([('name', '=ilike', key)], limit=1)
        if batch or not key.isdigit():
            return batch
        wanted = key.lstrip('0')
        if not wanted:
            return self.browse()
        candidates = self.search([('name', 'ilike', wanted)], limit=50)
        for candidate in candidates:
            if re.sub(r'\D', '', candidate.name or '').lstrip('0') == wanted:
                return candidate
        return self.browse()

    def _mesdan_matches_key(self, key):
        """¿La clave extraída del archivo corresponde a esta partida?"""
        self.ensure_one()
        if not key:
            return False
        name = (self.name or '').strip().upper()
        if key.upper() == name:
            return True
        if key.isdigit():
            return re.sub(r'\D', '', name).lstrip('0') == key.lstrip('0')
        return False

    @api.model
    def _mesdan_iter_pdfs(self):
        """Recorre el NAS y devuelve (carpeta, nombre, ruta completa) de cada PDF."""
        root = self._mesdan_reports_dir()
        for folder in _list_date_folders(root):
            folder_path = os.path.join(root, folder)
            try:
                names = os.listdir(folder_path)
            except OSError as exc:
                _logger.info("Mesdan: no se pudo leer %s (%s)", folder_path, exc)
                continue
            for name in sorted(names):
                if name.lower().endswith('.pdf'):
                    yield folder, name, os.path.join(folder_path, name)

    def _mesdan_has_attachment(self, filename):
        self.ensure_one()
        return bool(self.env['ir.attachment'].sudo().search_count([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('name', '=', filename),
        ], limit=1))

    def _mesdan_attach(self, filename, content, folder):
        """Crea el adjunto y deja constancia en el chatter de la partida."""
        self.ensure_one()
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'datas': base64.b64encode(content),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/pdf',
        })
        self.message_post(
            body=_("Reporte Mesdan importado desde el NAS (%(folder)s): %(file)s",
                   folder=folder, file=filename),
            attachment_ids=[attachment.id],
        )
        return attachment

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def action_fetch_mesdan_reports(self):
        """Botón manual: adjunta todos los PDF del NAS que correspondan a esta
        partida (omite los ya adjuntos)."""
        self.ensure_one()
        root = self._mesdan_reports_dir()
        if not os.path.isdir(root):
            raise UserError(_(
                "El directorio de reportes %s no está disponible. "
                "Verifica que el NFS del NAS esté montado en el servidor.") % root)
        attached = skipped = 0
        for folder, name, path in self._mesdan_iter_pdfs():
            if not self._mesdan_matches_key(_batch_key_from_filename(name)):
                continue
            if self._mesdan_has_attachment(name):
                skipped += 1
                continue
            with open(path, 'rb') as fh:
                self._mesdan_attach(name, fh.read(), folder)
            attached += 1
        if not attached and not skipped:
            raise UserError(_("No se encontró ningún PDF del Mesdan para la partida %s.") % self.name)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'type': 'success',
                'title': _('Reportes Mesdan'),
                'message': _('%(n)s reporte(s) nuevo(s) adjuntado(s), %(s)s ya existían.',
                             n=attached, s=skipped),
                'sticky': False,
            },
        }

    def action_view_mesdan_reports(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reportes Mesdan de %s') % self.name,
            'res_model': 'ir.attachment',
            'view_mode': 'list,form',
            'domain': [('res_model', '=', self._name), ('res_id', '=', self.id),
                       ('name', '=ilike', 'Rep\\_%.pdf')],
            'context': {'default_res_model': self._name, 'default_res_id': self.id},
        }

    # ------------------------------------------------------------------
    # Cron
    # ------------------------------------------------------------------
    @api.model
    def cron_sync_mesdan_reports(self):
        """Recorre el NAS y adjunta a su partida cada PDF nuevo.

        Idempotente: solo adjunta archivos que aún no están en la partida.
        Antes de leer intenta reparar el montaje NFS del lado Mesdan (si hay
        clave telnet configurada)."""
        try:
            self._reconcile_mesdan_mounts()
        except Exception:
            _logger.exception("Mesdan cron: la reparación del montaje falló (se continúa)")

        root = self._mesdan_reports_dir()
        if not os.path.isdir(root):
            _logger.warning("Mesdan cron: %s no accesible (¿NFS sin montar?), salgo", root)
            return False

        attached = skipped = unmatched = errors = 0
        cache = {}
        for folder, name, path in self._mesdan_iter_pdfs():
            try:
                key = _batch_key_from_filename(name)
                if not key:
                    unmatched += 1
                    continue
                if key not in cache:
                    cache[key] = self._mesdan_find_batch(key)
                batch = cache[key]
                if not batch:
                    unmatched += 1
                    continue
                if batch._mesdan_has_attachment(name):
                    skipped += 1
                    continue
                with open(path, 'rb') as fh:
                    batch._mesdan_attach(name, fh.read(), folder)
                attached += 1
            except Exception:
                errors += 1
                _logger.exception("Mesdan cron: error procesando %s/%s", folder, name)

        _logger.info("Mesdan cron: adjuntados=%s repetidos=%s sin_partida=%s errores=%s",
                     attached, skipped, unmatched, errors)
        return True

    # ------------------------------------------------------------------
    # Reparación del montaje NFS en el Mesdan (telnet)
    # ------------------------------------------------------------------
    @api.model
    def _reconcile_mesdan_mounts(self):
        """Asegura que /mnt/Part2/Reports del Mesdan esté enlazado al NFS del NAS.

        El enlace (bind) se ha perdido alguna vez (umount + reinicio del HMI);
        entonces el HMI escribe en el disco local y los PDF nunca llegan al
        NAS. Aquí se detecta, se migran los archivos locales y se restablece
        el enlace. Requiere la clave telnet en ``idtx_mesdan.telnet_password``;
        sin ella no se hace nada."""
        password = self._mesdan_param(PARAM_TELNET_PASSWORD)
        if not password:
            _logger.info("Mesdan: sin clave telnet configurada, se omite la reparación del montaje")
            return False
        host = self._mesdan_param(PARAM_HOST)
        user = self._mesdan_param(PARAM_TELNET_USER) or 'root'
        try:
            tn = _mesdan_telnet_login(host, user, password)
        except Exception as exc:
            _logger.warning("Mesdan: no se pudo entrar por telnet a %s (%s)", host, exc)
            return False
        try:
            mounts = _mesdan_tcmd(tn, "mount")
            nfs_up = ":/odoo on /mnt/Part2/.nfs_odoo" in mounts
            bind_up = ":/odoo/MESDAN on /mnt/Part2/Reports" in mounts
            if nfs_up and bind_up:
                return True
            _logger.warning("Mesdan: NFS=%s bind=%s — restaurando", nfs_up, bind_up)

            stranded_count = 0
            if not bind_up:
                out = _mesdan_tcmd(tn, "find /mnt/Part2/Reports -type f 2>/dev/null | wc -l")
                try:
                    stranded_count = int(out.splitlines()[-1].strip())
                except Exception:
                    stranded_count = 0
                if stranded_count:
                    _logger.info("Mesdan: %s archivos locales a migrar al NAS", stranded_count)
                    if not nfs_up:
                        _mesdan_tcmd(tn,
                                     "mkdir -p /mnt/Part2/.nfs_odoo && "
                                     "mount -t nfs -o rw,nolock,soft,timeo=30,retrans=3 "
                                     "172.16.64.6:/odoo /mnt/Part2/.nfs_odoo",
                                     w=20)
                    _mesdan_tcmd(tn,
                                 "mkdir -p /mnt/Part2/.nfs_odoo/MESDAN && "
                                 "cp -r /mnt/Part2/Reports/. /mnt/Part2/.nfs_odoo/MESDAN/ "
                                 "&& echo COPY_OK || echo COPY_FAIL",
                                 w=180)
                    _mesdan_tcmd(tn, "rm -rf /mnt/Part2/Reports/* /mnt/Part2/Reports/.[!.]*", w=30)

            _mesdan_tcmd(tn, "/etc/init.d/nfs-reports start", w=30)
            ok = ":/odoo/MESDAN on /mnt/Part2/Reports" in _mesdan_tcmd(tn, "mount")
            _logger.info("Mesdan: montaje restaurado=%s (migrados=%s archivos)", ok, stranded_count)
            return ok
        finally:
            try:
                tn.write(b"exit\r\n")
            except Exception:
                pass
            tn.close()


# ---- telnet mínimo (telnetlib desapareció en Python 3.13) --------------------

_IAC = 0xFF
_DONT, _DO, _WONT, _WILL = 0xFE, 0xFD, 0xFC, 0xFB
_SB, _SE = 0xFA, 0xF0


class _MesdanTelnet:
    """Subconjunto de telnetlib.Telnet suficiente para el getty del Mesdan."""

    def __init__(self, host, port=23, timeout=10):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self._buf = b""

    def _handle_iac(self, data):
        """Quita las negociaciones IAC rechazando toda opción (WONT/DONT)."""
        out = bytearray()
        replies = bytearray()
        i = 0
        while i < len(data):
            b = data[i]
            if b != _IAC:
                out.append(b)
                i += 1
                continue
            if i + 1 >= len(data):
                break
            cmd = data[i + 1]
            if cmd in (_DO, _DONT, _WILL, _WONT):
                if i + 2 >= len(data):
                    break
                opt = data[i + 2]
                if cmd == _DO:
                    replies.extend(bytes([_IAC, _WONT, opt]))
                elif cmd == _WILL:
                    replies.extend(bytes([_IAC, _DONT, opt]))
                i += 3
            elif cmd == _SB:
                j = i + 2
                while j + 1 < len(data):
                    if data[j] == _IAC and data[j + 1] == _SE:
                        break
                    j += 1
                i = j + 2
            else:
                i += 2
        if replies:
            try:
                self.sock.sendall(bytes(replies))
            except OSError:
                pass
        return bytes(out)

    def _drain(self, timeout):
        self.sock.settimeout(timeout)
        try:
            chunk = self.sock.recv(65536)
        except (socket.timeout, BlockingIOError):
            return b""
        if not chunk:
            return b""
        return self._handle_iac(chunk)

    def read_until(self, marker, timeout=10):
        deadline = time.time() + timeout
        while marker not in self._buf and time.time() < deadline:
            chunk = self._drain(0.5)
            if chunk:
                self._buf += chunk
        if marker in self._buf:
            idx = self._buf.index(marker) + len(marker)
            out, self._buf = self._buf[:idx], self._buf[idx:]
            return out
        out, self._buf = self._buf, b""
        return out

    def read_very_eager(self):
        chunk = self._drain(0.05)
        if chunk:
            self._buf += chunk
        out, self._buf = self._buf, b""
        return out

    def write(self, data):
        if bytes([_IAC]) in data:
            data = data.replace(bytes([_IAC]), bytes([_IAC, _IAC]))
        self.sock.sendall(data)

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def _mesdan_telnet_login(host, user, password):
    tn = _MesdanTelnet(host, 23, timeout=15)
    tn.read_until(b"login:", 5)
    tn.write(user.encode() + b"\r\n")
    tn.read_until(b"assword:", 5)
    tn.write(password.encode() + b"\r\n")
    time.sleep(2)
    tn.read_very_eager()
    return tn


def _mesdan_tcmd(tn, command, w=3):
    tn.write(command.encode() + b"\r\n")
    time.sleep(w)
    out = b""
    deadline = time.time() + w * 2 + 5
    while time.time() < deadline:
        chunk = tn.read_very_eager()
        if chunk:
            out += chunk
            deadline = time.time() + 2
        else:
            time.sleep(0.2)
    return out.decode(errors="replace").strip()
