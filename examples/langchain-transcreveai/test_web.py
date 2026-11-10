import web
from fastapi.testclient import TestClient
from langchain_core.documents import Document


def test_authenticated_ask(monkeypatch):
    monkeypatch.setenv("DEMO_PASSWORD", "senha-teste")
    monkeypatch.setattr(web, "OpenAIEmbeddings", lambda: None)
    monkeypatch.setattr(web, "ChatOpenAI", lambda **kwargs: None)
    monkeypatch.setattr(web, "prepare_store", lambda path, embeddings: path.read_text())
    monkeypatch.setattr(
        web,
        "answer_question",
        lambda store, question, model: ("Milho", [Document(page_content=store)]),
    )
    client = TestClient(web.app)
    assert client.get("/").status_code == 401
    auth = ("demo", "senha-teste")
    assert client.get("/", auth=auth).status_code == 200
    response = client.post(
        "/ask", auth=auth, json={"dossier": "Cultivo de milho", "question": "Qual cultura?"}
    )
    assert response.json() == {"answer": "Milho", "sources": ["Cultivo de milho"]}
    assert (
        client.post("/ask", auth=auth, json={"dossier": " ", "question": "Qual?"}).status_code
        == 400
    )
    assert client.post("/ingest", auth=auth, files={"video": ("v.mp4", b"")}).status_code == 400


def test_video_ingestion_is_isolated_and_returns_dossier(monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace

    monkeypatch.setenv("DEMO_PASSWORD", "senha-teste")

    def run(command, **kwargs):
        if command[0] == "ffprobe":
            return SimpleNamespace(stdout="12.0")
        assert "--no-index" in command
        output = Path(command[command.index("--out") + 1])
        output.mkdir()
        (output / "knowledge.md").write_text("Dossiê do vídeo", encoding="utf-8")
        assert command[command.index("--index-db") + 1].startswith(str(output.parent))
        return SimpleNamespace()

    monkeypatch.setattr(web.subprocess, "run", run)
    client = TestClient(web.app)
    response = client.post(
        "/ingest", auth=("demo", "senha-teste"), files={"video": ("v.mp4", b"video")}
    )
    assert response.status_code == 200
    assert response.json() == {"dossier": "Dossiê do vídeo"}


def test_interview_corpus_and_coaching_are_private(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_PASSWORD", "senha-teste")
    monkeypatch.setattr(web, "INTERVIEWS", tmp_path)
    monkeypatch.setattr(web, "OpenAIEmbeddings", lambda: None)
    monkeypatch.setattr(web, "ChatOpenAI", lambda **kwargs: None)
    monkeypatch.setattr(web.InMemoryVectorStore, "from_documents", lambda docs, embeddings: docs)
    monkeypatch.setattr(
        web, "answer_question", lambda docs, question, model, **kw: ("Sugestão", docs)
    )
    client = TestClient(web.app)
    auth = ("demo", "senha-teste")
    item = {"title": "Entrevista", "transcript": "Construí um fluxo de RAG."}
    assert client.post("/interviews", json=item).status_code == 401
    assert client.post("/interviews", auth=auth, json=item).status_code == 200
    assert client.get("/interviews", auth=auth).json() == ["Entrevista"]
    result = client.post("/interviews/coach", auth=auth, json={"question": "Como melhorar?"})
    assert result.status_code == 200
    assert result.json()["sources"][0]["title"] == "Entrevista"


def test_cross_site_mutation_is_rejected(monkeypatch):
    monkeypatch.setenv("DEMO_PASSWORD", "senha-teste")
    monkeypatch.setenv("DEMO_ORIGIN", "https://langchain.dehor.com.br")
    client = TestClient(web.app)
    response = client.post(
        "/interviews",
        auth=("demo", "senha-teste"),
        headers={"origin": "https://attacker.example", "sec-fetch-site": "cross-site"},
        json={"title": "teste", "transcript": "teste"},
    )
    assert response.status_code == 403
