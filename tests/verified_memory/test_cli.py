import json
import socket
import sys

from verified_memory.cli import main
from verified_memory.storage import SQLiteVerifiedMemoryStore


def _run_cli(argv, capsys):
    code = main(argv)
    captured = capsys.readouterr()
    payload = json.loads(captured.out) if captured.out.strip() else None
    return code, payload, captured


def test_ingest_command_stores_chunks_and_prints_json(tmp_path, capsys):
    db = tmp_path / "vm.sqlite3"
    document = tmp_path / "sop.md"
    document.write_text("# SOP\nUsers must connect to Wi-Fi.\n", encoding="utf-8")

    code, payload, _ = _run_cli(["ingest", str(document), "--db", str(db)], capsys)

    assert code == 0
    assert payload["command"] == "ingest"
    assert payload["document_name"] == "sop.md"
    assert payload["chunks_created"] == 1
    assert len(SQLiteVerifiedMemoryStore(db).list_document_chunks()) == 1


def test_ingest_rejects_unsupported_file_extensions(tmp_path, capsys):
    db = tmp_path / "vm.sqlite3"
    document = tmp_path / "sop.pdf"
    document.write_text("not supported", encoding="utf-8")

    code = main(["ingest", str(document), "--db", str(db)])
    captured = capsys.readouterr()

    assert code != 0
    assert "Unsupported document extension" in captured.err
    assert captured.out == ""


def test_ingest_extract_stores_claims(tmp_path, capsys):
    db = tmp_path / "vm.sqlite3"
    document = tmp_path / "sop.txt"
    document.write_text("Users must connect to Wi-Fi.\n", encoding="utf-8")

    code, payload, _ = _run_cli(["ingest", str(document), "--db", str(db), "--extract"], capsys)

    assert code == 0
    assert payload["command"] == "ingest"
    assert payload["extraction"]["claims_created"] == 1
    assert len(SQLiteVerifiedMemoryStore(db).list_memory_claims()) == 1


def test_extract_command_creates_claims_from_existing_chunks(tmp_path, capsys):
    db = tmp_path / "vm.sqlite3"
    document = tmp_path / "sop.txt"
    document.write_text("Admins should verify Teams permissions.\n", encoding="utf-8")
    main(["ingest", str(document), "--db", str(db)])
    capsys.readouterr()

    code, payload, _ = _run_cli(["extract", "--db", str(db)], capsys)

    assert code == 0
    assert payload["command"] == "extract"
    assert payload["claims_created"] == 1
    assert payload["chunks_processed"] == 1


def test_context_command_returns_context_and_does_not_generate_answer(tmp_path, capsys):
    db = tmp_path / "vm.sqlite3"
    document = tmp_path / "sop.txt"
    document.write_text("Users must connect to Wi-Fi during OOBE.\n", encoding="utf-8")
    main(["ingest", str(document), "--db", str(db), "--extract"])
    capsys.readouterr()

    code, payload, _ = _run_cli(["context", "What does the SOP say about Wi-Fi?", "--db", str(db)], capsys)

    assert code == 0
    assert payload["command"] == "context"
    assert payload["question"] == "What does the SOP say about Wi-Fi?"
    assert payload["retrieved_chunks"]
    assert payload["retrieved_claims"]
    assert payload["metadata"]["answer_generated"] is False
    assert "answer" not in payload


def test_stats_command_returns_correct_counts(tmp_path, capsys):
    db = tmp_path / "vm.sqlite3"
    document = tmp_path / "sop.txt"
    document.write_text("Users must connect to Wi-Fi.\n", encoding="utf-8")
    main(["ingest", str(document), "--db", str(db), "--extract"])
    capsys.readouterr()

    code, payload, _ = _run_cli(["stats", "--db", str(db)], capsys)

    assert code == 0
    assert payload == {
        "command": "stats",
        "documents": 1,
        "chunks": 1,
        "claims": 1,
        "conflicts": 0,
        "verification_runs": 0,
    }


