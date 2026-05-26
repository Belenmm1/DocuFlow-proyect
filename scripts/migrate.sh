#!/usr/bin/env bash
# scripts/migrate.sh
# =============================================================================
# Bloque 2.4 — Script de migración seguro con checks previos
#
# Uso:
#   ./scripts/migrate.sh            → aplica todas las migraciones pendientes
#   ./scripts/migrate.sh --check    → solo verifica qué migraciones están pendientes
#   ./scripts/migrate.sh --fresh    → borra la DB y la recrea desde cero (¡DESTRUCTIVO!)
#   ./scripts/migrate.sh --rollback → revierte la última migración
# =============================================================================

set -euo pipefail

# ── Colores ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ── Verificar que exista .env ─────────────────────────────────────────────────
if [ ! -f ".env" ] && [ ! -f "../.env" ]; then
    log_warn ".env no encontrado. Usando variables de entorno del sistema."
fi

# ── Verificar que DATABASE_URL esté seteada ───────────────────────────────────
if [ -z "${DATABASE_URL:-}" ]; then
    # Intentar cargar desde .env
    if [ -f ".env" ]; then
        export $(grep -v '^#' .env | grep 'DATABASE_URL' | xargs)
    fi
fi

if [ -z "${DATABASE_URL:-}" ]; then
    log_error "DATABASE_URL no está configurada. Abortando."
    exit 1
fi

log_info "DATABASE_URL: ${DATABASE_URL:0:30}..."

# ── Modo ──────────────────────────────────────────────────────────────────────
MODE="${1:---apply}"

case "$MODE" in
    --check)
        log_info "Migraciones pendientes:"
        alembic history --indicate-current
        alembic current
        ;;

    --rollback)
        log_warn "Revirtiendo la última migración..."
        alembic downgrade -1
        log_info "Rollback aplicado."
        ;;

    --fresh)
        log_warn "⚠️  MODO FRESH: esto BORRA TODOS LOS DATOS. ¿Confirmar? (escribe 'si')"
        read -r CONFIRM
        if [ "$CONFIRM" != "si" ]; then
            log_info "Cancelado."
            exit 0
        fi
        log_warn "Bajando todas las migraciones..."
        alembic downgrade base
        log_info "Aplicando todas las migraciones desde cero..."
        alembic upgrade head
        log_info "Base de datos recreada exitosamente."
        ;;

    --apply|*)
        log_info "Aplicando migraciones pendientes..."
        alembic upgrade head
        log_info "✅ Migraciones aplicadas. Estado actual:"
        alembic current
        ;;
esac
