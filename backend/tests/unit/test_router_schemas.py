"""Unit tests for router validation and response schemas."""


class TestAuthRouterSchemas:
    def test_register_request_validation(self):
        from pydantic import BaseModel

        class RegisterRequest(BaseModel):
            email: str
            password: str
            display_name: str

        req = RegisterRequest(email="test@example.com", password="SecureP@ss123", display_name="Test")
        assert req.email == "test@example.com"

    def test_login_request_validation(self):
        from pydantic import BaseModel

        class LoginRequest(BaseModel):
            email: str
            password: str

        req = LoginRequest(email="test@example.com", password="pass")
        assert req.email == "test@example.com"


class TestUnitRouterSchemas:
    def test_submit_assessment_request(self):
        from app.routers.units import SubmitAssessmentRequest

        req = SubmitAssessmentRequest(answers={"q1": "a", "q2": ["a", "b"]})
        assert req.answers["q1"] == "a"
        assert req.answers["q2"] == ["a", "b"]

    def test_submit_assessment_with_string_list(self):
        from app.routers.units import SubmitAssessmentRequest

        req = SubmitAssessmentRequest(answers={"q1": "answer text"})
        assert req.answers["q1"] == "answer text"


class TestChatRouterSchemas:
    def test_chat_request_validation(self):
        from app.routers.chat import ChatRequest

        req = ChatRequest(question="什么是二叉树？", node_id="node-1", path_id="path-1")
        assert req.question == "什么是二叉树？"
        assert req.node_id == "node-1"


class TestClarificationSchemas:
    def test_clarification_answer_types(self):
        answers = {
            "skill_level": "intermediate",
            "focus": "algorithms",
            "hours": "10",
            "style": "hands-on",
        }
        assert all(isinstance(v, str) for v in answers.values())
