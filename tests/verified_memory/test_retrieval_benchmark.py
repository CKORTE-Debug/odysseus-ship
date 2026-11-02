from scripts.evaluate_verified_memory import evaluate


def test_synthetic_retrieval_regression_gates():
    result = evaluate()
    assert result['summary']['development']['cases'] == 30
    assert result['summary']['reserved']['cases'] == 10
    assert result['gates_passed'], result
