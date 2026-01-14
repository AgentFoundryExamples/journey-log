# Dependency Graph

Multi-language intra-repository dependency analysis.

Supports Python, JavaScript/TypeScript, C/C++, Rust, Go, Java, C#, Swift, HTML/CSS, and SQL.

Includes classification of external dependencies as stdlib vs third-party.

## Statistics

- **Total files**: 24
- **Intra-repo dependencies**: 38
- **External stdlib dependencies**: 30
- **External third-party dependencies**: 32

## External Dependencies

### Standard Library / Core Modules

Total: 30 unique modules

- `argparse`
- `contextvars.ContextVar`
- `copy`
- `datetime.datetime`
- `datetime.timedelta`
- `datetime.timezone`
- `enum.Enum`
- `functools.lru_cache`
- `json`
- `logging`
- `os`
- `random`
- `re`
- `sys`
- `threading`
- `time`
- `traceback`
- `typing.Annotated`
- `typing.Any`
- `typing.Callable`
- ... and 10 more (see JSON for full list)

### Third-Party Packages

Total: 32 unique packages

- `fastapi.APIRouter`
- `fastapi.Depends`
- `fastapi.FastAPI`
- `fastapi.HTTPException`
- `fastapi.Header`
- `fastapi.Query`
- `fastapi.Request`
- `fastapi.Response`
- `fastapi.exceptions.RequestValidationError`
- `fastapi.responses.JSONResponse`
- `fastapi.status`
- `fastapi.testclient.TestClient`
- `google.cloud.exceptions.GoogleCloudError`
- `google.cloud.firestore`
- `openai`
- `openai.OpenAI`
- `pydantic.BaseModel`
- `pydantic.ConfigDict`
- `pydantic.Field`
- `pydantic.ValidationError`
- ... and 12 more (see JSON for full list)

## Most Depended Upon Files (Intra-Repo)

- `app/models.py` (8 dependents)
- `app/config.py` (7 dependents)
- `app/logging.py` (6 dependents)
- `app/dependencies.py` (5 dependents)
- `app/main.py` (5 dependents)
- `app/firestore.py` (3 dependents)
- `app/routers/firestore_test.py` (1 dependents)
- `app/routers/characters.py` (1 dependents)
- `app/middleware.py` (1 dependents)
- `app/__init__.py` (1 dependents)

## Files with Most Dependencies (Intra-Repo)

- `app/main.py` (5 dependencies)
- `app/routers/characters.py` (5 dependencies)
- `app/routers/firestore_test.py` (3 dependencies)
- `tests/test_narrative_turns.py` (3 dependencies)
- `app/firestore.py` (2 dependencies)
- `app/middleware.py` (2 dependencies)
- `tests/test_characters.py` (2 dependencies)
- `tests/test_combat.py` (2 dependencies)
- `tests/test_context_aggregation.py` (2 dependencies)
- `tests/test_status_validation.py` (2 dependencies)
