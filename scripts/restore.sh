#!/usr/bin/env bash
# =============================================================================
# scripts/restore.sh — Bloque 7.4
#
# Restaurar un backup de DocuFlow.
#
# ┌─────────────────────────────────────────────────────────────────────────┐
# │  ⚠️  ATENCIÓN: esto BORRA todos los datos actuales de la base antes     │
# │  de restaurar. Usar solo en caso de recuperación de desastre o          │
# │  migraciones planificadas.                                              │
# └─────────────────────────────────────────────────────────────────────────┘
#
# Uso:
#   ./scripts/restore.sh /app/backups/docuflow_20240101_120000.sql.gz
#   ./scripts/restore.sh --list                # listar backups disponibles
#   ./scripts/restore.sh --latest              # restaurar el más reciente
#   ./scripts/restore.sh --s3 s3://mi-bucket/docuflow-backups/docuflow_...sql.gz
#
# Flujo completo de recuperación de desastre:
#   1. docker compose down
#   2. docker compose up -d db redis
#   3. docker compose exec worker bash scripts/restore.sh --latest
#   4. docker compose up -d
#
# =============================================================================

set -euo pipefail

# ── Configuración ─────────────────────────────────────────────────────────────
BACKUP_DIR="${BACKUP_DIR:-/app/backups}"
DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${POSTGRES_USER:-docuflow}"
DB_NAME="${POSTGRES_DB:-docuflow}"

# ── Funciones ─────────────────────────────────────────────────────────────────

log()  { echo "[restore][$(date '+%H:%M:%S')] $*"; }
err()  { echo "[restore][$(date '+%H:%M:%S')] ❌ $*" >&2; }
ok()   { echo "[restore][$(date '+%H:%M:%S')] ✅ $*"; }
warn() { echo "[restore][$(date '+%H:%M:%S')] ⚠️  $*"; }

usage() {
  cat <<EOF

  Uso: $0 <backup_file.sql.gz>
       $0 --list
       $0 --latest
       $0 --s3 <s3://bucket/key.sql.gz>

  Opciones:
    <archivo>     Ruta local al archivo .sql.gz
    --list        Listar todos los backups locales disponibles
    --latest      Restaurar el backup local más reciente
    --s3 <url>    Descargar desde S3 y restaurar

EOF
  exit 1
}

list_backups() {
  log "Backups disponibles en $BACKUP_DIR:"
  echo ""
  local count=0
  while IFS= read -r f; do
    local size
    size=$(du -sh "$f" | cut -f1)
    local mtime
    mtime=$(stat -c "%y" "$f" | cut -d'.' -f1)
    echo "  [$count] $(basename "$f")  ($size)  —  $mtime"
    (( count++ )) || true
  done < <(find "$BACKUP_DIR" -name "docuflow_*.sql.gz" | sort -r 2>/dev/null)
  echo ""
  if [[ $count -eq 0 ]]; then
    warn "No se encontraron backups locales."
    exit 0
  fi
}

verify_checksum() {
  local file="$1"
  local checksum_file="${file}.sha256"
  if [[ -f "$checksum_file" ]]; then
    log "Verificando checksum SHA-256..."
    if sha256sum -c "$checksum_file" --quiet 2>/dev/null; then
      ok "Checksum válido."
    else
      err "Checksum INVÁLIDO. El archivo puede estar corrupto."
      read -r -p "¿Continuar de todos modos? [s/N]: " FORCE
      [[ "$FORCE" != "s" && "$FORCE" != "S" ]] && exit 1
      warn "Continuando sin verificación de checksum."
    fi
  else
    warn "No se encontró archivo de checksum (.sha256). No se puede verificar integridad."
  fi
}

# ── Parsing de argumentos ─────────────────────────────────────────────────────

BACKUP_FILE=""
S3_MODE=false

case "${1:-}" in
  --list)
    list_backups
    exit 0
    ;;
  --latest)
    BACKUP_FILE=$(find "$BACKUP_DIR" -name "docuflow_*.sql.gz" | sort -r | head -1 2>/dev/null || true)
    if [[ -z "$BACKUP_FILE" ]]; then
      err "No se encontraron backups locales en $BACKUP_DIR"
      exit 1
    fi
    log "Backup más reciente: $BACKUP_FILE"
    ;;
  --s3)
    S3_URL="${2:-}"
    if [[ -z "$S3_URL" ]]; then
      err "Debés especificar la URL de S3: $0 --s3 s3://bucket/key.sql.gz"
      exit 1
    fi
    S3_MODE=true
    BACKUP_FILE="/tmp/$(basename "$S3_URL")"
    ;;
  "")
    usage
    ;;
  *)
    BACKUP_FILE="$1"
    ;;
