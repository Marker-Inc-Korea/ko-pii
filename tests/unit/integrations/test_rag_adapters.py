"""RAG 연동 어댑터 — LlamaIndex / LangChain (프레임워크 미설치 시 skip)."""
import re

import pytest


class TestImportSafety:
    """프레임워크 없이도 모듈 import 는 안전, 팩토리 호출만 ImportError."""

    def test_modules_import_without_frameworks(self):
        import ko_pii.integrations.langchain  # noqa: F401
        import ko_pii.integrations.llamaindex  # noqa: F401


class TestLangChainRedactor:
    def setup_method(self):
        pytest.importorskip("langchain_core")

    def test_redacts_documents_with_coreference(self):
        from langchain_core.documents import Document

        from ko_pii.integrations.langchain import KoPiiRedactor

        docs = [
            Document(page_content="김철수 부장 010-1234-5678", metadata={"src": "a"}),
            Document(page_content="김철수 부장 900101-1234567", metadata={"src": "b"}),
        ]
        out = KoPiiRedactor(mode="STRICT").invoke(docs)
        joined = " ".join(d.page_content for d in out)
        assert "김철수" not in joined and "010-1234-5678" not in joined
        # 같은 인물 = 같은 토큰
        toks = re.findall(r"<PERSON_\d+>", joined)
        assert len(toks) == 2 and len(set(toks)) == 1
        # metadata 보존
        assert out[0].metadata == {"src": "a"}

    def test_redacts_plain_string(self):
        from ko_pii.integrations.langchain import KoPiiRedactor

        out = KoPiiRedactor(mode="STRICT").invoke("연락처 010-1234-5678")
        assert "010-1234-5678" not in out

    def test_vault_reveal_restores(self):
        from langchain_core.documents import Document

        from ko_pii.integrations.langchain import KoPiiRedactor
        from ko_pii.vault import ReversibleVault

        v = ReversibleVault()
        out = KoPiiRedactor(mode="STRICT", vault=v).invoke(
            [Document(page_content="박민수 010-9999-8888", metadata={})]
        )
        tok = re.search(r"<PERSON_\d+>", out[0].page_content).group()
        assert v.reveal(tok) == "박민수"


class TestLlamaIndexPostprocessor:
    def setup_method(self):
        pytest.importorskip("llama_index.core")

    def test_masks_node_text(self):
        from llama_index.core.schema import NodeWithScore, TextNode

        from ko_pii.integrations.llamaindex import KoPiiNodePostprocessor

        nodes = [
            NodeWithScore(node=TextNode(text="이영희 과장 02-555-1234"), score=0.9)
        ]
        out = KoPiiNodePostprocessor(mode="STRICT").postprocess_nodes(
            nodes, query_str="q"
        )
        masked = out[0].node.text
        assert "이영희" not in masked and "02-555-1234" not in masked
        assert "<PERSON_1>" in masked and "<PHONE_1>" in masked


def test_llamaindex_masks_llm_metadata_without_mutating_retrieval_nodes():
    schema = pytest.importorskip("llama_index.core.schema")
    from ko_pii.integrations.llamaindex import KoPiiNodePostprocessor
    from ko_pii.vault import ReversibleVault

    node = schema.TextNode(text="demo@example.com", metadata={"contact": "demo@example.com"})
    wrapped = schema.NodeWithScore(node=node, score=0.8)
    out = KoPiiNodePostprocessor().postprocess_nodes([wrapped])
    assert "demo@example.com" not in out[0].node.get_content(metadata_mode=schema.MetadataMode.LLM)
    assert out[0].node.node_id == node.node_id
    assert out[0].score == 0.8
    assert node.text == node.metadata["contact"] == "demo@example.com"
    vault = ReversibleVault()
    later = KoPiiNodePostprocessor(vault=vault).postprocess_nodes([
        wrapped, schema.NodeWithScore(node=schema.TextNode(text="other@example.com")),
    ])
    assert vault.reveal(later[0].node.text) == "demo@example.com"
    assert later[0].node.text != later[1].node.text


def test_langchain_preserves_id_masks_nested_metadata_and_keeps_original():
    documents = pytest.importorskip("langchain_core.documents")
    from ko_pii.integrations.langchain import KoPiiRedactor

    doc = documents.Document(id="source-001", page_content="demo@example.com",
                             metadata={"nested": ["demo@example.com"], "count": 2})
    out = KoPiiRedactor().invoke(doc)
    assert out.id == doc.id
    assert out.metadata == {"nested": ["<EMAIL_1>"], "count": 2}
    assert doc.page_content == doc.metadata["nested"][0] == "demo@example.com"


@pytest.mark.parametrize("value", [{"context": "demo@example.com"}, b"demo@example.com", [object()]])
def test_langchain_rejects_unsupported_inputs(value):
    pytest.importorskip("langchain_core")
    from ko_pii.integrations.langchain import KoPiiRedactor
    with pytest.raises(TypeError, match="accepts"):
        KoPiiRedactor().invoke(value)


def test_metadata_fails_closed_for_unsupported_values_and_sensitive_keys():
    documents = pytest.importorskip("langchain_core.documents")
    from ko_pii.integrations.langchain import KoPiiRedactor
    for metadata in ({"demo@example.com": "x"}, {"value": object()}):
        with pytest.raises(ValueError):
            KoPiiRedactor().invoke(documents.Document(page_content="public", metadata=metadata))


def test_empty_include_has_same_validation_as_core():
    pytest.importorskip("langchain_core")
    from ko_pii.integrations.langchain import KoPiiRedactor
    with pytest.raises(ValueError):
        KoPiiRedactor(include=[])
