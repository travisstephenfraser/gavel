import json
import os
from urllib.parse import quote_plus

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv:
    load_dotenv()


def _validate_env_value(name: str, value: str | None) -> str:
    if value is None or value.strip() == "":
        raise ValueError(f"Missing required environment variable: {name}")
    if any(ch in value for ch in ("\n", "\r", "\x00")):
        raise ValueError(f"Invalid value for {name}: contains unsafe control characters")
    return value


def load_db_config(path: str) -> str:
    """Load database connection string from a JSON config file."""
    try:
        with open(path, encoding="utf-8") as f:
            try:
                config = json.load(f)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON config file: {exc}") from exc
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Config file not found: {path}") from exc
    except OSError as exc:
        raise OSError(f"Unable to read config file '{path}': {exc}") from exc

    database = config.get("database", {})
    host = database.get("host")
    port = database.get("port", 5432)
    name = database.get("name")

    if not host or not name:
        raise ValueError("Missing required database settings: 'database.host' and 'database.name'")
    if not isinstance(port, int) or port < 1 or port > 65535:
        raise ValueError("Invalid database port. Expected an integer between 1 and 65535.")

    user = _validate_env_value("DB_USER", os.environ.get("DB_USER"))
    password = _validate_env_value("DB_PASSWORD", os.environ.get("DB_PASSWORD"))

    encoded_user = quote_plus(user)
    encoded_password = quote_plus(password)
    encoded_host = quote_plus(str(host))
    encoded_name = quote_plus(str(name))
    return f"postgresql://{encoded_user}:{encoded_password}@{encoded_host}:{port}/{encoded_name}"
