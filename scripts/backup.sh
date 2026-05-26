#!/usr/bin/env bash
# =============================================================================
# scripts/backup.sh — Bloque 7.4
#
# Backup automático de PostgreSQL para DocuFlow.
# Invocado por Celery Beat cada 24hs (00:00 UTC) o manualmente.
#
# Uso:
#   ./scripts/backup.sh                        # backup normal
#   ./scripts/backup.sh --verify               # backup + verificar integridad
#   BACKUP_S3_BUCKET=mi-bucket ./scripts/backup.sh  # backup + subir a S3
#
# Variables de entorno (todas opcionales salvo las DB):
#   POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB  ← requeridas
#   DB_HOST              (default: db)
#   DB_PORT              (default: 5432)
#   BACKUP_DIR           (default: /app/backups)
#   BACKUP_RETENTION_DAYS (default: 30)
#   BACKUP_S3_BUCKET     (vacío = no subir a S3)
#   BACKUP_S3_PREFIX     (default: docuflow-backups)
#   BACKUP_VERIFY        (true/false, default: false)
#
# Salida:
#   /app/backups/docuflow_YYYYMMDD_HHMMSS.sql.gz
#   /app/backups/docuflow_YYYYMMDD_HHMMSS.sql.gz.sha256
# =============================================================================

set -euo pipefail

# ── Configuración ─────────────────────────────────────────────────────────────
BACKUP_DIR="${BACKUP_DIR:-/app/backups}"
DB_HOST="${DB_HOST:-db}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${POSTGRES_USER:-docuflow}"
DB_NAME="${POSTGRES_DB:-docuflow}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
S3_BUCKET="${BACKUP_S3_BUCKET:-}"
S3_PREFIX="${BACKUP_S3_PREFIX:-docuflow-backups}"
VERIFY="${BACKUP_VERIFY:-false}"

# Argumento --verify
for arg in "$@"; do
  [[ "$arg" == "--verify" ]] && VERIFY="true"
done

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
FILENAME="${BACKUP_DIR}/docuflow_${TIMESTAMP}.sql.gz"
CHECKSUM_FILE="${FILENAME}.sha256"
START_TIME=$(date +%s)

# ── Funciones ─────────────────────────────────────────────────────────────────

log()  { echo "[backup][$(date '+%H:%M:%S')] $*"; }
err()  { echo "[backup][$(date '+%H:%M:%S')] ❌ ERROR: $*" >&2; }
ok()   { echo "[backup][$(date '+%H:%M:%S')] ✅ $*"; }
warn() { echo "[backup][$(date '+%H:%M:%S')] ⚠️  $*"; }

cleanup_on_error() {
  local exit_code=$?
  if [[ $exit_code -ne 0 ]]; then
    err "Backup falló (código $exit_code). Eliminando archivo parcial..."
    [[ -f "$FILENAME" ]] && rm -f "$FILENAME"
    [[ -f "$CHECKSUM_FILE" ]] && rm -f "$CHECKSUM_FILE"
  fi
}
trap cleanup_on_error EXIT

# ── Verificaciones previas ────────────────────────────────────────────────────

log "Verificando dependencias..."
command -v pg_dump  >/dev/null 2>&1 || { err "pg_dump no encontrado. Instalá postgresql-client en la imagen."; exit 1; }
command -v gzip     >/dev/null 2>&1 || { err "gzip no encontrado."; exit 1; }
command -v sha256sum >/dev/null 2>&1 || { err "sha256sum no encontrado."; exit 1; }

if [[ -z "${POSTGRES_PASSWORD:-}" ]]; then
  err "POSTGRES_PASSWORD no está configurada."
  exit 1
fi

# ── Crear directorio de backups ───────────────────────────────────────────────

mkdir -p "$BACKUP_DIR"
log "Directorio de backups: $BACKUP_DIR"

# ── Verificar conectividad con la DB ─────────────────────────────────────────

log "Verificando conectividad con PostgreSQL ($DB_HOST:$DB_PORT)..."
if ! PGPASSWORD="$POSTGRES_PASSWORD" pg_isready \
    -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
    -q 2>/dev/null; then
  err "No se puede conectar a PostgreSQL en $DB_HOST:$DB_PORT"
  exit 1
