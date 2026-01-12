# Dependency Graph

Multi-language intra-repository dependency analysis.

Supports Python, JavaScript/TypeScript, C/C++, Rust, Go, Java, C#, Swift, HTML/CSS, and SQL.

Includes classification of external dependencies as stdlib vs third-party.

## Statistics

- **Total files**: 19
- **Intra-repo dependencies**: 29
- **External stdlib dependencies**: 23
- **External third-party dependencies**: 30

## External Dependencies

### Standard Library / Core Modules

Total: 23 unique modules

- `contextvars.ContextVar`
- `datetime.datetime`
- `datetime.timedelta`
- `datetime.timezone`
- `enum.Enum`
- `functools.lru_cache`
- `json`
- `logging`
- `os`
- `random`
- `sys`
- `threading`
- `time`
- `typing.Annotated`
- `typing.Any`
- `typing.Callable`
- `typing.List`
- `typing.Literal`
- `typing.Optional`
- `typing.Union`
- ... and 3 more (see JSON for full list)

### Third-Party Packages

Total: 30 unique packages

- `fastapi.APIRouter`
- `fastapi.Depends`
- `fastapi.FastAPI`
- `fastapi.HTTPException`
- `fastapi.Header`
- `fastapi.Request`
- `fastapi.Response`
- `fastapi.exceptions.RequestValidationError`
- `fastapi.responses.JSONResponse`
- `fastapi.status`
- `fastapi.testclient.TestClient`
- `google.cloud.firestore`
- `openai`
- `openai.OpenAI`
- `pydantic.BaseModel`
- `pydantic.ConfigDict`
- `pydantic.Field`
- `pydantic.ValidationError`
- `pydantic.ValidationInfo`
- `pydantic.field_validator`
- ... and 10 more (see JSON for full list)

## Most Depended Upon Files (Intra-Repo)

- `app/config.py` (7 dependents)
- `app/models.py` (6 dependents)
- `app/logging.py` (4 dependents)
- `app/dependencies.py` (4 dependents)
- `app/firestore.py` (2 dependents)
- `app/main.py` (2 dependents)
- `app/routers/firestore_test.py` (1 dependents)
- `app/routers/characters.py` (1 dependents)
- `app/middleware.py` (1 dependents)
- `app/__init__.py` (1 dependents)

## Files with Most Dependencies (Intra-Repo)

- `app/main.py` (5 dependencies)
- `app/routers/characters.py` (4 dependencies)
- `app/routers/firestore_test.py` (3 dependencies)
- `tests/test_narrative_turns.py` (3 dependencies)
- `app/middleware.py` (2 dependencies)
- `tests/test_characters.py` (2 dependencies)
- `tests/test_combat.py` (2 dependencies)
- `app/__init__.py` (1 dependencies)
- `app/dependencies.py` (1 dependencies)
- `app/firestore.py` (1 dependencies)
