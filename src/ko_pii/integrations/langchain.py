"""LangChain 연동 — 검색 결과(Document)의 PII 를 LLM 전달 *전* 에 마스킹.

``Runnable`` 이라 RAG 체인에 그대로 끼운다 (검색 → **마스킹** → 프롬프트 → LLM).
한 번의 ``invoke`` 안의 문서들이 같은 vault 를 공유해 *같은 인물 = 같은 토큰*
일관성을 유지한다.

코어는 의존성을 추가하지 않는다 (설계 원칙 #1). ``langchain-core`` 가 설치돼
있을 때만 동작한다::

    pip install ko-pii[langchain]

사용::

    from ko_pii.integrations.langchain import KoPiiRedactor

    chain = retriever | KoPiiRedactor(mode="STRICT") | prompt | llm

``List[Document]`` / 단일 ``Document`` / ``str`` 입력을 모두 받아 같은 타입으로 반환.
복원이 필요하면 ``vault`` 를 넘긴다 (이후 ``vault.reveal``).
"""
from __future__ import annotations

from typing import Any, Iterable, Optional, Tuple, Union

from ko_pii import Anonymizer, ProcessingMode


def _require() -> Tuple[Any, Any]:
    try:
        from langchain_core.documents import Document
        from langchain_core.runnables import Runnable
        return Runnable, Document
    except ImportError as exc:  # pragma: no cover - 설치 안내 경로
        raise ImportError(
            "KoPiiRedactor 는 langchain-core 가 필요합니다. "
            "설치: pip install ko-pii[langchain]"
        ) from exc


def KoPiiRedactor(
    mode: Union[str, ProcessingMode] = "STRICT",
    strategy: str = "tokenize",
    include: Optional[Iterable[str]] = None,
    exclude: Optional[Iterable[str]] = None,
    vault: Any = None,
) -> Any:
    """검색 문서의 PII 를 마스킹하는 LangChain ``Runnable``.

    Parameters
    ----------
    mode : str | ProcessingMode
        차단 임계 프로파일.
    strategy : str
        가명화 방식. 기본 ``"tokenize"`` (coreference 보존, 가역).
    include / exclude : Iterable[str]
        검출기 라벨 필터.
    vault : ReversibleVault | None
        주면 매핑 유지(복원 가능). 없으면 호출마다 임시 vault.

    Returns
    -------
    ``Runnable`` 인스턴스. langchain-core 미설치 시 ImportError.
    """
    Runnable, Document = _require()
    mode_enum = ProcessingMode[mode] if isinstance(mode, str) else mode
    _inc = list(include) if include else None
    _exc = list(exclude) if exclude else None

    # Runnable 은 런타임에 결정되는 외부 클래스 — 동적 서브클래싱.
    class _KoPiiRedactor(Runnable):  # type: ignore[valid-type, misc]
        def _new_anon(self) -> Anonymizer:
            return Anonymizer(
                mode=mode_enum, strategy=strategy,
                include=_inc, exclude=_exc, vault=vault,
            )

        def _redact(self, obj: Any, anon: Anonymizer) -> Any:
            if isinstance(obj, str):
                return anon.process(obj).text
            if isinstance(obj, Document):
                return Document(
                    page_content=anon.process(obj.page_content).text,
                    metadata=obj.metadata,
                )
            if isinstance(obj, (list, tuple)):
                return type(obj)(self._redact(o, anon) for o in obj)
            return obj

        def invoke(
            self, input: Any, config: Any = None, **kwargs: Any
        ) -> Any:
            # 한 invoke 내 문서들이 vault 공유 → 같은 인물 같은 토큰
            return self._redact(input, self._new_anon())

    return _KoPiiRedactor()
