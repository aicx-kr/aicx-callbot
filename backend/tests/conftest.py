"""pytest conftest — 테스트 시작 시 DATABASE_URL 을 격리된 임시 SQLite 로 강제 설정.

이렇게 안 하면:
- src.infrastructure.db 모듈이 임포트되는 순간 기본 URL 로 engine 이 만들어진다.
- 어떤 테스트가 먼저 임포트되었느냐에 따라 어떤 DB 가 쓰이는지 달라져 cross-test pollution 이 발생한다.

conftest 는 pytest 가 테스트 수집 전 가장 먼저 로드하므로 안전하다.
"""

import os
import tempfile

_tmp = tempfile.NamedTemporaryFile(prefix="aicx_callbot_test_", suffix=".db", delete=False)
_tmp.close()
# 빈 파일이라도 OK — alembic 가 schema 를 생성한다.
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp.name}"
