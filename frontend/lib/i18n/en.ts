export const t = {
  // Nav
  dashboard:       "Dashboard",
  documents:       "Documents",
  settings:        "Settings",
  logout:          "Log out",
  // Actions
  upload:          "Upload document",
  reprocess:       "Reprocess",
  compare:         "Compare",
  export:          "Export",
  chat:            "Chat",
  // Status
  processing:      "Processing",
  pending:         "Pending",
  done:            "Done",
  failed:          "Error",
  // Labels
  aiSummary:       "AI Summary",
  sentiment:       "Sentiment",
  keywords:        "Keywords",
  category:        "Category",
  entities:        "Entities",
  filename:        "File",
  fileSize:        "Size",
  pages:           "Pages",
  createdAt:       "Date",
  updatedAt:       "Updated",
  // Categories
  contrato:        "Contract",
  factura:         "Invoice",
  informe:         "Report",
  cv:              "Resume",
  resolucion:      "Resolution",
  presentacion:    "Presentation",
  academico:       "Academic",
  legal:           "Legal",
  medico:          "Medical",
  otro:            "Other",
  // Dashboard
  processedToday:  "Processed today",
  avgTime:         "Avg. time",
  withErrors:      "With errors",
  totalDocs:       "Total documents",
  // Plan
  freePlan:        "Free Plan",
  proPlan:         "Pro Plan",
  limitReached:    "Monthly limit reached",
  upgradePrompt:   "Upgrade your plan to keep processing",
  docsRemaining:   "documents remaining this month",
  // Chat
  chatWith:        "Chat with",
  askQuestion:     "Ask a question about this document...",
  send:            "Send",
  chatEmpty:       "Ask your first question about this document",
  suggestedQ:      "Suggested questions",
  // Errors
  errorLoading:    "Error loading",
  errorProcessing: "Error processing",
  notFound:        "Document not found",
  // Misc
  noDocuments:     "No documents yet",
  uploadFirst:     "Upload your first document to get started",
  of:              "of",
  results:         "results",
} as const

export type TranslationKey = keyof typeof t
