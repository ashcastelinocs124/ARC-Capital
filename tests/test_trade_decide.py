from castelino.agents.trade import decide, llm


def test_decisions_api_probabilities_per_question():
    sent = {}

    def post(body):
        sent.update(body)
        return {
            "answers": [
                {"type": "predicate", "name": "research", "probability": 0.93},
                {"type": "predicate", "name": "edit", "probability": 0.04},
            ],
            "usage": {"input_tokens": 480},
        }

    m = llm.Meter()
    out = decide.decide("ctx", "My read is the RBI defends 95", ["research", "edit"], m, post=post)
    assert out == {"research": 0.93, "edit": 0.04}
    assert sent["model"] == "gpt-6-luna"
    assert sent["input"].endswith("User's latest message: My read is the RBI defends 95")
    assert [q["name"] for q in sent["questions"]] == ["research", "edit"]
    assert all(q["type"] == "predicate" and q["instructions"] for q in sent["questions"])
    assert m.total > 0


def test_api_error_falls_back_to_a_structured_yes_no(monkeypatch):
    def post(body):
        raise RuntimeError("403 Decision API is not enabled")

    asked = []

    def fake_structured(agent, model, messages, schema, meter, fallback=None):
        asked.append(messages[0]["content"])
        return schema(yes=True)

    monkeypatch.setattr(llm, "structured", fake_structured)
    out = decide.decide("ctx", "msg", ["research"], llm.Meter(), post=post)
    assert out == {"research": 1.0}
    assert decide.QUESTIONS["research"] in asked[0]
