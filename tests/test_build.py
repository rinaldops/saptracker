"""Testes do empacotador (Fase 11).

Validam a fiação do ``scripts/build.py`` e a presença da spec, sem invocar o
PyInstaller de fato (lento e dependente do ambiente). A execução real do
empacotamento é coberta pelo job de CI/uso manual.
"""

from __future__ import annotations

from scripts import build


def test_arch_label() -> None:
    assert build.current_arch() in {"x86", "x64"}


def test_spec_existe_e_referencia_main() -> None:
    assert build.SPEC_FILE.exists()
    assert build.SPEC_FILE.name == "sap_scripting_tool.spec"
    conteudo = build.SPEC_FILE.read_text(encoding="utf-8")
    assert "src" in conteudo and "main.py" in conteudo
    assert "SAPScriptingTool" in conteudo


def test_build_aborta_sem_spec(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    # Aponta a spec para um caminho inexistente: build deve falhar sem chamar
    # o PyInstaller.
    monkeypatch.setattr(build, "SPEC_FILE", tmp_path / "inexistente.spec")
    chamado: list[bool] = []
    monkeypatch.setattr(
        build.subprocess, "run", lambda *a, **k: chamado.append(True)
    )
    assert build.build() == 1
    assert chamado == []