def test_missing_db_returns_nonzero(tmp_path, capsys):
    document = tmp_path / "sop.txt"
    document.write_text("content", encoding="utf-8")

    code = main(["ingest", str(document)])
    captured = capsys.readouterr()

    assert code != 0
    assert "--db" in captured.err


def test_invalid_file_path_returns_nonzero(tmp_path, capsys):
    code = main(["ingest", str(tmp_path / "missing.txt"), "--db", str(tmp_path / "vm.sqlite3")])
    captured = capsys.readouterr()

    assert code != 0
    assert "Document path does not exist" in captured.err


def test_cli_does_not_call_network_or_llm(tmp_path, capsys, monkeypatch):
    db = tmp_path / "vm.sqlite3"
    document = tmp_path / "sop.txt"
    document.write_text("Users must connect to Wi-Fi.\n", encoding="utf-8")

    def fail_network(*args, **kwargs):
        raise AssertionError("network should not be called")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    sys.modules.pop("src.llm_core", None)

    code, payload, _ = _run_cli(["ingest", str(document), "--db", str(db), "--extract"], capsys)
    code2, context_payload, _ = _run_cli(["context", "Wi-Fi", "--db", str(db)], capsys)

    assert code == 0
    assert code2 == 0
    assert payload["extraction"]["claims_created"] == 1
    assert context_payload["metadata"]["answer_generated"] is False
    assert "src.llm_core" not in sys.modules


def test_prompt_command_prints_valid_json(tmp_path, capsys):
    db = tmp_path / "vm.sqlite3"
    document = tmp_path / "sop.txt"
    document.write_text("Users must connect to Wi-Fi during OOBE.\n", encoding="utf-8")
    main(["ingest", str(document), "--db", str(db), "--extract"])
    capsys.readouterr()

    code, payload, _ = _run_cli(["prompt", "What does the SOP say about Wi-Fi?", "--db", str(db)], capsys)

    assert code == 0
    assert payload["command"] == "prompt"
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][1]["role"] == "user"
    assert "answer" not in payload


def test_prompt_command_format_messages_prints_messages_only(tmp_path, capsys):
    db = tmp_path / "vm.sqlite3"
    document = tmp_path / "sop.txt"
    document.write_text("Users must connect to Wi-Fi during OOBE.\n", encoding="utf-8")
    main(["ingest", str(document), "--db", str(db), "--extract"])
    capsys.readouterr()

    code, payload, _ = _run_cli([
        "prompt",
        "What does the SOP say about Wi-Fi?",
        "--db",
        str(db),
        "--format",
        "messages",
    ], capsys)

    assert code == 0
    assert payload == {
        "command": "prompt",
        "messages": payload["messages"],
        "warnings": payload["warnings"],
    }
    assert len(payload["messages"]) == 2
    assert "evidence_blocks" not in payload


def test_prompt_command_does_not_call_network_or_llm(tmp_path, capsys, monkeypatch):
    db = tmp_path / "vm.sqlite3"
    document = tmp_path / "sop.txt"
    document.write_text("Users must connect to Wi-Fi.\n", encoding="utf-8")

    def fail_network(*args, **kwargs):
        raise AssertionError("network should not be called")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    sys.modules.pop("src.llm_core", None)

    main(["ingest", str(document), "--db", str(db), "--extract"])
    capsys.readouterr()
    code, payload, _ = _run_cli(["prompt", "Wi-Fi", "--db", str(db)], capsys)

    assert code == 0
    assert payload["metadata"]["answer_generated"] is False
    assert "src.llm_core" not in sys.modules


