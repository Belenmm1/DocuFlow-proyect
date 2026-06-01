export const t = {
  // Nav
  dashboard:       "Dashboard",
  documents:       "Documentos",
  settings:        "Configuración",
  logout:          "Cerrar sesión",
  // Actions
  upload:          "Subir documento",
  reprocess:       "Reprocesar",
  compare:         "Comparar",
  export:          "Exportar",
  chat:            "Chat",
  // Status
  processing:      "Procesando",
  pending:         "Pendiente",
  done:            "Listo",
  failed:          "Error",
  // Labels
  aiSummary:       "Resumen IA",
  sentiment:       "Sentimiento",
  keywords:        "Palabras clave",
  category:        "Categoría",
  entities:        "Entidades",
  filename:        "Archivo",
  fileSize:        "Tamaño",
  pages:           "Páginas",
  createdAt:       "Fecha",
  updatedAt:       "Actualizado",
  // Categories
  contrato:        "Contrato",
  factura:         "Factura",
  informe:         "Informe",
  cv:              "CV",
  resolucion:      "Resolución",
  presentacion:    "Presentación",
  academico:       "Académico",
  legal:           "Legal",
  medico:          "Médico",
  otro:            "Otro",
  // Dashboard
  processedToday:  "Procesados hoy",
  avgTime:         "Tiempo promedio",
  withErrors:      "Con errores",
  totalDocs:       "Total documentos",
  // Plan
  freePlan:        "Plan Gratuito",
  proPlan:         "Plan Pro",
  limitReached:    "Límite mensual alcanzado",
  upgradePrompt:   "Actualizá tu plan para seguir procesando",
  docsRemaining:   "documentos restantes este mes",
  // Chat
  chatWith:        "Chat con",
  askQuestion:     "Hacé una pregunta sobre este documento...",
  send:            "Enviar",
  chatEmpty:       "Hacé tu primera pregunta sobre este documento",
  suggestedQ:      "Preguntas sugeridas",
  // Errors
  errorLoading:    "Error al cargar",
  errorProcessing: "Error al procesar",
  notFound:        "Documento no encontrado",
  // Misc
  noDocuments:     "No hay documentos aún",
  uploadFirst:     "Subí tu primer documento para comenzar",
  of:              "de",
  results:         "resultados",
} as const

export type TranslationKey = keyof typeof t
