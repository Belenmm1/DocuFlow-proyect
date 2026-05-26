"""
alembic/env.py — Bloque 2.4

Configuración del entorno de Alembic.

Puntos clave:
  - La DATABASE_URL se lee desde app.config.settings (que a su vez la toma del .env).
  - `target_metadata` apunta a Base.metadata con todos los modelos importados,
    lo que permite que Alembic detecte cambios automáticamente (--autogenerate).
  - Soporte para migraciones online (PostgreSQL) y offline (genera SQL sin conectar).
  - compare_type=True → detecta cambios de tipo de columna en autogenerate.
  - compare_server_default=True → detecta cambios en valores por defecto.
"""

import sys
import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Asegurar que el root del proyecto esté en sys.path
# para que `from app.xxx` funcione al correr `alembic` desde cualquier directorio.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# ── Importar todos los modelos ANTES de usar Base.metadata ────────────────────
# Alembic detecta cambios solo de los modelos que estén importados en este punto.
from app.models.database import Base          # noqa: F401 — registra Document
from app.models.user import User              # noqa: F401 — registra User
from app.models.chat import ChatConversation, ChatMessage  # noqa: F401 — Bloque 3.1
from app.config import settings

# Alembic Config object
config = context.config

# Inyectar la URL desde settings (toma precedencia sobre alembic.ini)
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


# ─────────────────────────────────────────────────────────────────────────────
# Migraciones OFFLINE — genera SQL sin conexión real a la DB
# ─────────────────────────────────────────────────────────────────────────────

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ─────────────────────────────────────────────────────────────────────────────
# Migraciones ONLINE — conecta a la DB y aplica los cambios
# ─────────────────────────────────────────────────────────────────────────────

def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # NullPool en migraciones evita conexiones colgadas
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
