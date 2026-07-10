import os

import uvicorn


def env_bool(name: str, default: bool = False) -> bool:
	value = os.getenv(name)
	if value is None:
		return default
	return value.lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
	try:
		return int(os.getenv(name, str(default)))
	except ValueError:
		return default


if __name__ == "__main__":
	uvicorn.run(
		"main:app",
		host=os.getenv("APP_HOST", "0.0.0.0"),
		port=env_int("APP_PORT", 8000),
		reload=env_bool("APP_RELOAD", True),
	)
