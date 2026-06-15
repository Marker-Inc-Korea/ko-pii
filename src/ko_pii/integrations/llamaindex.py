"""LlamaIndex 연동 — 검색된 노드의 PII 를 LLM 답변 *전* 에 마스킹.

RAG post-processor 패턴 (검색 → **마스킹** → LLM). 한 쿼리에서 검색된 노드들이
같은 vault 를 공유하므로 *같은 인물 = 같은 토큰* (``<PERSON_1>``) 일관성을 유지한다
→ LLM 이 동일 개체를 계속 같은 것으로 추론 가능.

코어는 의존성을 추가하지 않는다 (설계 원칙 #1). 본 모듈은 ``llama-index-core`` 가
설치돼 있을 때만 동작한다::

    pip install ko-pii[llamaindex]

사용::

    from ko_pii.integrations.llamaindex import KoPiiNodePostprocessor

    qe = index.as_query_engine(
        node_postprocessors=[KoPiiNodePostprocessor(mode="STRICT")]
    )

복원이 필요하면 ``vault`` 를 넘겨 매핑을 유지한다 (답변 생성 후 ``vault.reveal``)::

    from ko_pii.vault import ReversibleVault
    v = ReversibleVault()
    pp = KoPiiNodePostprocessor(mode="STRICT", vault=v)
"""
from __future__ import annotations

from typing import Any, Iterable, Optional, Union

from ko_pii import Anonymizer, ProcessingMode


def _require() -> Any:
    try:
        from llama_index.core.postprocessor.types import BaseNodePostprocessor
        from llama_index.core.schema import NodeWithScore  # noqa: F401
        return BaseNodePostprocessor
    except ImportError as exc:  # pragma: no cover - 설치 안내 경로
        raise ImportError(
            "KoPiiNodePostprocessor 는 llama-index-core 가 필요합니다. "
            "설치: pip install ko-pii[llamaindex]"
        ) from exc


def KoPiiNodePostprocessor(
    mode: Union[str, ProcessingMode] = "STRICT",
    strategy: str = "tokenize",
    include: Optional[Iterable[str]] = None,
    exclude: Optional[Iterable[str]] = None,
    vault: Any = None,
) -> Any:
    """검색된 노드 텍스트의 PII 를 마스킹하는 LlamaIndex node postprocessor.

    Parameters
    ----------
    mode : str | ProcessingMode
        차단 임계 프로파일 ("PARANOID"/"STRICT"/"BALANCED"/"PERMISSIVE"/"AUDIT").
    strategy : str
        가명화 방식. 기본 ``"tokenize"`` (``<PERSON_1>`` — coreference 보존, 가역).
    include / exclude : Iterable[str]
        검출기 라벨 필터.
    vault : ReversibleVault | None
        주면 매핑을 유지(답변 후 복원 가능). 없으면 쿼리마다 임시 vault.

    Returns
    -------
    ``BaseNodePostprocessor`` 인스턴스. llama-index-core 미설치 시 ImportError.
    """
    base = _require()
    mode_enum = ProcessingMode[mode] if isinstance(mode, str) else mode
    _inc = list(include) if include else None
    _exc = list(exclude) if exclude else None

    # base 는 런타임에 결정되는 외부 클래스(BaseNodePostprocessor) — 동적 서브클래싱.
    class _KoPiiNodePostprocessor(base):  # type: ignore[valid-type, misc]
        @classmethod
        def class_name(cls) -> str:
            return "KoPiiNodePostprocessor"

        def _postprocess_nodes(
            self, nodes: Any, query_bundle: Any = None
        ) -> Any:
            # vault 가 주어지면 그것을(영속·복원), 아니면 쿼리당 하나 공유(노드 간 일관성)
            anon = Anonymizer(
                mode=mode_enum, strategy=strategy,
                include=_inc, exclude=_exc, vault=vault,
            )
            for nws in nodes:
                node = getattr(nws, "node", nws)
                text = getattr(node, "text", None)
                if text:
                    node.text = anon.process(text).text
            return nodes

    return _KoPiiNodePostprocessor()
