"""
Testes de integracao da API web do TranscreveAI.

Usa FastAPI TestClient (httpx sync) para testar os endpoints sem subir
um servidor real. O pipeline pesado (VideoKnowledgePipeline.run) e
completamente mockado - nenhuma rede ou arquivo de video e acessado.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch


def _unique_url() -> str:
    """Gera URL unica para evitar conflito de dedupe entre testes."""
    return f"https://example.com/video-{uuid.uuid4().hex}"


# ---------------------------------------------------------------------------
# Helper: cria AnalysisResult fake
# ---------------------------------------------------------------------------


def _make_fake_result(workdir: str) -> object:
    from video_kb.models import AnalysisResult, KnowledgeSynthesis, SourceMetadata

    meta = SourceMetadata(
        source="https://example.com/fake-video",
        title="Video de Teste",
        duration=120.0,
    )
    synthesis = KnowledgeSynthesis(
        summary="Resumo do video de teste.",
        chapters=[],
        entities=["Entidade1"],
        action_items=["Acao 1"],
    )
    return AnalysisResult(
        run_id="run-test-001",
        created_at="2026-06-02T12:00:00Z",
        source="https://example.com/fake-video",
        workdir=workdir,
        media_path=str(Path(workdir) / "video.mp4"),
        audio_path=str(Path(workdir) / "audio.wav"),
        metadata=meta,
        transcript_text="Transcricao de teste.",
        synthesis=synthesis,
        warnings=[],
    )


# ---------------------------------------------------------------------------
# Helper: cria app de teste com out_dir temporario
# ---------------------------------------------------------------------------


def _make_test_app(tmp_dir: str):  # type: ignore[no-untyped-def]
    from video_kb.web.app import create_app

    # Usa arquivo sqlite isolado dentro do tmp_dir para nao contaminar o index real
    index_db = str(Path(tmp_dir) / "test_index.db")
    return create_app(out_dir=Path(tmp_dir), index_db=index_db)


# ---------------------------------------------------------------------------
# Base: garante que o TestClient usa context manager (lifespan ativo)
# ---------------------------------------------------------------------------


class _WebTestCase(unittest.TestCase):
    """Base que cria um TestClient com lifespan ativo para cada teste."""

    def setUp(self) -> None:
        from fastapi.testclient import TestClient

        self._tmp_dir = tempfile.mkdtemp()
        self._app = _make_test_app(self._tmp_dir)
        self._tc = TestClient(self._app)
        self._tc.__enter__()
        self.client = self._tc

    def tearDown(self) -> None:
        try:
            self._tc.__exit__(None, None, None)
        except Exception:  # noqa: BLE001
            pass
        shutil.rmtree(self._tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# 1. /api/health
# ---------------------------------------------------------------------------


class TestHealthEndpoint(_WebTestCase):
    def test_health_retorna_200(self) -> None:
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)

    def test_health_status_ok(self) -> None:
        resp = self.client.get("/api/health")
        data = resp.json()
        self.assertEqual(data["status"], "ok")

    def test_health_tem_version(self) -> None:
        resp = self.client.get("/api/health")
        data = resp.json()
        self.assertIn("version", data)
        self.assertIsInstance(data["version"], str)

    def test_health_tem_queue_size(self) -> None:
        resp = self.client.get("/api/health")
        data = resp.json()
        self.assertIn("queue_size", data)
        self.assertIsInstance(data["queue_size"], int)

    def test_health_active_job_none_sem_jobs(self) -> None:
        resp = self.client.get("/api/health")
        data = resp.json()
        self.assertIsNone(data["active_job"])


# ---------------------------------------------------------------------------
# 2. POST /api/jobs
# ---------------------------------------------------------------------------


class TestSubmitJob(_WebTestCase):
    def test_submit_url_retorna_202(self) -> None:
        resp = self.client.post("/api/jobs", json={"source": _unique_url()})
        self.assertEqual(resp.status_code, 202)

    def test_submit_url_retorna_job_id(self) -> None:
        resp = self.client.post("/api/jobs", json={"source": _unique_url()})
        data = resp.json()
        self.assertIn("job_id", data)
        self.assertIsInstance(data["job_id"], str)
        self.assertTrue(len(data["job_id"]) > 0)

    def test_submit_url_status_queued(self) -> None:
        resp = self.client.post("/api/jobs", json={"source": _unique_url()})
        data = resp.json()
        self.assertEqual(data["status"], "queued")

    def test_submit_url_tem_queued_at(self) -> None:
        resp = self.client.post("/api/jobs", json={"source": _unique_url()})
        data = resp.json()
        self.assertIn("queued_at", data)

    def test_submit_sem_source_retorna_422(self) -> None:
        resp = self.client.post("/api/jobs", json={})
        self.assertEqual(resp.status_code, 422)

    def test_submit_sem_source_mensagem_erro(self) -> None:
        resp = self.client.post("/api/jobs", json={})
        data = resp.json()
        self.assertIn("message", data)

    def test_submit_body_invalido_retorna_422(self) -> None:
        resp = self.client.post(
            "/api/jobs",
            content=b"nao e json",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(resp.status_code, 422)

    def test_submit_com_provider_e_ai_mode(self) -> None:
        resp = self.client.post(
            "/api/jobs",
            json={"source": _unique_url(), "provider": "gemini", "ai_mode": "full"},
        )
        self.assertEqual(resp.status_code, 202)
        data = resp.json()
        self.assertIn("job_id", data)

    def test_submit_rejeita_url_local_ou_privada(self) -> None:
        blocked_sources = [
            "http://localhost/video.mp4",
            "http://127.0.0.1/video.mp4",
            "http://[::1]/video.mp4",
            "http://10.0.0.5/video.mp4",
            "http://172.16.0.5/video.mp4",
            "http://192.168.1.5/video.mp4",
            "http://169.254.169.254/latest/meta-data/",
        ]
        for source in blocked_sources:
            with self.subTest(source=source):
                resp = self.client.post("/api/jobs", json={"source": source})
                self.assertEqual(resp.status_code, 422)
                data = resp.json()
                self.assertEqual(data["error"], "validation")
                self.assertIn("nao permitida", data["message"])

    def test_submit_json_rejeita_caminho_local(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".mp4", dir=self._tmp_dir, delete=False) as handle:
            handle.write(b"dummy")
            local_path = handle.name

        resp = self.client.post("/api/jobs", json={"source": local_path})
        self.assertEqual(resp.status_code, 422)
        body = json.dumps(resp.json())
        self.assertIn("http(s)", body)
        self.assertNotIn(local_path, body)

    def test_submit_upload_multipart_retorna_job_id(self) -> None:
        video_bytes = b"\x00\x00\x00\x18ftypmp42fake-video"

        resp = self.client.post(
            "/api/jobs",
            files={"file": ("clip.mp4", video_bytes, "video/mp4")},
            data={"ai_mode": "off", "provider": "local"},
        )

        self.assertEqual(resp.status_code, 202)
        data = resp.json()
        self.assertIn("job_id", data)
        self.assertEqual(data["status"], "queued")


# ---------------------------------------------------------------------------
# 3. GET /api/jobs
# ---------------------------------------------------------------------------


class TestListJobs(_WebTestCase):
    def test_list_vazio_retorna_200(self) -> None:
        resp = self.client.get("/api/jobs")
        self.assertEqual(resp.status_code, 200)

    def test_list_vazio_retorna_lista_vazia(self) -> None:
        resp = self.client.get("/api/jobs")
        data = resp.json()
        self.assertIn("jobs", data)
        self.assertIsInstance(data["jobs"], list)
        self.assertEqual(data["total"], 0)

    def test_list_apos_submit_tem_um_job(self) -> None:
        self.client.post("/api/jobs", json={"source": _unique_url()})
        resp = self.client.get("/api/jobs")
        data = resp.json()
        self.assertGreaterEqual(len(data["jobs"]), 1)

    def test_list_job_tem_campos_esperados(self) -> None:
        self.client.post("/api/jobs", json={"source": _unique_url()})
        resp = self.client.get("/api/jobs")
        jobs = resp.json()["jobs"]
        self.assertGreater(len(jobs), 0)
        job = jobs[0]
        for campo in ("job_id", "status", "source", "created_at"):
            self.assertIn(campo, job)


# ---------------------------------------------------------------------------
# 4. GET /api/jobs/{id}
# ---------------------------------------------------------------------------


class TestGetJob(_WebTestCase):
    def test_get_job_inexistente_retorna_404(self) -> None:
        resp = self.client.get("/api/jobs/nao-existe-xyzxyz")
        self.assertEqual(resp.status_code, 404)

    def test_get_job_inexistente_mensagem_erro(self) -> None:
        resp = self.client.get("/api/jobs/nao-existe-xyzxyz")
        data = resp.json()
        self.assertIn("detail", data)

    def test_get_job_apos_submit_retorna_200(self) -> None:
        post = self.client.post("/api/jobs", json={"source": _unique_url()})
        job_id = post.json()["job_id"]
        resp = self.client.get(f"/api/jobs/{job_id}")
        self.assertEqual(resp.status_code, 200)

    def test_get_job_campos_detail(self) -> None:
        post = self.client.post("/api/jobs", json={"source": _unique_url()})
        job_id = post.json()["job_id"]
        resp = self.client.get(f"/api/jobs/{job_id}")
        data = resp.json()
        for campo in ("job_id", "status", "source", "created_at", "progress_history"):
            self.assertIn(campo, data)

    def test_get_job_status_queued_ou_running(self) -> None:
        post = self.client.post("/api/jobs", json={"source": _unique_url()})
        job_id = post.json()["job_id"]
        resp = self.client.get(f"/api/jobs/{job_id}")
        data = resp.json()
        self.assertIn(data["status"], ("queued", "running", "completed", "failed"))


# ---------------------------------------------------------------------------
# 5. GET /api/jobs/{id}/dossier (lendo arquivos temporarios)
# ---------------------------------------------------------------------------


class TestGetDossier(_WebTestCase):
    def test_dossier_job_inexistente_retorna_404(self) -> None:
        resp = self.client.get("/api/jobs/nao-existe-abc/dossier")
        self.assertEqual(resp.status_code, 404)

    def test_dossier_job_nao_concluido_retorna_409(self) -> None:
        post = self.client.post("/api/jobs", json={"source": _unique_url()})
        job_id = post.json()["job_id"]
        resp = self.client.get(f"/api/jobs/{job_id}/dossier")
        self.assertEqual(resp.status_code, 409)

    def test_dossier_job_concluido_le_arquivos(self) -> None:
        """Simula job concluido e verifica que o dossier retorna markdown e analysis."""
        from video_kb.web.jobs import ActiveJob, JobStore, _iso_now

        # Cria diretorio de saida simulado
        output_dir = Path(self._tmp_dir) / "run-fake-001"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "knowledge.md").write_text("# Resumo\nConteudo do video.", encoding="utf-8")
        (output_dir / "analysis.json").write_text(
            json.dumps({"run_id": "run-fake-001", "source": "https://example.com/vdoss"}),
            encoding="utf-8",
        )

        # Injeta job completed diretamente no store ativo
        store: JobStore = self._app.state.job_store
        job = ActiveJob(
            job_id="run-fake-001",
            source="https://example.com/vdoss",
            status="completed",
            created_at=_iso_now(),
            provider="openai",
            ai_mode="auto",
            output_dir=str(output_dir),
        )
        store._jobs["run-fake-001"] = job

        resp = self.client.get("/api/jobs/run-fake-001/dossier")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("markdown", data)
        self.assertIn("analysis", data)
        self.assertIn("Resumo", data["markdown"])
        self.assertEqual(data["analysis"]["run_id"], "run-fake-001")

    def test_dossier_expoe_frames_count_e_poda_colecoes_pesadas(self) -> None:
        """O dossier deve derivar frames_count e remover frames/transcript_segments."""
        from video_kb.web.jobs import ActiveJob, JobStore, _iso_now

        output_dir = Path(self._tmp_dir) / "run-fake-002"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "knowledge.md").write_text("# Resumo", encoding="utf-8")
        (output_dir / "analysis.json").write_text(
            json.dumps(
                {
                    "run_id": "run-fake-002",
                    "source": "https://example.com/vframes",
                    "frames": [{"timestamp": 1.0}, {"timestamp": 2.0}, {"timestamp": 3.0}],
                    "transcript_segments": [{"start": 0.0, "end": 1.0, "text": "ola"}],
                    "transcript_text": "ola mundo",
                }
            ),
            encoding="utf-8",
        )

        store: JobStore = self._app.state.job_store
        store._jobs["run-fake-002"] = ActiveJob(
            job_id="run-fake-002",
            source="https://example.com/vframes",
            status="completed",
            created_at=_iso_now(),
            provider="openai",
            ai_mode="auto",
            output_dir=str(output_dir),
        )

        resp = self.client.get("/api/jobs/run-fake-002/dossier")
        self.assertEqual(resp.status_code, 200)
        analysis = resp.json()["analysis"]
        self.assertEqual(analysis["frames_count"], 3)
        self.assertNotIn("frames", analysis)
        self.assertNotIn("transcript_segments", analysis)
        self.assertEqual(analysis["transcript_text"], "ola mundo")


# ---------------------------------------------------------------------------
# 6. POST /api/jobs com pipeline mockado (sem IO real)
# ---------------------------------------------------------------------------


class TestSubmitJobComPipelineMockado(unittest.TestCase):
    """Testa o ciclo completo submit -> worker -> completed mockando o pipeline."""

    def setUp(self) -> None:
        self._tmp_dir = tempfile.mkdtemp()
        self._output_dir = Path(self._tmp_dir) / "run-test-001"
        self._output_dir.mkdir(parents=True, exist_ok=True)
        (self._output_dir / "knowledge.md").write_text(
            "# Sinopse\nVideo mockado.", encoding="utf-8"
        )
        (self._output_dir / "analysis.json").write_text(
            json.dumps({"run_id": "run-test-001", "source": "https://example.com/mock"}),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def test_pipeline_mockado_job_fica_completed(self) -> None:
        """Com pipeline mockado o worker deve marcar o job como completed."""
        from fastapi.testclient import TestClient

        fake_result = _make_fake_result(str(self._output_dir))

        with patch("video_kb.pipeline.VideoKnowledgePipeline.run", return_value=fake_result):
            app = _make_test_app(self._tmp_dir)
            with TestClient(app) as client:
                post = client.post(
                    "/api/jobs",
                    json={"source": "https://example.com/mock"},
                )
                self.assertEqual(post.status_code, 202)
                job_id = post.json()["job_id"]

                deadline = time.monotonic() + 3.0
                status = "queued"
                while time.monotonic() < deadline and status in ("queued", "running"):
                    time.sleep(0.05)
                    resp = client.get(f"/api/jobs/{job_id}")
                    status = resp.json()["status"]

                self.assertEqual(
                    status, "completed", f"Status esperado 'completed', obtido '{status}'"
                )

    def test_pipeline_mockado_dossier_disponivel(self) -> None:
        """Apos job completed, /dossier deve retornar 200."""
        from fastapi.testclient import TestClient

        fake_result = _make_fake_result(str(self._output_dir))

        with patch("video_kb.pipeline.VideoKnowledgePipeline.run", return_value=fake_result):
            app = _make_test_app(self._tmp_dir)
            with TestClient(app) as client:
                post = client.post(
                    "/api/jobs",
                    json={"source": "https://example.com/mock"},
                )
                job_id = post.json()["job_id"]

                deadline = time.monotonic() + 3.0
                status = "queued"
                while time.monotonic() < deadline and status in ("queued", "running"):
                    time.sleep(0.05)
                    status = client.get(f"/api/jobs/{job_id}").json()["status"]

                if status == "completed":
                    resp = client.get(f"/api/jobs/{job_id}/dossier")
                    self.assertEqual(resp.status_code, 200)
                    data = resp.json()
                    self.assertIn("markdown", data)


# ---------------------------------------------------------------------------
# 7. SSE endpoint existe e responde content-type correto
# ---------------------------------------------------------------------------


class TestSSEEndpoint(_WebTestCase):
    def test_sse_job_inexistente_retorna_404(self) -> None:
        resp = self.client.get("/api/jobs/nao-existe/events")
        self.assertEqual(resp.status_code, 404)

    def test_sse_job_existente_content_type_sse(self) -> None:
        """Verifica que o endpoint SSE existe e declara text/event-stream."""
        post = self.client.post("/api/jobs", json={"source": _unique_url()})
        job_id = post.json()["job_id"]

        with self.client.stream("GET", f"/api/jobs/{job_id}/events") as resp:
            ct = resp.headers.get("content-type", "")
            self.assertIn("text/event-stream", ct)


# ---------------------------------------------------------------------------
# 9. POST /api/sources/probe
# ---------------------------------------------------------------------------


class TestSourceProbeEndpoint(_WebTestCase):
    def test_source_probe_youtube(self) -> None:
        resp = self.client.post("/api/sources/probe", json={"source": "https://youtu.be/abc123"})
        self.assertEqual(resp.status_code, 200)

        data = resp.json()
        for campo in (
            "source",
            "kind",
            "adapter",
            "is_url",
            "canonical",
            "requires_cookies",
            "notes",
        ):
            self.assertIn(campo, data)
        self.assertEqual(data["kind"], "youtube")
        self.assertEqual(data["adapter"], "youtube")
        self.assertTrue(data["is_url"])

    def test_source_probe_rejeita_local_file_sem_vazar_path(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".mp4", dir=self._tmp_dir, delete=False) as handle:
            handle.write(b"dummy")
            local_path = handle.name

        for source in (local_path, f"file://{local_path}"):
            with self.subTest(source=source):
                resp = self.client.post("/api/sources/probe", json={"source": source})
                self.assertEqual(resp.status_code, 422)
                body = json.dumps(resp.json())
                self.assertIn("http(s)", body)
                self.assertNotIn(local_path, body)
                self.assertNotIn(str(Path(local_path).parent), body)

    def test_source_probe_rejeita_url_privada(self) -> None:
        resp = self.client.post(
            "/api/sources/probe",
            json={"source": "http://169.254.169.254/latest/meta-data/"},
        )
        self.assertEqual(resp.status_code, 422)
        data = resp.json()
        self.assertEqual(data["error"], "validation")
        self.assertIn("nao permitida", data["message"])

    def test_source_probe_sem_source_retorna_422(self) -> None:
        resp = self.client.post("/api/sources/probe", json={})
        self.assertEqual(resp.status_code, 422)
        data = resp.json()
        self.assertIn("error", data)
        self.assertEqual(data["error"], "validation")

    def test_source_probe_source_vazio_retorna_422(self) -> None:
        resp = self.client.post("/api/sources/probe", json={"source": "   "})
        self.assertEqual(resp.status_code, 422)
        data = resp.json()
        self.assertIn("message", data)
        self.assertIn("obrigatorio", data["message"].lower())


# ---------------------------------------------------------------------------
# 10. Smoke de integracao: StaticFiles serve index.html se dist existir
# ---------------------------------------------------------------------------


class TestStaticFilesSPA(unittest.TestCase):
    def test_frontend_dist_serve_index_html(self) -> None:
        """Se frontend/dist existir, FastAPI deve servir index.html na raiz."""
        dist_path = Path(__file__).resolve().parent.parent / "frontend" / "dist"
        if not dist_path.is_dir():
            self.skipTest("frontend/dist nao existe - rode pnpm build no frontend primeiro")

        from fastapi.testclient import TestClient

        from video_kb.web.app import create_app

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(out_dir=Path(tmp), index_db=":memory:")
            with TestClient(app) as client:
                resp = client.get("/")
                self.assertEqual(resp.status_code, 200)
                ct = resp.headers.get("content-type", "")
                self.assertIn("text/html", ct)


if __name__ == "__main__":
    unittest.main()
