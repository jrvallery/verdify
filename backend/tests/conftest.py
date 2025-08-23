import os

# Minimal environment to allow app.settings to initialize in tests
os.environ.setdefault("ENVIRONMENT", "local")
os.environ.setdefault("PROJECT_NAME", "Verdify API")
os.environ.setdefault("POSTGRES_SERVER", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_USER", "postgres")
os.environ.setdefault("POSTGRES_PASSWORD", "changethis")
os.environ.setdefault("POSTGRES_DB", "verdify")
os.environ.setdefault("FIRST_SUPERUSER", "admin@example.com")
os.environ.setdefault("FIRST_SUPERUSER_PASSWORD", "changethis")
os.environ.setdefault("FRONTEND_HOST", "http://localhost:5173")
