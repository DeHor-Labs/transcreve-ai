from langchain_core.embeddings import Embeddings
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from app import answer_question, prepare_store


class TestEmbeddings(Embeddings):
    def embed_documents(self, texts):
        return [[1.0, 0.0] for _ in texts]

    def embed_query(self, text):
        return [1.0, 0.0]


def test_dossier_to_langchain_answer(tmp_path):
    dossier = tmp_path / "knowledge.md"
    dossier.write_text("# Dossiê\nO vídeo ensina a plantar milho.", encoding="utf-8")
    store = prepare_store(dossier, TestEmbeddings())
    answer, documents = answer_question(store, "Qual cultura?", FakeListChatModel(responses=["Milho."]))
    assert answer == "Milho."
    assert "plantar milho" in documents[0].page_content
    assert documents[0].metadata["source"] == str(dossier)


def test_empty_dossier_is_rejected(tmp_path):
    import pytest
    dossier = tmp_path / "knowledge.md"
    dossier.write_text(" \n", encoding="utf-8")
    with pytest.raises(ValueError, match="vazio"):
        prepare_store(dossier, TestEmbeddings())


def test_ingest_invokes_transcreveai_without_index(tmp_path, monkeypatch):
    from app import ingest
    calls = []
    def run(command, check):
        calls.append((command, check))
        (tmp_path / "out" / "knowledge.md").write_text("conteúdo", encoding="utf-8")
    monkeypatch.setattr("app.subprocess.run", run)
    assert ingest("video.mp4", tmp_path / "out") == tmp_path / "out" / "knowledge.md"
    assert calls[0][0] == ["transcreveai", "--index-db", str(tmp_path / "out" / "index.db"), "analyze", "video.mp4", "--out", str(tmp_path / "out"), "--ai", "auto", "--language", "pt", "--no-index"]
    assert calls[0][1] is True


def test_ingest_rejects_nonempty_output(tmp_path):
    import pytest
    from app import ingest
    (tmp_path / "existing").write_text("não apagar")
    with pytest.raises(ValueError, match="vazio"):
        ingest("video.mp4", tmp_path)
