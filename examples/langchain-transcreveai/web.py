"""Demonstração autenticada de TranscreveAI e RAG com LangChain."""

import hmac
import json
import os
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Annotated

from app import answer_question, prepare_store
from fastapi import Depends, FastAPI, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import BaseModel, Field

app = FastAPI(title="TranscreveAI + LangChain", docs_url=None, redoc_url=None)
security = HTTPBasic()
MAX_VIDEO_SIZE = 50 * 1024 * 1024
processing = threading.BoundedSemaphore(1)
INTERVIEWS = Path(os.environ.get("INTERVIEW_DIR", "/data/interviews"))


def authenticate(credentials: Annotated[HTTPBasicCredentials, Depends(security)]):
    password = os.environ.get("DEMO_PASSWORD", "")
    if (
        not password
        or not hmac.compare_digest(credentials.username.encode(), b"demo")
        or not hmac.compare_digest(credentials.password.encode(), password.encode())
    ):
        raise HTTPException(
            status_code=401, detail="Acesso negado", headers={"WWW-Authenticate": "Basic"}
        )


class Question(BaseModel):
    dossier: str = Field(min_length=1, max_length=200_000)
    question: str = Field(min_length=1, max_length=2000)


@app.get("/", response_class=HTMLResponse, dependencies=[Depends(authenticate)])
def home():
    return Path(__file__).with_name("index.html").read_text(encoding="utf-8")


@app.post("/ingest", dependencies=[Depends(authenticate)])
def ingest_video(video: UploadFile):
    if not processing.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="Outro vídeo está em processamento.")
    try:
        return _process_video(video)
    finally:
        processing.release()


def _process_video(video: UploadFile):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "video.mp4"
        with source.open("wb") as output:
            size = 0
            while block := video.file.read(1024 * 1024):
                size += len(block)
                if size > MAX_VIDEO_SIZE:
                    raise HTTPException(status_code=413, detail="Vídeo excede 50 MB.")
                output.write(block)
        if not size:
            raise HTTPException(status_code=400, detail="Vídeo vazio.")
        try:
            probe = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(source),
                ],
                check=True,
                timeout=10,
                capture_output=True,
                text=True,
            )
            duration = float(probe.stdout.strip())
            if not 0 < duration <= 120:
                raise HTTPException(status_code=400, detail="O vídeo deve ter até 2 minutos.")
        except (subprocess.SubprocessError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Vídeo inválido.") from exc
        env = os.environ.copy()
        env["VIDEO_KB_ALLOWED_LOCAL_SOURCE_ROOTS"] = str(root)
        try:
            subprocess.run(
                [
                    "transcreveai",
                    "--index-db",
                    str(root / "index.db"),
                    "analyze",
                    str(source),
                    "--out",
                    str(root / "run"),
                    "--ai",
                    "auto",
                    "--language",
                    "pt",
                    "--no-index",
                ],
                env=env,
                check=True,
                timeout=300,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            dossiers = list((root / "run").rglob("knowledge.md"))
            if len(dossiers) != 1:
                raise ValueError("Dossiê não produzido")
            text = dossiers[0].read_text(encoding="utf-8")
            if not text.strip() or len(text) > 200_000:
                raise ValueError("Dossiê vazio ou grande demais")
            return {"dossier": text}
        except (subprocess.SubprocessError, OSError, ValueError) as exc:
            raise HTTPException(
                status_code=502, detail="Não foi possível processar o vídeo."
            ) from exc


@app.post("/ask", dependencies=[Depends(authenticate)])
def ask(request: Question):
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


class Interview(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    transcript: str = Field(min_length=1, max_length=200_000)


class InterviewQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


@app.get("/interviews", dependencies=[Depends(authenticate)])
def list_interviews():
    if not INTERVIEWS.exists():
        return []
    return [
        json.loads(path.read_text(encoding="utf-8"))["title"]
        for path in sorted(INTERVIEWS.glob("*.json"))
    ]


@app.post("/interviews", dependencies=[Depends(authenticate)])
def add_interview(interview: Interview):
    if not interview.title.strip() or not interview.transcript.strip():
        raise HTTPException(status_code=400, detail="Informe título e transcrição.")
    INTERVIEWS.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = INTERVIEWS / f"{uuid.uuid4().hex}.json"
    with path.open("x", encoding="utf-8") as output:
        os.chmod(path, 0o600)
        json.dump(interview.model_dump(), output, ensure_ascii=False)
    return {"title": interview.title}


@app.post("/interviews/coach", dependencies=[Depends(authenticate)])
def coach(request: InterviewQuestion):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Informe uma pergunta.")
    paths = sorted(INTERVIEWS.glob("*.json")) if INTERVIEWS.exists() else []
    if not paths:
        raise HTTPException(status_code=400, detail="Adicione uma entrevista primeiro.")
    try:
        documents = []
        for path in paths:
            item = json.loads(path.read_text(encoding="utf-8"))
            documents.append(
                Document(page_content=item["transcript"], metadata={"source": item["title"]})
            )
        chunks = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150).split_documents(
            documents
        )
        store = InMemoryVectorStore.from_documents(chunks, OpenAIEmbeddings())
        answer, sources = answer_question(
            store, request.question, ChatOpenAI(model="gpt-4o-mini", temperature=0), coach=True
        )
        return {
            "answer": answer,
            "sources": [{"title": d.metadata["source"], "text": d.page_content} for d in sources],
        }
    except Exception as exc:
        raise HTTPException(
            status_code=502, detail="Não foi possível analisar as entrevistas."
        ) from exc
