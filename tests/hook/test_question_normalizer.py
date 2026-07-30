from cataforge.runtime.hook.question import normalize_answers


def test_codex_top_level_answer_records_are_normalized() -> None:
    payload = (
        '{"answers": ['
        '{"question_id": "architecture", "answers": ["Legacy"]},'
        '{"id": "database", "answer": "PostgreSQL"},'
        '{"question_id": "empty", "answers": []},'
        '{"answers": ["missing id"]},'
        '"invalid"'
        "]}"
    )

    assert normalize_answers(payload) == {
        "architecture": ["Legacy"],
        "database": ["PostgreSQL"],
    }
