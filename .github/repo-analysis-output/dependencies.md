# Dependency Graph

Multi-language intra-repository dependency analysis.

Supports Python, JavaScript/TypeScript, C/C++, Rust, Go, Java, C#, Swift, HTML/CSS, and SQL.

Includes classification of external dependencies as stdlib vs third-party.

## Statistics

- **Total files**: 4
- **Intra-repo dependencies**: 2
- **External stdlib dependencies**: 6
- **External third-party dependencies**: 9

## External Dependencies

### Standard Library / Core Modules

Total: 6 unique modules

- `functools.lru_cache`
- `logging`
- `time`
- `typing.Any`
- `typing.Literal`
- `typing.Optional`

### Third-Party Packages

Total: 9 unique packages

- `fastapi.FastAPI`
- `openai`
- `openai.OpenAI`
- `pydantic.Field`
- `pydantic.ValidationInfo`
- `pydantic.field_validator`
- `pydantic_settings.BaseSettings`
- `pydantic_settings.SettingsConfigDict`
- `uvicorn`

## Most Depended Upon Files (Intra-Repo)

- `app/config.py` (1 dependents)
- `app/__init__.py` (1 dependents)

## Files with Most Dependencies (Intra-Repo)

- `app/main.py` (1 dependencies)
- `example_openai_usage.py` (1 dependencies)
