import json

def load_db_config(path: str) -> str:
    """Load database connection string from a JSON config file."""
    with open(path) as f:
        config = json.load(f)
    host = config["database"]["host"]
    port = config["database"]["port"]
    name = config["database"]["name"]
    user = config["credentials"]["username"]
    password = config["credentials"]["password"]
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"
