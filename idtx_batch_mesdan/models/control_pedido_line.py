# -*- coding: utf-8 -*-
import base64
import logging
import os
import re
import sqlite3
import telnetlib
import tempfile
import time
from ftplib import FTP

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

# --- Mesdan host connection (for burst.db maintenance only) -----------------
# The HMI keeps an SQLite DB at /mnt/Part2/burst.db that caps at 101 tests
# (hardcoded in the HMI binary). When full it refuses to save. We log in as
# root via Telnet + Mesdan-user via FTP to prune the oldest entries nightly.
MESDAN_HOST = "172.16.64.100"
MESDAN_ROOT_PWD_B64 = "b2JhZg=="  # 'obaf'
MESDAN_FTP_USER = "Mesdan"
MESDAN_FTP_PWD_B64 = "TWVzZGFu"   # 'Mesdan'
MESDAN_DB_PATH = "/mnt/Part2/burst.db"
MESDAN_DB_KEEP = 30               # how many recent tests to retain
MESDAN_DB_BACKUPS_KEEP = 7        # rotate daily backups, keep one week


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

    report_pdf_attached = fields.Boolean(compute='_compute_report_pdf_attached')

    def _compute_report_pdf_attached(self):
        Attachment = self.env['ir.attachment']
        for rec in self:
            if not rec.id:
                rec.report_pdf_attached = False
                continue
            rec.report_pdf_attached = bool(Attachment.search_count([
                ('res_model', '=', rec._name),
                ('res_id', '=', rec.id),
                ('name', 'like', 'Rep_%'),
                ('mimetype', '=', 'application/pdf'),
            ], limit=1))

    # ---- single-line fetch (manual button) ---------------------------------

    def _find_report_pdf(self, batch):
        """Locate the most recent PDF for `batch` in the NFS mirror.

        Returns (filename, folder, content_bytes) or raises UserError.
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
            candidates = [
                name for name in names
                if name.lower().endswith(".pdf")
                and (f"_C{clean_batch}_" in name or f"_{clean_batch}_" in name)
            ]
            if candidates:
                filename = sorted(candidates)[-1]
                with open(os.path.join(folder_path, filename), 'rb') as fh:
                    content = fh.read()
                return filename, folder, content

        raise UserError(_(
            "No se encontró un PDF para la partida %s en %s."
        ) % (batch, MESDAN_REPORTS_DIR))

    def action_fetch_report_pdf(self):
        """Manual button on the line view. Surfaces the latest PDF for this
        partida into Odoo as an ir.attachment."""
        self.ensure_one()
        if not self.batch:
            raise UserError(_("Esta línea no tiene partida."))
        filename, folder, content = self._find_report_pdf(self.batch)
        self._attach_report_pdf(filename, content, folder)
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
        """
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

    # ---- HMI internal SQLite maintenance (cron) ---------------------------

    @api.model
    def cron_clean_mesdan_burst_db(self):
        """Prune the HMI's burst.db to keep only the MESDAN_DB_KEEP most
        recent tests. The HMI caps the database at 101 entries; without this
        the operator has to manually press "Erase All" on the touchscreen.

        Safe because:
        - The actual measurement PDFs are mirrored on the NAS already, so
          deleting metadata is non-destructive (the truth is in the PDFs).
        - We back up burst.db with a timestamp before swapping, rotating
          backups (keep MESDAN_DB_BACKUPS_KEEP newest).
        - Designed to run nightly when the HMI is idle.
        """
        try:
            tn = _mesdan_telnet_login()
        except Exception as exc:
            _logger.warning("Mesdan DB cleanup: telnet login failed (%s)", exc)
            return False
        try:
            # 1. Stage burst.db where the FTP user can read it (the FTP root
            #    chroots to /home/Mesdan -> /mnt/Part2/Reports -> NFS).
            _mesdan_tcmd(tn, f"cp {MESDAN_DB_PATH} /mnt/Part2/Reports/_burst_in.db", w=15)

            # 2. Pull via FTP and immediately delete the staging file.
            ftp = FTP(MESDAN_HOST, timeout=60)
            ftp.login(MESDAN_FTP_USER, base64.b64decode(MESDAN_FTP_PWD_B64).decode())
            ftp.cwd("/mnt/Part2/Reports")
            with tempfile.NamedTemporaryFile(prefix="burst.", suffix=".db", delete=False) as tf:
                local_db = tf.name
            with open(local_db, "wb") as f:
                ftp.retrbinary("RETR _burst_in.db", f.write)
            try:
                ftp.delete("_burst_in.db")
            except Exception:
                _logger.info("Mesdan DB cleanup: no se pudo borrar _burst_in.db del FTP")

            # 3. Prune locally with sqlite3.
            con = sqlite3.connect(local_db)
            try:
                cur = con.cursor()
                total = cur.execute("SELECT COUNT(*) FROM table_tests").fetchone()[0]
                if total <= MESDAN_DB_KEEP:
                    _logger.info("Mesdan DB cleanup: %s tests <= %s, nada que hacer",
                                 total, MESDAN_DB_KEEP)
                    ftp.quit()
                    return True
                oldest = [r[0] for r in cur.execute(
                    "SELECT test_code_all FROM table_tests "
                    "ORDER BY test_date_time ASC LIMIT ?",
                    (total - MESDAN_DB_KEEP,)
                )]
                # FK chain: samples -> parProva -> tests (ON DELETE RESTRICT).
                ph = ",".join(["?"] * len(oldest))
                cur.execute(f"DELETE FROM table_samples WHERE test_code_all IN ({ph})", oldest)
                cur.execute(f"DELETE FROM table_parProva WHERE test_code_all IN ({ph})", oldest)
                cur.execute(f"DELETE FROM table_tests WHERE test_code_all IN ({ph})", oldest)
                con.commit()
                cur.execute("VACUUM")
                _logger.info("Mesdan DB cleanup: %s -> %s tests (purged %s)",
                             total, MESDAN_DB_KEEP, len(oldest))
            finally:
                con.close()

            # 4. Push back: STOR pruned file, then cp into place. Use `cp`
            #    (not `mv`) so the inode is preserved — the HMI keeps many
            #    open fds to burst.db that share the same inode, so an
            #    in-place rewrite is friendlier than a rename.
            ts = time.strftime("%Y%m%d_%H%M%S")
            _mesdan_tcmd(tn, f"cp {MESDAN_DB_PATH} {MESDAN_DB_PATH}.backup.{ts}", w=10)

            with open(local_db, "rb") as f:
                ftp.storbinary("STOR _burst_new.db", f)
            ftp.quit()

            out = _mesdan_tcmd(tn,
                f"cp /mnt/Part2/Reports/_burst_new.db {MESDAN_DB_PATH} "
                f"&& rm /mnt/Part2/Reports/_burst_new.db && sync && echo SWAPPED_OK",
                w=15,
            )
            if "SWAPPED_OK" not in out:
                _logger.warning("Mesdan DB cleanup: swap output: %s", out[:300])
            os.unlink(local_db)

            # 5. Rotate old backups, keep MESDAN_DB_BACKUPS_KEEP newest.
            list_out = _mesdan_tcmd(tn,
                "ls -1 /mnt/Part2/burst.db.backup.* 2>/dev/null | sort", w=3
            )
            backups = [ln.strip() for ln in list_out.splitlines()
                       if ln.startswith("/mnt/Part2/burst.db.backup.")]
            if len(backups) > MESDAN_DB_BACKUPS_KEEP:
                to_delete = backups[: len(backups) - MESDAN_DB_BACKUPS_KEEP]
                _mesdan_tcmd(tn, "rm -f " + " ".join(to_delete), w=10)
                _logger.info("Mesdan DB cleanup: removed %s old backups", len(to_delete))
        finally:
            try: tn.write(b"exit\r\n")
            except Exception: pass
            try: tn.close()
            except Exception: pass
        return True


# ---- telnet helpers (module-level) ---------------------------------------

def _mesdan_telnet_login():
    pwd = base64.b64decode(MESDAN_ROOT_PWD_B64).decode("utf-8")
    tn = telnetlib.Telnet(MESDAN_HOST, 23, timeout=15)
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
