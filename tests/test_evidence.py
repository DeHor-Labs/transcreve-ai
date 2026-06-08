from __future__ import annotations

import json

from video_kb.evidence import (
    build_evidence_items,
    detect_tool_names,
    evidence_items_to_dicts,
    get_evidence_items,
    render_evidence_item,
    tool_names_from_evidence,
)
from video_kb.models import AnalysisResult, FrameObservation, KnowledgeSynthesis, SourceMetadata


def _result() -> AnalysisResult:
    return AnalysisResult(
        run_id="run-evidence",
        created_at="2026-06-07T00:00:00Z",
        source="https://example.com/reel",
        workdir="/tmp/run",
        media_path="source.mp4",
        audio_path="",
        metadata=SourceMetadata(
            source="https://example.com/reel",
            title="QA stack",
            description="Post sobre ferramentas de testes e CI/CD.",
        ),
        frames=[
            FrameObservation(
                timestamp=8,
                image_path="frames/frame_0005_00008s00.jpg",
                ocr_text="CI/CD e Versionamento - Docker - Jenkins - GitHub Actions - GitLab",
                visual_note="Tela mostra uma lista de ferramentas de CI/CD com Docker.",
            ),
            FrameObservation(
                timestamp=2,
                image_path="frames/frame_0002_00002s00.jpg",
                ocr_text="Testes de API - Swagger - Postman - PactumJS - Insomnia - Newman",
                visual_note="Slide de ferramentas de teste de API.",
            ),
        ],
        synthesis=KnowledgeSynthesis(
            summary="Reel lista ferramentas de QA, testes de API e CI/CD.",
            tools_or_products=["Docker", "OpenWA Cloud", "Ferramentas de gestao"],
        ),
    )


def test_detect_tool_names_cobre_stack_qa_ci_do_reel() -> None:
    names = detect_tool_names(
        "Swagger Postman PactumJS Insomnia Newman Playwright Cypress Selenium "
        "Appium Robot K6 Grafana JMeter Kibana Docker Jenkins GitHub Actions "
        "GitLab Azure DevOps Jira Trello Qase Notion"
    )

    for expected in (
        "Swagger",
        "Postman",
        "PactumJS",
        "Insomnia",
        "Newman",
        "K6",
        "JMeter",
        "Docker",
        "Jenkins",
        "GitHub Actions",
        "GitLab",
        "Azure DevOps",
        "Qase",
    ):
        assert expected in names


def test_detect_tool_names_nao_duplica_alias_composto_com_pai() -> None:
    assert detect_tool_names("GitHub Actions") == ["GitHub Actions"]
    assert detect_tool_names("Claude Code") == ["Claude Code"]
    assert detect_tool_names("cloud code") == ["Claude Code"]
    assert detect_tool_names("GitHub Actions e GitHub repos") == [
        "GitHub Actions",
        "GitHub",
    ]


def test_build_evidence_items_preserva_origem_timestamp_e_confianca() -> None:
    items = build_evidence_items(_result())
    by_name = {item.value: item for item in items}

    docker = by_name["Docker"]
    assert docker.confidence == "high"
    assert any(support.signal == "ocr" and support.timestamp == 8 for support in docker.supports)
    assert any(support.signal == "synthesis" for support in docker.supports)

    inferred = by_name["OpenWA Cloud"]
    assert inferred.confidence == "low"
    assert inferred.supports[0].signal == "synthesis"
    assert "Ferramentas de gestao" not in by_name


def test_tool_names_from_evidence_e_render_legivel() -> None:
    items = build_evidence_items(_result())
    names = tool_names_from_evidence(items)

    assert "Swagger" in names
    assert "Docker" in names

    docker = next((item for item in items if item.value == "Docker"), None)
    assert docker is not None, "Expected Docker in build_evidence_items output"
    rendered = render_evidence_item(docker)

    assert "Docker: confianca alta" in rendered
    assert "OCR em 00:08" in rendered
    assert "frames/frame_0005_00008s00.jpg" in rendered


def test_get_evidence_items_normaliza_payload_vindo_de_json() -> None:
    result = _result()
    payload = json.loads(json.dumps(evidence_items_to_dicts(build_evidence_items(result))))
    result.evidence_items = payload  # type: ignore[assignment]

    items = get_evidence_items(result)
    docker = next((item for item in items if item.value == "Docker"), None)
    assert docker is not None, "Expected Docker in normalized evidence items"
    rendered = render_evidence_item(docker)

    assert docker.confidence == "high"
    assert "Docker" in tool_names_from_evidence(items)
    assert "OCR em 00:08" in rendered
