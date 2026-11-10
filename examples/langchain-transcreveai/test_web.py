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
