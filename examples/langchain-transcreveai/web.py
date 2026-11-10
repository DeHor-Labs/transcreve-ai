"""Interface local para perguntas sobre um dossiê TranscreveAI."""

from pathlib import Path

from app import answer_question, prepare_store
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import BaseModel, Field

app = FastAPI(title="TranscreveAI + LangChain")


class Question(BaseModel):
    dossier: str = Field(min_length=1, max_length=200_000)
    question: str = Field(min_length=1, max_length=2000)


@app.get("/", response_class=HTMLResponse)
def home():
    return Path(__file__).with_name("index.html").read_text(encoding="utf-8")


@app.post("/ask")
def ask(request: Question):
    import tempfile

    if not request.dossier.strip() or not request.question.strip():
        raise HTTPException(status_code=400, detail="Informe dossiê e pergunta.")
    try:
        with tempfile.TemporaryDirectory() as directory:
            dossier = Path(directory) / "knowledge.md"
            dossier.write_text(request.dossier, encoding="utf-8")
            store = prepare_store(dossier, OpenAIEmbeddings())
            answer, documents = answer_question(
                store, request.question, ChatOpenAI(model="gpt-4o-mini", temperature=0)
            )
            return {"answer": answer, "sources": [doc.page_content for doc in documents]}
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail="Não foi possível consultar o provedor."
        ) from exc
