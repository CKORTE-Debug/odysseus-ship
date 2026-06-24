import sys

from verified_memory.config import VerifiedMemoryGenerationConfig
from verified_memory.contracts import VerifiedMemoryAnswerRequest, VerifiedMemoryAnswerResponse


def test_contract_request_response_to_dict_works():
    config = VerifiedMemoryGenerationConfig(model="fake", temperature=0.2)
    request = VerifiedMemoryAnswerRequest(question="Wi-Fi?", db_path="vm.db", generation_config=config)
    response = VerifiedMemoryAnswerResponse(
        question="Wi-Fi?",
        answer="Use Wi-Fi.",
        safe_to_show=True,
        validation={"severity": "pass"},
        generation_metadata={"llm_called": True},
    )

    assert request.to_dict()["generation_config"]["model"] == "fake"
    assert response.to_dict()["validation"] == {"severity": "pass"}


def test_contract_objects_do_not_call_llm_or_db():
    sys.modules.pop("src.llm_core", None)
    request = VerifiedMemoryAnswerRequest(question="Wi-Fi?")
    response = VerifiedMemoryAnswerResponse(question="Wi-Fi?", answer="", safe_to_show=False, validation={})

    assert request.to_dict()["db_path"] is None
    assert response.to_dict()["generation_metadata"] == {}
    assert "src.llm_core" not in sys.modules
