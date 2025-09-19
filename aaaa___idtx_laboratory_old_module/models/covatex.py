import mysql.connector
import logging
import base64
import os
import binascii
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

# ENCRYPTION_KEY = 'b17335883b1008d8d0c8bb50601f333b16759cc329d2e3050f9c8ae1b8a4d6bf'
# KEY = binascii.unhexlify(ENCRYPTION_KEY)
# BS = AES.block_size

# ---------- tus claves ----------
ENCRYPTION_KEY = 'b17335883b1008d8d0c8bb50601f333b16759cc329d2e3050f9c8ae1b8a4d6bf'
METHOD = 'AES-256-CBC'
KEY = binascii.unhexlify(ENCRYPTION_KEY)
BS  = AES.block_size          # 16 bytes

_logger = logging.getLogger(__name__)

class MySQLConnector:
    def __init__(self, host, user, password, database):
        self.host = host
        self.user = user
        self.password = password
        self.database = database

    def _get_connection(self):
        try:
            return mysql.connector.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database,
                charset='utf8mb4',
                use_unicode=True,
                collation='utf8mb4_bin',
                init_command="SET NAMES utf8mb4 COLLATE utf8mb4_bin",
            )
        except Exception as e:
            _logger.error("Error al conectar a MySQL: %s", e)
            raise

    def execute_query(self, query, params=None, fetch=False):
        conn = self._get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params or ())
        results = cursor.fetchall() if fetch else None
        conn.commit()
        cursor.close()
        conn.close()
        return results

    def insert(self, table, values: dict):
        cols = ", ".join(values.keys())
        placeholders = ", ".join(["%s"] * len(values))
        sql = f"INSERT INTO {table} ({cols}) VALUES ({placeholders})"
        self.execute_query(sql, tuple(values.values()))
        _logger.info("Registro insertado en %s: %s", table, values)

    # ---------- cifrado compatible ----------
    @staticmethod
    def encrypt_data(data: str) -> str:
        iv = os.urandom(BS)
        cipher = AES.new(KEY, AES.MODE_CBC, iv)
        ct = cipher.encrypt(pad(data.encode('utf-8'), BS))
        return base64.b64encode(iv + ct).decode('ascii')

    @staticmethod
    def decrypt_data(b64: str) -> str:
        raw = base64.b64decode(b64)
        iv, ct = raw[:BS], raw[BS:]
        cipher = AES.new(KEY, AES.MODE_CBC, iv)
        return unpad(cipher.decrypt(ct), BS).decode('utf-8')