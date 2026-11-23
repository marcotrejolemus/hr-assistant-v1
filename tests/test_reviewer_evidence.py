"""Pruebas de I7 (F3): el Reviewer recibe la evidencia de las herramientas.

El Reviewer sigue sin historial, sin herramientas y sin secretos; ahora ve los
resultados de las tools de esta petición, serializados y truncados, para no
rechazar respuestas correctas por no conocer los datos.
"""

import json

from doubles import is_reviewer_call

from app.guards import SAFE_ANSWER
from app.llm import Completion
from app.reviewer import MAX_EVIDENCE_CHARS, REVIEWER_PROMPT, build_review_messages

HISTORY_TEXT = "Mensaje previo de prueba"


class RejectingReviewerModel:  # pylint: disable=too-few-public-methods
    """Specialist que consulta EMP-0004 y responde ``Ok``; el Reviewer rechaza.

    Guarda los mensajes de cada llamada del Reviewer.
    """

    def __init__(self):
        self._specialist_calls = 0
        self.reviewer_messages = []

    async def complete(self, messages, *, model, max_tokens):
        """Rechaza como Reviewer o sigue el guion del Specialist."""
        del model, max_tokens
        if is_reviewer_call(messages):
            self.reviewer_messages.append([dict(message) for message in messages])
            reply = {"verdict": "reject", "issues": ["dato dudoso"]}
        else:
            self._specialist_calls += 1
            reply = (
                {"tool": "get_employee", "args": {"employee_id": "EMP-0004"}}
                if self._specialist_calls == 1
                else {"answer": "Ok"}
            )
        return Completion(text=json.dumps(reply), input_tokens=1, output_tokens=1)


def _contents(messages):
    """Une el contenido de todos los mensajes en un solo texto."""
    return "\n".join(message["content"] for message in messages)


def test_reviewer_sees_the_tool_evidence_and_a_rejection_still_gives_the_safe_answer(
    make_client,
):
    """El borrador es ``Ok``: el nombre solo puede venir de la evidencia."""
    model = RejectingReviewerModel()
    history = [{"role": "user", "content": HISTORY_TEXT}]

    body = (
        make_client(model=model)
        .post("/ask", json={"question": "¿Quién es EMP-0004?", "history": history})
        .json()
    )

    assert len(model.reviewer_messages) == 1
    messages = model.reviewer_messages[0]
    assert [message["role"] for message in messages] == ["system", "user"]
    assert "Jorge" in _contents(messages)
    assert HISTORY_TEXT not in _contents(messages)
    assert body["review"]["status"] == "rejected"
    assert body["answer"] == SAFE_ANSWER


def test_reviewer_evidence_is_truncated_to_max_evidence_chars():
    evidence = [{"nota": "x" * 5000}]

    messages = build_review_messages("¿Quién es EMP-0004?", "Borrador", evidence)

    content = _contents(messages)
    assert MAX_EVIDENCE_CHARS == 1500
    assert "x" * 1000 in content
    assert "x" * MAX_EVIDENCE_CHARS not in content


def test_reviewer_without_tools_is_told_that_no_tool_was_consulted():
    """Sin tools, la evidencia lo dice y el prompt pide revisar contra la evidencia."""
    messages = build_review_messages("Hola", "Puedo consultar empleados.", [])

    assert [message["role"] for message in messages] == ["system", "user"]
    assert "ninguna" in messages[1]["content"].casefold()
    assert "evidencia" in REVIEWER_PROMPT.casefold()
