# Journey Log API

A FastAPI-based service for managing journey logs and entries. Built with Python 3.12+ (targeting Python 3.14), FastAPI, and Google Cloud Firestore.

## Features

- **Health Check Endpoint**: `/health` - Returns service status and basic identifiers
- **Info Endpoint**: `/info` - Returns build and configuration metadata
- **Environment-based Configuration**: Uses Pydantic Settings for type-safe configuration
- **Google Cloud Integration**: Ready for Cloud Run deployment with Firestore support

## Requirements

- **Python**: 3.12+ (targeting 3.14 for production)
- **Package Manager**: `uv` (preferred) or `pip`
- **Dependencies**: See `requirements.txt`

## Local Development Setup

### 1. Create a Virtual Environment

```bash
# Using Python's built-in venv
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# OR using uv (preferred)
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

### 2. Install Dependencies

```bash
# Using pip
pip install -r requirements.txt

# OR using uv (preferred)
uv pip install -r requirements.txt
```

### 3. Configure Environment Variables

Copy the example environment file and customize it:

```bash
cp .env.example .env
```

Edit `.env` and set the required variables:
- `GCP_PROJECT_ID`: Your Google Cloud Project ID (required for non-dev environments)
- `SERVICE_ENVIRONMENT`: Set to `dev`, `staging`, or `prod`
- Other optional variables as needed

### 4. Run the Service Locally

```bash
# Using uvicorn directly
uvicorn app.main:app --reload --host 127.0.0.1 --port 8080

# OR using Python module
python -m app.main

# OR using uv (preferred)
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8080
```

The service will be available at:
- **API**: http://127.0.0.1:8080
- **Health Check**: http://127.0.0.1:8080/health
- **Info**: http://127.0.0.1:8080/info
- **API Docs**: http://127.0.0.1:8080/docs
- **ReDoc**: http://127.0.0.1:8080/redoc

## Running Without Firestore Credentials

For local development, you can run the service without Firestore credentials. The `/health` and `/info` endpoints do not require Firestore access. When you add endpoints that use Firestore, you'll need to:

1. Create a GCP Service Account with Firestore permissions
2. Download the credentials JSON file
3. Set the `GOOGLE_APPLICATION_CREDENTIALS` environment variable to the file path

## Environment Variables

See `.env.example` for a complete list of available environment variables with descriptions.

### Required Variables
- `GCP_PROJECT_ID`: Required in `staging` and `prod` environments

### Optional Variables
- `SERVICE_ENVIRONMENT`: Defaults to `dev`
- `SERVICE_NAME`: Defaults to `journey-log`
- `FIRESTORE_JOURNEYS_COLLECTION`: Defaults to `journeys`
- `FIRESTORE_ENTRIES_COLLECTION`: Defaults to `entries`
- `API_HOST`: Defaults to `127.0.0.1`
- `API_PORT`: Defaults to `8080`
- `LOG_LEVEL`: Defaults to `INFO`

## Development

### Code Quality

This project uses:
- **Ruff**: For linting and formatting
- **MyPy**: For static type checking
- **Pytest**: For testing

```bash
# Run linter
ruff check .

# Format code
ruff format .

# Type checking
mypy app/

# Run tests
pytest
```

## Deployment

This service is designed to run on Google Cloud Run. See `gcp_deployment_reference.md` for detailed deployment instructions.



# Permanents (License, Contributing, Author)

Do not change any of the below sections

## License

This Agent Foundry Project is licensed under the Apache 2.0 License - see the LICENSE file for details.

## Contributing

Feel free to submit issues and enhancement requests!

## Author

Created by Agent Foundry and John Brosnihan