esac

# ── Verificaciones previas ────────────────────────────────────────────────────

command -v psql >/dev/null 2>&1 || { err "psql no encontrado. Instalá postgresql-client."; exit 1; }
command -v gunzip >/dev/null 2>&1 || { err "gunzip no encontrado."; exit 1; }

if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
  err "POSTGRES_PASSWORD no está configurada."
  exit 1
fi

# ── Descargar desde S3 si corresponde ─────────────────────────────────────────

if [[ "$S3_MODE" == "true" ]]; then
  command -v aws >/dev/null 2>&1 || { err "aws CLI no encontrado. Instalá awscli."; exit 1; }
  log "Descargando desde S3: $S3_URL → $BACKUP_FILE"
  aws s3 cp "$S3_URL" "$BACKUP_FILE"
  aws s3 cp "${S3_URL}.sha256" "${BACKUP_FILE}.sha256" 2>/dev/null || true
  ok "Descarga completada."
fi

# ── Verificar archivo ─────────────────────────────────────────────────────────

if [[ ! -f "$BACKUP_FILE" ]]; then
  err "El archivo '$BACKUP_FILE' no existe."
  exit 1
fi

FILESIZE=$(stat -c%s "$BACKUP_FILE" 2>/dev/null || echo 0)
if [[ "$FILESIZE" -lt 100 ]]; then
  err "El archivo parece vacío o inválido ($FILESIZE bytes)."
  exit 1
fi

# ── Verificar checksum ────────────────────────────────────────────────────────

verify_checksum "$BACKUP_FILE"

# ── Verificar integridad gzip ─────────────────────────────────────────────────

log "Verificando integridad del archivo gzip..."
if gunzip -t "$BACKUP_FILE" 2>/dev/null; then
  ok "Archivo gzip válido."
else
  err "El archivo gzip está corrupto."
  exit 1
fi

# ── Confirmación del usuario ──────────────────────────────────────────────────

SIZE_HR=$(du -sh "$BACKUP_FILE" | cut -f1)

echo ""
echo "  ┌──────────────────────────────────────────────────┐"
echo "  │            ⚠️  RESTAURACIÓN DE BASE DE DATOS       │"
echo "  └──────────────────────────────────────────────────┘"
echo ""
echo "  Base de datos : $DB_NAME @ $DB_HOST:$DB_PORT"
echo "  Backup        : $(basename "$BACKUP_FILE")  ($SIZE_HR)"
echo ""
echo "  ADVERTENCIA: Todos los datos actuales serán ELIMINADOS"
echo "  y reemplazados con el contenido del backup."
echo ""
read -r -p "  ¿Confirmás la restauración? Escribí 'RESTAURAR' para continuar: " CONFIRM

if [[ "$CONFIRM" != "RESTAURAR" ]]; then
  log "Restauración cancelada por el usuario."
  exit 0
fi

# ── Verificar conectividad ────────────────────────────────────────────────────

log "Verificando conectividad con PostgreSQL..."
if ! PGPASSWORD="$POSTGRES_PASSWORD" pg_isready \
    -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
    -q 2>/dev/null; then
  err "No se puede conectar a PostgreSQL en $DB_HOST:$DB_PORT"
  exit 1
fi

# ── Ejecutar restauración ─────────────────────────────────────────────────────

log "Iniciando restauración..."
START_TIME=$(date +%s)

PGPASSWORD="$POSTGRES_PASSWORD" gunzip -c "$BACKUP_FILE" | psql \
  -h "$DB_HOST" \
  -p "$DB_PORT" \
  -U "$DB_USER" \
  -d "$DB_NAME" \
  --no-password \
  -v ON_ERROR_STOP=0 \
  2>&1 | grep -v "^NOTICE\|^SET\|^CREATE\|^ALTER\|^DROP\|^COMMENT\|^INSERT\|^UPDATE\|^DELETE\|^COPY\|^INDEX\|rows)" \
  || true   # ON_ERROR_STOP=0 no falla en errores no críticos (p.ej. objetos ya existentes)

DURATION=$(( $(date +%s) - START_TIME ))

ok "Restauración completada en ${DURATION}s"
log ""
log "  Base  : $DB_NAME @ $DB_HOST:$DB_PORT"
log "  Desde : $(basename "$BACKUP_FILE")"
log "  Duró  : ${DURATION}s"
log ""
log "Próximos pasos recomendados:"
log "  1. Ejecutar migraciones pendientes: alembic upgrade head"
log "  2. Reiniciar los servicios: docker compose restart api worker beat"
log "  3. Verificar salud: curl http://localhost:8000/api/v1/health"
