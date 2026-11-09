"""Start FashionStore against the isolated local multitenant demo database."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.scripts.preparar_demo_tenants import DB_NAME, _local_test_url  # noqa: E402


def main() -> None:
    os.environ["DATABASE_URL"] = _local_test_url()
    os.environ["POSTGRES_DB"] = DB_NAME
    print(f"Iniciando API con la base local aislada: {DB_NAME}", flush=True)

    import uvicorn

    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
