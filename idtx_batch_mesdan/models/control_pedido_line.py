# -*- coding: utf-8 -*-
import base64
import logging
import os
import re
import socket
import time

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Carpeta donde el HMI Mesdan escribe (a través del NFS del NAS). El admin
# Odoo monta `172.16.64.6:/odoo` en el server y este path apunta al
# subdirectorio MESDAN/. Si el mount se cae, el módulo logea warning y
# devuelve sin hacer nada.
MESDAN_REPORTS_DIR = "/mnt/nas_mesdan_reports/MESDAN"

# Carpetas hijas con formato YY_MM_DD (creadas por el HMI cada día).
_FOLDER_RE = re.compile(r"^\d{2}_\d{2}_\d{2}$")

# --- Mesdan host connection (used by mount reconcile) ---------------------
# We log in as root via Telnet to repair the NFS bind mount if it goes down.
MESDAN_HOST = "172.16.64.100"
MESDAN_ROOT_PWD_B64 = "b2JhZg=="  # 'obaf'


def _batch_from_filename(name):
    """Return the partida key extracted from a Mesdan PDF filename, or None.

    Examples:
        Rep_None_378863_D000100_T0000.pdf -> '378863'
        Rep_X_C378863_...pdf              -> 'C378863'
    """
    if not name.lower().endswith(".pdf"):
        return None
    parts = name.split("_")
    if len(parts) < 4:
        return None
    return parts[2] or None


def _list_date_folders(root):
    """Return YY_MM_DD subfolders sorted newest first. Returns [] if root
    is unreachable (NFS not mounted, network down, etc)."""
    try:
        entries = os.listdir(root)
    except OSError:
        return []
    return sorted(
        (n for n in entries if _FOLDER_RE.match(n)),
        reverse=True,
    )