def test_validate_answer_command_accepts_answer(tmp_path, capsys):
    db = tmp_path / "vm.sqlite3"
    document = tmp_path / "sop.txt"
    document.write_text("Users must connect to Wi-Fi during OOBE.\n", encoding="utf-8")
    main(["ingest", str(document), "--db", str(db)])
    capsys.readouterr()
    ref = SQLiteVerifiedMemoryStore(db).list_document_chunks()[0].chunk_id

    code, payload, _ = _run_cli([
        "validate-answer",
        "What does the SOP say about Wi-Fi?",
        "--db",
        str(db),
        "--answer",
        f"Users must connect to Wi-Fi during OOBE. [{ref}]",
    ], capsys)

    assert code == 0
    assert payload["command"] == "validate-answer"
    assert payload["severity"] == "pass"
    assert payload["metadata"]["answer_generated"] is False


def test_validate_answer_command_accepts_answer_file(tmp_path, capsys):
    db = tmp_path / "vm.sqlite3"
    document = tmp_path / "sop.txt"
    answer_file = tmp_path / "answer.txt"
    document.write_text("Users must connect to Wi-Fi during OOBE.\n", encoding="utf-8")
    main(["ingest", str(document), "--db", str(db)])
    capsys.readouterr()
    ref = SQLiteVerifiedMemoryStore(db).list_document_chunks()[0].chunk_id
    answer_file.write_text(f"Users must connect to Wi-Fi during OOBE. [{ref}]", encoding="utf-8")

    code, payload, _ = _run_cli([
        "validate-answer",
        "What does the SOP say about Wi-Fi?",
        "--db",
        str(db),
        "--answer-file",
        str(answer_file),
    ], capsys)

    assert code == 0
    assert payload["severity"] == "pass"
    assert payload["used_citation_refs"] == [ref]


def test_validate_answer_rejects_both_answer_and_answer_file(tmp_path, capsys):
    db = tmp_path / "vm.sqlite3"
    answer_file = tmp_path / "answer.txt"
    answer_file.write_text("answer", encoding="utf-8")

    code = main([
        "validate-answer",
        "Question?",
        "--db",
        str(db),
        "--answer",
        "answer",
        "--answer-file",
        str(answer_file),
    ])
    captured = capsys.readouterr()

    assert code != 0
    assert "exactly one of --answer or --answer-file" in captured.err


def test_validate_answer_rejects_neither_answer_nor_answer_file(tmp_path, capsys):
    db = tmp_path / "vm.sqlite3"

    code = main(["validate-answer", "Question?", "--db", str(db)])
    captured = capsys.readouterr()

    assert code != 0
    assert "exactly one of --answer or --answer-file" in captured.err


def test_validate_answer_exits_nonzero_for_validation_errors(tmp_path, capsys):
    db = tmp_path / "vm.sqlite3"
    document = tmp_path / "sop.txt"
    document.write_text("Users must connect to Wi-Fi during OOBE.\n", encoding="utf-8")
    main(["ingest", str(document), "--db", str(db)])
    capsys.readouterr()

    code, payload, _ = _run_cli([
        "validate-answer",
        "What does the SOP say about Wi-Fi?",
        "--db",
        str(db),
        "--answer",
        "Users must connect to Wi-Fi. [made-up:chunk:9999]",
    ], capsys)

    assert code != 0
    assert payload["severity"] == "error"
    assert payload["issues"][0]["code"] == "invented_citation"


def test_validate_answer_command_does_not_import_or_call_llm_core(tmp_path, capsys, monkeypatch):
    db = tmp_path / "vm.sqlite3"
    document = tmp_path / "sop.txt"
    document.write_text("Users must connect to Wi-Fi.\n", encoding="utf-8")

    def fail_network(*args, **kwargs):
        raise AssertionError("network should not be called")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    sys.modules.pop("src.llm_core", None)

    main(["ingest", str(document), "--db", str(db)])
    capsys.readouterr()
    code, payload, _ = _run_cli([
        "validate-answer",
        "Wi-Fi",
        "--db",
        str(db),
        "--answer",
        "Users must connect to Wi-Fi.",
    ], capsys)

    assert code == 0
    assert payload["metadata"]["answer_generated"] is False
    assert "src.llm_core" not in sys.modules


