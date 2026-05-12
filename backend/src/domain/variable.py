"""VariableContext — 통화 세션 1개당 단일 객체. 모든 변수 출처 통합.

vox VOX_AGENT_STRUCTURE §5 정합 구현:
  - dynamic   : 통화 시작 시 SDK/웹훅으로 주입 (예: customer_name, phone)
  - system    : 시스템이 자동으로 채움 (call_id, started_at, caller_number)
  - extracted : 대화 중 extraction 노드가 채움 (date, time, symptom 등)

모든 prompt·condition·api body·sms 본문에서 `{{var_name}}` 치환에 사용.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# {{var}} 또는 {{var.path.to.value}} (점 표기 dotted-path) 모두 지원
_VAR_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*)\s*\}\}")


@dataclass
class VariableContext:
    """3종 출처를 통합한 변수 컨텍스트. 통화 세션당 1개.

    우선순위 (같은 이름이 여러 출처에 있을 때):
      extracted > dynamic > system
    """

    dynamic: dict[str, Any] = field(default_factory=dict)
    system: dict[str, Any] = field(default_factory=dict)
    extracted: dict[str, Any] = field(default_factory=dict)

    # ---------- 변수 접근 ----------

    def get(self, name: str, default: Any = None) -> Any:
        """단순 변수 또는 dotted path. 우선순위에 따라 조회."""
        head, *rest = name.split(".")
        for source in (self.extracted, self.dynamic, self.system):
            if head in source:
                cur = source[head]
                for part in rest:
                    if isinstance(cur, dict) and part in cur:
                        cur = cur[part]
                    else:
                        cur = None
                        break
                if cur is not None or not rest:
                    return cur if cur is not None else default
        return default

    def has(self, name: str) -> bool:
        return self.get(name, _SENTINEL) is not _SENTINEL

    # ---------- 변수 설정 ----------

    def set_extracted(self, name: str, value: Any) -> None:
        """extraction 노드가 슬롯을 채울 때."""
        self.extracted[name] = value

    def merge_dynamic(self, values: dict[str, Any]) -> None:
        """SDK/웹훅 주입."""
        self.dynamic.update(values)

    def set_system(self, name: str, value: Any) -> None:
        """시스템 변수 (call_id 등)."""
        self.system[name] = value

    # ---------- 템플릿 치환 ----------

    def resolve(self, template: str) -> str:
        """`{{var}}` / `{{var.path}}` 토큰을 값으로 치환. 미정의는 빈 문자열로."""
        if not template:
            return template

        def repl(m: re.Match[str]) -> str:
            name = m.group(1)
            v = self.get(name)
            if v is None:
                return ""
            return str(v)

        return _VAR_RE.sub(repl, template)

    def keys(self) -> set[str]:
        """모든 1-depth 키 (mention completion 등에 쓰기 좋음)."""
        return set(self.extracted) | set(self.dynamic) | set(self.system)


_SENTINEL = object()