class ControlPedidoLine(models.Model):
    _inherit = "control.pedido.line"

    # ---- single-line fetch (manual button) ---------------------------------

    def _find_report_pdfs(self, batch):
        """Locate every PDF for `batch` in the NFS mirror.

        Yields (filename, folder, content_bytes) tuples. A partida can have
        more than one PDF (multiple samples, manual retries, etc.) — all are
        returned.
        """
        if not os.path.isdir(MESDAN_REPORTS_DIR):
            raise UserError(_(
                "El directorio de reportes %s no está disponible. "
                "Verifica que el NFS del NAS esté montado."
            ) % MESDAN_REPORTS_DIR)

        clean_batch = batch[1:] if batch.startswith('C') else batch
        for folder in _list_date_folders(MESDAN_REPORTS_DIR):
            folder_path = os.path.join(MESDAN_REPORTS_DIR, folder)
            try:
                names = os.listdir(folder_path)
            except OSError:
                continue
            for name in sorted(names):
                if not name.lower().endswith(".pdf"):
                    continue
                if not (f"_C{clean_batch}_" in name or f"_{clean_batch}_" in name):
                    continue
                with open(os.path.join(folder_path, name), 'rb') as fh:
                    yield name, folder, fh.read()

    def action_fetch_report_pdf(self):
        """Manual button on the line view. Attaches every PDF that matches
        this partida (skipping ones already present)."""
        self.ensure_one()
        if not self.batch:
            raise UserError(_("Esta línea no tiene partida."))
        Attachment = self.env['ir.attachment']
        attached = skipped = 0
        for filename, folder, content in self._find_report_pdfs(self.batch):
            if Attachment.search_count([
                ('res_model', '=', self._name),
                ('res_id', '=', self.id),
                ('name', '=', filename),
            ], limit=1):
                skipped += 1
                continue
            self._attach_report_pdf(filename, content, folder)
            attached += 1
        if not attached and not skipped:
            raise UserError(_(
                "No se encontró ningún PDF para la partida %s."
            ) % self.batch)
        return True

    def _attach_report_pdf(self, filename, content, folder):
        """Create the ir.attachment + chatter entry on self (single line)."""
        self.ensure_one()
        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'datas': base64.b64encode(content),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'application/pdf',
        })
        self.message_post(
            body=_("Reporte importado desde NAS (%s): %s") % (folder, filename),
            attachment_ids=[attachment.id],
        )
        return attachment

    # ---- periodic sync (cron) ----------------------------------------------

    @api.model
    def cron_sync_mesdan_reports(self):
        """Walk the NAS NFS mirror and attach any new PDFs to their partidas.

        Idempotent: only downloads/attaches files that aren't already present
        as an ir.attachment for the same partida. The NAS keeps the long-term
        archive — we never delete anything from it.

        Self-healing: before reading, reconciles the Mesdan-side bind mount.
        If the bind is down, the HMI may have been writing PDFs to local ext4
        instead of the NAS — we migrate them and restore the bind.
        """
        try:
            self._reconcile_mesdan_mounts()
        except Exception:
            _logger.exception("Mesdan cron: mount reconcile failed (continuando igual)")

        if not os.path.isdir(MESDAN_REPORTS_DIR):
            _logger.warning(
                "Mesdan cron: %s no accesible (NFS no montado?), salgo",
                MESDAN_REPORTS_DIR,
            )
            return False

        Attachment = self.env['ir.attachment']
        attached = skipped = unmatched = errors = 0
        for folder in _list_date_folders(MESDAN_REPORTS_DIR):
            folder_path = os.path.join(MESDAN_REPORTS_DIR, folder)
            try:
                names = [n for n in os.listdir(folder_path)
                         if n.lower().endswith('.pdf')]
            except OSError as exc:
                _logger.info("Mesdan cron: no se pudo leer %s (%s)", folder_path, exc)
                continue
            for name in names:
                try:
                    batch_key = _batch_from_filename(name)
                    if not batch_key:
                        unmatched += 1
                        continue
                    line = self._find_line_by_batch_key(batch_key)
                    if not line:
                        unmatched += 1
                        continue
                    already = Attachment.search_count([
                        ('res_model', '=', self._name),
                        ('res_id', '=', line.id),
                        ('name', '=', name),
                    ], limit=1)
                    if already:
                        skipped += 1
                        continue
                    with open(os.path.join(folder_path, name), 'rb') as fh:
                        content = fh.read()
                    line._attach_report_pdf(name, content, folder)
                    attached += 1
                except Exception:
                    errors += 1
                    _logger.exception("Mesdan cron: error procesando %s/%s", folder, name)

        _logger.info(
            "Mesdan cron: attached=%s skipped=%s unmatched=%s errors=%s",
            attached, skipped, unmatched, errors,
        )
        return True

    @api.model
    def _find_line_by_batch_key(self, batch_key):
        """Resolve `batch_key` from filename (e.g. '378863' or 'C378863') to
        an existing control.pedido.line. Returns empty recordset if none.
        """
        candidates = [batch_key]
        if batch_key.startswith('C'):
            candidates.append(batch_key[1:])
        else:
            candidates.append(f"C{batch_key}")
        return self.search([('batch', 'in', candidates)], limit=1)

    # ---- mount self-healing -----------------------------------------------

    @api.model
    def _reconcile_mesdan_mounts(self):
        """Ensure the Mesdan's /mnt/Part2/Reports is bound to the NAS NFS.

        Why: the bind has been known to disappear (e.g. after lazy umount +
        HMI restart). When it does, the HMI keeps writing PDFs to local ext4
        — those files never reach the NAS. This function detects the gap,
        migrates stranded local files to the NAS, and re-establishes the
        bind so future writes go directly to the share.

        Safe to call at any time. Idempotent.
        """
        try:
            tn = _mesdan_telnet_login()
        except Exception as exc:
            _logger.warning("Mesdan reconcile: telnet login failed (%s)", exc)
            return False
        try:
            mounts = _mesdan_tcmd(tn, "mount")
            nfs_up = ":/odoo on /mnt/Part2/.nfs_odoo" in mounts
            bind_up = ":/odoo/MESDAN on /mnt/Part2/Reports" in mounts
            if nfs_up and bind_up:
                return True
            _logger.warning(
                "Mesdan reconcile: NFS=%s bind=%s — restaurando", nfs_up, bind_up,
            )

            # If bind is down, /mnt/Part2/Reports is the local ext4 dir.
            # Any HMI-written PDFs there are stranded.
            stranded_count = 0
            if not bind_up:
                out = _mesdan_tcmd(tn, "find /mnt/Part2/Reports -type f 2>/dev/null | wc -l")
                try:
                    stranded_count = int(out.splitlines()[-1].strip())
                except Exception:
                    stranded_count = 0
                if stranded_count:
                    _logger.info("Mesdan reconcile: %s archivos locales a migrar", stranded_count)
                    # Ensure the helper NFS mount is up first.
                    if not nfs_up:
                        _mesdan_tcmd(tn,
                            "mkdir -p /mnt/Part2/.nfs_odoo && "
                            "mount -t nfs -o rw,nolock,soft,timeo=30,retrans=3 "
                            "172.16.64.6:/odoo /mnt/Part2/.nfs_odoo",
                            w=20,
                        )
                    # Copy local content into the NFS subdir (cp -r, sin -p,
                    # para evitar chown a root mientras estamos squashed).
                    _mesdan_tcmd(tn,
                        "mkdir -p /mnt/Part2/.nfs_odoo/MESDAN && "
                        "cp -r /mnt/Part2/Reports/. /mnt/Part2/.nfs_odoo/MESDAN/ "
                        "&& echo COPY_OK || echo COPY_FAIL",
                        w=180,
                    )
                    # Wipe local Reports content (still ext4, bind is down).
                    _mesdan_tcmd(tn, "rm -rf /mnt/Part2/Reports/* /mnt/Part2/Reports/.[!.]*", w=30)

            # Establish (or re-establish) NFS + bind via the init script.
            _mesdan_tcmd(tn, "/etc/init.d/nfs-reports start", w=30)

            mounts2 = _mesdan_tcmd(tn, "mount")
            ok = ":/odoo/MESDAN on /mnt/Part2/Reports" in mounts2
            _logger.info(
                "Mesdan reconcile: post-recover bind=%s (migrated=%s archivos)",
                ok, stranded_count,
            )
            return ok
        finally:
            try: tn.write(b"exit\r\n")
            except Exception: pass
            try: tn.close()
            except Exception: pass

