import socket
import sys

from verified_memory.cli import main
from verified_memory.storage import SQLiteVerifiedMemoryStore
from verified_memory.workflows import validate_answer


def test_workflow_builds_prompt_then_validates_without_llm_or_network(tmp_path, capsys, monkeypatch):
    db = tmp_path / "vm.sqlite3"
    document = tmp_path / "sop.txt"
    document.write_text("Users must connect to Wi-Fi during OOBE.\n", encoding="utf-8")

    def fail_network(*args, **kwargs):
        raise AssertionError("network should not be called")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    sys.modules.pop("src.llm_core", None)

    assert main(["ingest", str(document), "--db", str(db), "--extract"]) == 0
    capsys.readouterr()

    result = validate_answer(
        "What does the SOP say about Wi-Fi?",
        "Users must connect to Wi-Fi during OOBE.",
        SQLiteVerifiedMemoryStore(db),
    )

    assert result.severity == "warning"
    assert result.metadata["answer_generated"] is False
    assert "src.llm_core" not in sys.modules
