# Dependency Graph

Multi-language intra-repository dependency analysis.

Supports Python, JavaScript/TypeScript, C/C++, Rust, Go, Java, C#, Swift, HTML/CSS, and SQL.

Includes classification of external dependencies as stdlib vs third-party.

## Statistics

- **Total files**: 8
- **Intra-repo dependencies**: 7
- **External stdlib dependencies**: 11
- **External third-party dependencies**: 15

## External Dependencies

### Standard Library / Core Modules

Total: 11 unique modules

- `datetime.datetime`
- `datetime.timezone`
- `functools.lru_cache`
- `logging`
- `os`
- `threading`
- `time`
- `typing.Annotated`
- `typing.Any`
- `typing.Literal`
- `typing.Optional`

### Third-Party Packages

Total: 15 unique packages

- `fastapi.APIRouter`
- `fastapi.Depends`
- `fastapi.FastAPI`
- `fastapi.HTTPException`
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
- `uvicorn`

## Most Depended Upon Files (Intra-Repo)

- `app/config.py` (3 dependents)
- `app/firestore.py` (1 dependents)
- `app/routers/firestore_test.py` (1 dependents)
- `app/dependencies.py` (1 dependents)
- `app/__init__.py` (1 dependents)

## Files with Most Dependencies (Intra-Repo)

- `app/main.py` (2 dependencies)
- `app/routers/firestore_test.py` (2 dependencies)
- `app/dependencies.py` (1 dependencies)
- `app/firestore.py` (1 dependencies)
- `example_openai_usage.py` (1 dependencies)
