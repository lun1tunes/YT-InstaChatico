# Instachatico Architecture Snapshot

## Layers & Responsibilities
- **FastAPI routers (`src/api_v1`)** – validate requests, translate HTTP ↔ use case DTOs, and delegate work via dependency-injected factories.
- **Use cases (`core/use_cases`)** – implement business rules. They coordinate repositories, domain services, and background tasks without touching framework code.
- **Services (`core/services`)** – integrations and domain helpers (OpenAI agents, Instagram API, S3, document processing, rate limiting, etc.). All are exposed through light protocols in `core/interfaces`.
- **Repositories (`core/repositories`)** – async SQLAlchemy data access for models defined in `core/models`.
- **Infrastructure (`core/container`, `core/tasks`, `core/infrastructure`)** – Dependency Injector container wires everything; Celery tasks orchestrate background pipelines; Redis, S3, and other clients live here.

## Dependency Flow
`HTTP request → Router → Use case → (Repositories ↔ Models) + (Services / Task Queue)`

- Routers obtain dependencies via `core/dependencies` (e.g., `get_process_webhook_comment_use_case`, `get_task_queue`).
- Use cases never pull from the container; they receive repositories, services, and task queues as constructor arguments.
- Services and repositories wrap external systems (OpenAI, Instagram Graph API, Selectel S3, PostgreSQL/pgvector).

## Core Workflows
- **Webhook ingestion**: Instagram POST → `ProcessWebhookCommentUseCase` → ensure media + comment records → queue classification task → downstream answer/hide/notification tasks.
- **Document pipeline**: `/documents/register|upload` → store metadata → queue `process_document_task` → S3 download + markdown extraction → context exposed to answer agents.
- **Comment management**: listing and detail endpoints read through repositories; hide/reply actions queue Celery tasks; unhide calls `HideCommentUseCase` directly for immediate feedback.
- **AI agents**: classification/answer services maintain session state via `AgentSessionService`, call OpenAI Agents, and persist token usage/results for analytics.
- **Background tasks**: Celery workers resolve the same use cases, ensuring consistent orchestration whether triggered from HTTP or async pipelines.

## Testing Strategy
- **Unit tests** cover repositories, services, utils.
- **Integration tests (`tests/integration`)** exercise routers end-to-end using in-memory SQLite and stubbed infrastructure.