# ---- telnet helpers (module-level) ---------------------------------------
# stdlib `telnetlib` was deprecated in Python 3.11 and removed in 3.13. We
# only need a tiny subset of the protocol (line-based shell over TCP with
# IAC option refusal), so this minimal socket wrapper replaces it without
# pulling in a third-party dependency.

_IAC = 0xFF
_DONT, _DO, _WONT, _WILL = 0xFE, 0xFD, 0xFC, 0xFB
_SB, _SE = 0xFA, 0xF0


class _MesdanTelnet:
    """Subset of telnetlib.Telnet sufficient for the Mesdan getty."""

    def __init__(self, host, port=23, timeout=10):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self._buf = b""

    def _handle_iac(self, data):
        """Strip IAC negotiations, refusing every option (WONT/DONT)."""
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


def _mesdan_telnet_login():
    pwd = base64.b64decode(MESDAN_ROOT_PWD_B64).decode("utf-8")
    tn = _MesdanTelnet(MESDAN_HOST, 23, timeout=15)
    tn.read_until(b"login:", 5)
    tn.write(b"root\r\n")
    tn.read_until(b"assword:", 5)
    tn.write(pwd.encode() + b"\r\n")
    time.sleep(2)
    tn.read_very_eager()
    return tn


def _mesdan_tcmd(tn, c, w=3):
    tn.write(c.encode() + b"\r\n")
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
