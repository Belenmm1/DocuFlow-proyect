#!/usr/bin/env bash
# scripts/docker.sh
#
# Utilidad de administración Docker para DocuFlow.
# Uso: ./scripts/docker.sh <comando>

set -euo pipefail

COMPOSE="docker compose"
DC_FILE="-f docker-compose.yml"

# En CI/prod, no usar override
if [[ "${CI:-false}" == "true" ]] || [[ "${ENVIRONMENT:-dev}" == "production" ]]; then
  DC_FILE="-f docker-compose.yml"
else
  DC_FILE="-f docker-compose.yml -f docker-compose.override.yml"
fi

usage() {
  cat <<EOF
DocuFlow Docker — comandos disponibles:

  up          Levantar todos los servicios (build si es necesario)
  down        Bajar todos los servicios
  restart     Reiniciar todos los servicios
  logs        Ver logs en tiempo real (todos los servicios)
  logs <svc>  Ver logs de un servicio específico (api|worker|beat|db|redis|frontend)

  migrate     Ejecutar migraciones Alembic (alembic upgrade head)
  shell       Abrir bash en el contenedor api
  psql        Abrir psql en el contenedor db

  build       Construir imágenes sin cache
  pull        Actualizar imágenes base

  backup      Ejecutar backup manual de PostgreSQL
  status      Estado de todos los servicios + health checks

EOF
}

case "${1:-help}" in
  up)
    echo "🚀 Levantando DocuFlow..."
    $COMPOSE $DC_FILE up -d --build
    echo "✅ Servicios levantados. API: http://localhost:${API_PORT:-8000}/docs"
    ;;

  down)
    $COMPOSE $DC_FILE down
    ;;

  restart)
    $COMPOSE $DC_FILE restart
    ;;

  logs)
    SVC="${2:-}"
    $COMPOSE $DC_FILE logs -f --tail=100 $SVC
    ;;

  migrate)
    echo "🔄 Ejecutando migraciones..."
    $COMPOSE $DC_FILE exec api alembic upgrade head
    ;;

  shell)
    $COMPOSE $DC_FILE exec api bash
    ;;

  psql)
    $COMPOSE $DC_FILE exec db psql -U "${POSTGRES_USER:-docuflow}" -d "${POSTGRES_DB:-docuflow}"
    ;;

  build)
    $COMPOSE $DC_FILE build --no-cache
    ;;

  pull)
    $COMPOSE $DC_FILE pull
    ;;

  backup)
    echo "💾 Ejecutando backup manual..."
    $COMPOSE $DC_FILE exec worker bash /app/scripts/backup.sh
    ;;

  status)
    $COMPOSE $DC_FILE ps
    echo ""
    echo "Health checks:"
    for svc in api worker frontend db redis; do
      STATUS=$(docker inspect --format='{{.State.Health.Status}}' "docuflow-${svc}" 2>/dev/null || echo "n/a")
      echo "  ${svc}: ${STATUS}"
    done
    ;;

  help|*)
    usage
    ;;
esac
