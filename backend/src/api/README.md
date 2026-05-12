# api — HTTP·WebSocket 외부 노출 (가장 바깥 층)

요청을 받아 application service로 위임하고, 응답·이벤트를 직렬화한다.

```
api/
├── routers/
│   ├── tenants.py            /api/tenants (Tenant CRUD)
│   ├── callbot_agents.py     /api/callbot-agents (콜봇 + 멤버 관리)
│   ├── bots.py               /api/bots (Bot + branches + runtime preview)
│   ├── skills.py             /api/skills
│   ├── knowledge.py          /api/knowledge
│   ├── tools.py              /api/tools
│   ├── mcp_servers.py        /api/mcp_servers + discover + import_tools
│   ├── calls.py              /api/calls/start (sessions·invocations)
│   └── transcripts.py        /api/transcripts/{sid}
└── ws/
    └── voice.py              /ws/calls/{sid} (PCM in / TTS out + JSON 이벤트)
```

## 룰

- 라우터는 **service 메서드 호출**만 함. SQL/ORM 직접 호출 금지
- `DomainError` → `HTTPException(400/404/409)` 변환 책임
- Pydantic 요청·응답 모델은 라우터 파일 또는 별도 dto 위치
- WebSocket 핸들러는 voice_session 인스턴스 1개 생성 후 메시지 라우팅만

## 새 라우터 추가

기존 라우터 7개 같은 패턴:

```python
@router.post("/api/<name>")
def create_<name>(payload: <Name>Create, db: Session = Depends(get_db)):
    service = <Name>Service(repository=<Name>Repository(db))
    try:
        entity = service.create(payload.dict())
    except DomainError as e:
        raise HTTPException(400, str(e))
    return <Name>Read.from_orm(entity)
```

## 이벤트 (WebSocket)

`voice.py`가 클라이언트로 보내는 JSON 타입:
- `state` (idle/listening/thinking/speaking)
- `transcript` (role: user/assistant, text, is_final)
- `tool_call` / `tool_result` (페어로)
- `extracted` (값 + source)
- `handover` / `transfer_to_agent`
- `skill` (스킬 전환)
- `error`
- `end` (reason)