fi
log "PostgreSQL disponible."

# ── Ejecutar pg_dump ──────────────────────────────────────────────────────────

log "Iniciando backup → $FILENAME"

PGPASSWORD="$POSTGRES_PASSWORD" pg_dump \
  -h "$DB_HOST" \
  -p "$DB_PORT" \
  -U "$DB_USER" \
  -d "$DB_NAME" \
  --no-password \
  --format=plain \
  --clean \
  --if-exists \
  --verbose \
  2>/tmp/pgdump_stderr.log \
  | gzip -9 > "$FILENAME"

# Verificar que el archivo no esté vacío
FILESIZE=$(stat -c%s "$FILENAME" 2>/dev/null || echo 0)
if [[ "$FILESIZE" -lt 100 ]]; then
  err "El archivo de backup parece vacío o corrupto ($FILESIZE bytes)."
  err "stderr de pg_dump:"
  cat /tmp/pgdump_stderr.log >&2
  exit 1
fi

# ── Generar checksum SHA-256 ──────────────────────────────────────────────────

sha256sum "$FILENAME" > "$CHECKSUM_FILE"
CHECKSUM=$(awk '{print $1}' "$CHECKSUM_FILE")
log "Checksum SHA-256: $CHECKSUM"

# ── Verificar integridad del backup ──────────────────────────────────────────

if [[ "$VERIFY" == "true" ]]; then
  log "Verificando integridad del backup (descompresión de prueba)..."
  if gunzip -t "$FILENAME" 2>/dev/null; then
    ok "Integridad verificada: el archivo gzip es válido."
  else
    err "El archivo gzip está corrupto. Eliminando backup inválido."
    rm -f "$FILENAME" "$CHECKSUM_FILE"
    exit 1
  fi
fi

# ── Métricas del backup ───────────────────────────────────────────────────────

SIZE_HR=$(du -sh "$FILENAME" | cut -f1)
DURATION=$(( $(date +%s) - START_TIME ))

ok "Backup completado en ${DURATION}s"
log "  Archivo : $FILENAME"
log "  Tamaño  : $SIZE_HR"
log "  SHA-256 : $CHECKSUM"

# ── Subir a S3 (opcional) ─────────────────────────────────────────────────────

if [[ -n "$S3_BUCKET" ]]; then
  if command -v aws >/dev/null 2>&1; then
    S3_KEY="${S3_PREFIX}/$(basename "$FILENAME")"
    log "Subiendo backup a s3://${S3_BUCKET}/${S3_KEY}..."

    aws s3 cp "$FILENAME" "s3://${S3_BUCKET}/${S3_KEY}" \
      --storage-class STANDARD_IA \
      --metadata "sha256=${CHECKSUM},duration_s=${DURATION}"

    aws s3 cp "$CHECKSUM_FILE" "s3://${S3_BUCKET}/${S3_KEY}.sha256"

    ok "Backup subido a S3 correctamente."
  else
    warn "BACKUP_S3_BUCKET configurado pero 'aws' CLI no está disponible. Omitiendo subida."
  fi
fi

# ── Rotación: eliminar backups viejos ─────────────────────────────────────────

log "Eliminando backups con más de $RETENTION_DAYS días..."
DELETED=0
while IFS= read -r old_file; do
  rm -f "$old_file" "${old_file}.sha256"
  log "  Eliminado: $(basename "$old_file")"
  (( DELETED++ )) || true
done < <(find "$BACKUP_DIR" -name "docuflow_*.sql.gz" -mtime +"$RETENTION_DAYS" 2>/dev/null)

[[ $DELETED -gt 0 ]] && log "Backups eliminados: $DELETED" || log "No hay backups viejos para eliminar."

# ── Resumen final ─────────────────────────────────────────────────────────────

log ""
log "Backups disponibles en $BACKUP_DIR:"
find "$BACKUP_DIR" -name "docuflow_*.sql.gz" -printf "  %TY-%Tm-%Td %TH:%TM  %f  (%s bytes)\n" 2>/dev/null \
  | sort || echo "  (ninguno)"
log ""

# Exportar nombre del archivo para uso por scripts externos
echo "$FILENAME"
