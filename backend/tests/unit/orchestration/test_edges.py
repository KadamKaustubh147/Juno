from langgraph.graph import END

from app.orchestration.edges import route_after_assessment


def test_session_done_ends_the_graph():
    assert route_after_assessment({"session_done": True, "section_complete": True}) == END


def test_section_complete_goes_to_select_next_section():
    assert route_after_assessment({"session_done": False, "section_complete": True}) == "select_next_section"


def test_otherwise_goes_to_chatbot():
    assert route_after_assessment({"session_done": False, "section_complete": False}) == "chatbot"


def test_missing_flags_count_as_false():
    assert route_after_assessment({}) == "chatbot"