def test_generate_answer_command_works_with_fake_generation(tmp_path, capsys, monkeypatch):
    db = tmp_path / "vm.sqlite3"
    document = tmp_path / "sop.txt"
    document.write_text("Users must connect to Wi-Fi during OOBE.\n", encoding="utf-8")
    main(["ingest", str(document), "--db", str(db)])
    capsys.readouterr()
    ref = SQLiteVerifiedMemoryStore(db).list_document_chunks()[0].chunk_id

    async def fake_generate_answer(question, store, **kwargs):
        from verified_memory.workflows.generate_answer import generate_answer as real_generate_answer

        async def fake_llm(messages, **llm_kwargs):
            return f"Users must connect to Wi-Fi during OOBE. [{ref}]"

        return await real_generate_answer(question, store, llm_call=fake_llm, **kwargs)

    monkeypatch.setattr("verified_memory.cli.generate_answer", fake_generate_answer)

    code, payload, _ = _run_cli([
        "generate-answer",
        "What does the SOP say about Wi-Fi?",
        "--db",
        str(db),
    ], capsys)

    assert code == 0
    assert payload["command"] == "generate-answer"
    assert payload["safe_to_show"] is True
    assert payload["validation"]["severity"] == "pass"
    assert payload["metadata"]["llm_called"] is True
    assert payload["metadata"]["web_called"] is False


def test_generate_answer_command_returns_nonzero_for_validation_errors(tmp_path, capsys, monkeypatch):
    db = tmp_path / "vm.sqlite3"
    document = tmp_path / "sop.txt"
    document.write_text("Users must connect to Wi-Fi during OOBE.\n", encoding="utf-8")
    main(["ingest", str(document), "--db", str(db)])
    capsys.readouterr()

    async def fake_generate_answer(question, store, **kwargs):
        from verified_memory.workflows.generate_answer import generate_answer as real_generate_answer

        async def fake_llm(messages, **llm_kwargs):
            return "Users must connect to Wi-Fi. [made-up:chunk:9999]"

        return await real_generate_answer(question, store, llm_call=fake_llm, **kwargs)

    monkeypatch.setattr("verified_memory.cli.generate_answer", fake_generate_answer)

    code, payload, _ = _run_cli([
        "generate-answer",
        "What does the SOP say about Wi-Fi?",
        "--db",
        str(db),
    ], capsys)

    assert code != 0
    assert payload["safe_to_show"] is False
    assert payload["validation"]["severity"] == "error"
    assert payload["validation"]["issues"][0]["code"] == "invented_citation"


def test_generate_answer_format_answer_prints_answer_plus_validation(tmp_path, capsys, monkeypatch):
    db = tmp_path / "vm.sqlite3"
    document = tmp_path / "sop.txt"
    document.write_text("Users must connect to Wi-Fi during OOBE.\n", encoding="utf-8")
    main(["ingest", str(document), "--db", str(db)])
    capsys.readouterr()
    ref = SQLiteVerifiedMemoryStore(db).list_document_chunks()[0].chunk_id

    async def fake_generate_answer(question, store, **kwargs):
        from verified_memory.workflows.generate_answer import generate_answer as real_generate_answer

        async def fake_llm(messages, **llm_kwargs):
            return f"Users must connect to Wi-Fi during OOBE. [{ref}]"

        return await real_generate_answer(question, store, llm_call=fake_llm, **kwargs)

    monkeypatch.setattr("verified_memory.cli.generate_answer", fake_generate_answer)

    code = main([
        "generate-answer",
        "What does the SOP say about Wi-Fi?",
        "--db",
        str(db),
        "--format",
        "answer",
    ])
    captured = capsys.readouterr()

    assert code == 0
    assert "Users must connect to Wi-Fi during OOBE." in captured.out
    assert "Validation: pass" in captured.out
    assert "Safe to show: true" in captured.out
    assert captured.err == ""
