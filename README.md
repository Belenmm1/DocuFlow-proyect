# DocuFlow: Intelligent Document Processing System

DocuFlow is a high-performance REST API designed to automate the extraction, analysis, and synthesis of data from unstructured documents. Built with a focus on scalability and reliability, it leverages Large Language Models (LLMs) and an asynchronous task architecture to transform raw files into structured, actionable intelligence.

## System Overview

The core mission of DocuFlow is to bridge the gap between static documents (PDF, DOCX, XLSX) and structured data. By combining **FastAPI** for low-latency requests and **Celery** for long-running background tasks, the system ensures a non-blocking user experience even when processing high-volume datasets.

## Technical Stack

* **Backend:** FastAPI (Python)
* **Database:** SQLAlchemy ORM with support for SQLite (Development) and PostgreSQL (Production).
* **Asynchronous Processing:** Celery + Redis (Message Broker).
* **AI Engine:** LangChain + OpenAI (GPT-4o-mini).
* **Document Extraction:** `pdfplumber`, `python-docx`, and `pandas`.
* **Reporting:** `ReportLab` (PDF generation) and `XlsxWriter` (Excel exports).
* **Frontend Dashboard:** Streamlit.

## Architecture and Workflow

DocuFlow implements an event-driven architecture to handle document processing:

1.  **Ingestion:** The client submits a file via `POST /api/v1/documents/upload`.
2.  **Acknowledgment:** The API performs initial validation and returns a `202 Accepted` status immediately, providing a task ID.
3.  **Task Queuing:** A record is created in the database with a "pending" status, and a task is dispatched to the Celery worker via Redis.
4.  **Processing Pipeline:**
    * **Extraction:** The worker identifies the MIME type and extracts raw text using specialized libraries.
    * **Analysis:** The extracted text is processed through a LangChain pipeline, where GPT-4o-mini performs entity extraction and semantic analysis.
5.  **Persistence:** Results are saved to the relational database and cached in Redis for rapid retrieval.
6.  **Retrieval:** The client monitors progress via `GET /api/v1/documents/{id}/status` until completion.

## AI Analysis Capabilities

The system produces a comprehensive JSON metadata object for every document:

* **Executive Summary:** A concise overview of the document content.
* **Classification:** Automatic detection of document type (Invoice, Contract, Report, etc.).
* **Key Points:** Identification of the most relevant information.
* **Entity Recognition:** Extraction of specific names, organizations, dates, and monetary amounts.
* **Sentiment Analysis:** Detection of the document's underlying tone.
* **Language Detection:** Automatic identification of the source language.

## Project Structure

```text
docuflow/
├── app/
│   ├── api/v1/         # Endpoints for authentication, documents, and reports
│   ├── core/           # Security headers, rate limiting, and middleware
│   ├── models/         # SQLAlchemy ORM definitions
│   ├── schemas/        # Pydantic models for request/response validation
│   ├── services/       # Core logic for AI analysis and extraction
│   └── utils/          # Logging and file handling utilities
├── streamlit_app/      # Visual dashboard for end-users
├── tests/              # Unit and integration tests
└── requirements.txt    # Project dependencies
