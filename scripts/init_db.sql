-- scripts/init_db.sql
-- Se ejecuta automáticamente la primera vez que el contenedor postgres arranca
-- (solo si el volumen postgres_data está vacío).

-- Extensión para búsqueda full-text con trigramas (usada en Bloque 2.3)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Extensión para UUIDs (por si se usan en el futuro)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Timezone por defecto
SET timezone = 'UTC';
