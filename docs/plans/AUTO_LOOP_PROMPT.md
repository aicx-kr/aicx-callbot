# Auto-Loop 메타 프롬프트

루프 한 사이클이 깨어났을 때 따를 절차.

## 입력

이 파일 + `AUTO_LOOP_LOG.md` + `AWKWARDNESS_LOG.md` + `FIX_LOG.md` 를 컨텍스트로 사용.

## 절차

1. **현재 상태 파악**
   - `AUTO_LOOP_LOG.md` 마지막 사이클 확인 → 다음 카테고리 결정 (로테이션: 테스트·성능 → UI → 구조 → 테스트·성능…)
   - 서버 상태 확인: `curl -sf http://localhost:8080/api/health` 실패 시 재시작 (`cd backend && PORT=8080 ./run.sh &`)

2. **타깃 1개 선정** (해당 카테고리 안에서)
   - 테스트·성능: 누락된 endpoint 테스트, 느린 query, 캐시 누수, 메모리 누적, 불필요 fetch
   - UI 어색함: 색상/여백 불일치, 로딩 상태 부재, 빈 상태 UX, 다크모드 깨짐, 키보드 접근성
   - 구조: 중복 코드, 모호한 네이밍, 큰 컴포넌트 분리, 사용 안 하는 코드, 매직넘버
   - 큰 마이그레이션·아키텍처 재설계는 **회피** (사용자 결정 필요)

3. **변경**
   - 가능하면 1~3 파일 이내, ~100줄 이내
   - 기존 패턴/명명 일관성 우선

4. **검증** (필수 — 통과 못 하면 롤백)
   ```bash
   # Backend
   curl -sf http://localhost:8080/api/health || echo "BACKEND DOWN"
   curl -sf http://localhost:8080/api/bots | python3 -c "import sys,json; print(len(json.load(sys.stdin)))"
   curl -sf "http://localhost:8080/api/skills?bot_id=1" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))"

   # Frontend (router redirects → 307 OK)
   curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/bots/1/persona
   curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/bots/1/settings

   # Type-check
   cd /Users/dongwanhong/Desktop/chat-STT-TTS/aicx-callbot/frontend && npx tsc --noEmit 2>&1 | tail -5
   ```

5. **로그 갱신**
   - `AUTO_LOOP_LOG.md` 끝에 새 Cycle 섹션 추가:
     ```
     ### Cycle #N — YYYY-MM-DD HH:MM
     - 카테고리: 테스트·성능 / UI / 구조
     - 변경: <한 줄 요약>
     - 파일: <경로 목록>
     - 동기: <왜 했는지>
     - Smoke: PASS / FAIL (FAIL이면 롤백 사유)
     ```

6. **다음 사이클 스케줄**
   - `ScheduleWakeup`: delaySeconds=**270** (≈5분, 프롬프트 캐시 TTL 안), reason="다음 자동 개선 사이클", prompt 동일하게 `/loop`로 재진입
   - **왜 270초**: 정확히 300초는 캐시 TTL과 같아서 매번 미스 → 비용·지연 손해. 270초면 캐시 유지되면서 ~5분 주기 효과.
   - 사용자가 일어나서 직접 중단하기 전까지 계속

## 안전 가드

- DB 마이그레이션·데이터 삭제 금지
- 외부 API 호출 형식 변경 금지 (스키마 호환성)
- 의존성 추가 회피 (꼭 필요하면 한 사이클 통째로 그 작업에 쓰고 명시)
- 한 카테고리 연속 2회 같은 영역 손대지 않기 (다양성 유지)
- 사용자의 명시적 결정이 필요한 큰 변경은 `AUTO_LOOP_LOG.md`에 "🔔 사용자 결정 필요" 마커로 기록만
