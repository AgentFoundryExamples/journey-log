# Dependency Graph

Multi-language intra-repository dependency analysis.

Supports Python, JavaScript/TypeScript, C/C++, Rust, Go, Java, C#, Swift, HTML/CSS, and SQL.

Includes classification of external dependencies as stdlib vs third-party.

## Statistics

- **Total files**: 10
- **Intra-repo dependencies**: 13
- **External stdlib dependencies**: 15
- **External third-party dependencies**: 24

## External Dependencies

### Standard Library / Core Modules

Total: 15 unique modules

- `contextvars.ContextVar`
- `datetime.datetime`
- `datetime.timezone`
- `functools.lru_cache`
- `logging`
- `os`
- `sys`
- `threading`
- `time`
- `typing.Annotated`
- `typing.Any`
- `typing.Callable`
- `typing.Literal`
- `typing.Optional`
- `uuid`

### Third-Party Packages

Total: 24 unique packages

- `fastapi.APIRouter`
- `fastapi.Depends`
- `fastapi.FastAPI`
- `fastapi.HTTPException`
- `fastapi.Request`
- `fastapi.Response`
- `fastapi.exceptions.RequestValidationError`
- `fastapi.responses.JSONResponse`
- `fastapi.status`
- `google.cloud.firestore`
- `openai`
- `openai.OpenAI`
- `pydantic.BaseModel`
- `pydantic.Field`
- `pydantic.ValidationInfo`
- `pydantic.field_validator`
- `pydantic_settings.BaseSettings`
- `pydantic_settings.SettingsConfigDict`
- `starlette.middleware.base.BaseHTTPMiddleware`
- `starlette.types.ASGIApp`
- ... and 4 more (see JSON for full list)

## Most Depended Upon Files (Intra-Repo)

- `app/config.py` (5 dependents)
- `app/logging.py` (3 dependents)
- `app/firestore.py` (1 dependents)
- `app/routers/firestore_test.py` (1 dependents)
- `app/middleware.py` (1 dependents)
- `app/dependencies.py` (1 dependents)
- `app/__init__.py` (1 dependents)

## Files with Most Dependencies (Intra-Repo)

- `app/main.py` (4 dependencies)
- `app/routers/firestore_test.py` (3 dependencies)
- `app/middleware.py` (2 dependencies)
- `app/dependencies.py` (1 dependencies)
- `app/firestore.py` (1 dependencies)
- `app/logging.py` (1 dependencies)
- `example_openai_usage.py` (1 dependencies)
