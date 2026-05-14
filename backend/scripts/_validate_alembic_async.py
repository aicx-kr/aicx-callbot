"""ad-hoc validation: alembic upgrade head with SQLite async."""
import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:////tmp/callbot_async_test.db"

# remove existing db so we exercise the full upgrade chain
db_path = Path("/tmp/callbot_async_test.db")
if db_path.exists():
    db_path.unlink()

backend_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_root))
os.chdir(backend_root)

from alembic import command
from alembic.config import Config

cfg = Config(str(backend_root / "alembic.ini"))
cfg.set_main_option("script_location", str(backend_root / "alembic"))
command.upgrade(cfg, "head")
print("UPGRADE OK")

# 테이블 개수 확인
import sqlite3
conn = sqlite3.connect("/tmp/callbot_async_test.db")
rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
print(f"\n생성된 테이블 ({len(rows)}):")
for r in rows:
    print(f"  - {r[0]}")
conn.close()
