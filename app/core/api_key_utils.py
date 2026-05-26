"""
app/core/api_key_utils.py

Bloque 6.2 — Utilidades para generación y verificación de API Keys.

Formato de la clave:  df_<env>_<32 bytes random hex>
  Ejemplo:            df_live_a3f2c8e1b7d4...

Se almacena solo el SHA-256 del valor completo.
El prefijo visible (primeros 14 chars) se guarda por separado para
que el usuario pueda identificar sus claves en el listado.
"""

import hashlib
import secrets

PREFIX = "df_live_"   # cambiar a "df_test_" en entornos de prueba


def generate_api_key() -> tuple[str, str, str]:
    """
    Genera una API key nueva.

    Retorna:
      (raw_key, key_hash, key_prefix)
      - raw_key   : valor completo que se muestra UNA SOLA VEZ al usuario
      - key_hash  : SHA-256 del raw_key, guardado en BD
      - key_prefix: primeros 14 chars visibles para identificación
    """
    random_part = secrets.token_hex(32)          # 64 chars hex
    raw_key     = f"{PREFIX}{random_part}"
    key_hash    = _hash_key(raw_key)
    key_prefix  = raw_key[:14]                   # "df_live_AbCdEf"
    return raw_key, key_hash, key_prefix


def _hash_key(raw_key: str) -> str:
    """SHA-256 del raw_key, en hex."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def verify_api_key(raw_key: str, stored_hash: str) -> bool:
    """Compara en tiempo constante para evitar timing attacks."""
    return secrets.compare_digest(_hash_key(raw_key), stored_hash)


def hash_key(raw_key: str) -> str:
    """Alias público para usar en la dependency de autenticación."""
    return _hash_key(raw_key)
