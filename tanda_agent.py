"""The AI coordinator: a Gemini model that looks at the circle through our tools.

HOW IT WORKS (the loop, in plain English)
1. We send Gemini the person's question, our rules (AGENT_INSTRUCTIONS), and a
   menu of tools it is allowed to ask for.
2. Gemini either answers in words, or replies "please run tool X".
3. If it asks for a tool, WE run it (through call_tool, which only allows the
   safe tools) and send the result back.
4. Repeat until Gemini answers in words, or we hit a safety limit.

Gemini never touches PayPal and never does any math. It only reads results that
our own Python code produced, and a human still has to approve every round.

Uses plain `requests` (no special Google library) so every step is visible.
"""
import os

import requests

from tanda_tools import AGENT_INSTRUCTIONS, TOOL_SPECS, call_tool

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"

# Google renames and retires models often. This default is a guess that you should
# confirm in Google AI Studio; set GEMINI_MODEL in .env to use a different one.
DEFAULT_MODEL = "gemini-3.5-flash-lite"

MAX_STEPS = 6                  # most tool round-trips allowed for one question
QUESTIONS_PER_VISITOR = 15     # limit per browser session (protects your free quota)
QUESTIONS_PER_SERVER = 300     # limit for the whole running server
_server_questions = 0


class AgentError(Exception):
    """A problem we can explain to the user in one sentence."""


def _declarations():
    """Our tool list in the shape Gemini expects.

    Gemini rejects an empty 'parameters' block, so tools that take no inputs
    get no 'parameters' key at all.
    """
    out = []
    for spec in TOOL_SPECS:
        d = {"name": spec["name"], "description": spec["description"]}
        if spec["parameters"].get("properties"):
            d["parameters"] = spec["parameters"]
        out.append(d)
    return out


def _generate(model, api_key, contents):
    """One request to Gemini. Returns its reply as a dictionary."""
    url = f"{API_ROOT}/{model}:generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": AGENT_INSTRUCTIONS}]},
        "contents": contents,
        "tools": [{"functionDeclarations": _declarations()}],
    }
    try:
        resp = requests.post(
            url,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json=body,
            timeout=60,
        )
    except requests.RequestException:
        raise AgentError("Could not reach Google's servers. Check the internet "
                         "connection and try again.")
    if resp.status_code == 200:
        return resp.json()

    try:
        detail = resp.json().get("error", {}).get("message", "")
    except ValueError:
        detail = ""
    detail = detail.replace(api_key, "***")[:200]       # never show the key
    explanations = {
        400: "Google rejected the request. This is often an invalid API key.",
        401: "Google rejected the API key. Check GEMINI_API_KEY.",
        403: "Google refused access with this API key. Check the key and its settings.",
        404: f"Google does not know the model '{model}'. Set GEMINI_MODEL to a model "
             "your key can use (see Google AI Studio).",
        429: "The free-tier limit was reached. Wait a minute and try again.",
    }
    message = explanations.get(resp.status_code, f"Google returned an error ({resp.status_code}).")
    raise AgentError(f"{message} {detail}".strip())


class Coordinator:
    """Asks Gemini questions about a TandaSession. One per visitor."""

    def __init__(self, api_key=None, model=None, max_questions=QUESTIONS_PER_VISITOR):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL") or DEFAULT_MODEL
        self.max_questions = max_questions
        self.asked = 0

    @property
    def available(self):
        return bool(self.api_key)

    @property
    def questions_left(self):
        return max(self.max_questions - self.asked, 0)

    def ask(self, session, question):
        """Answer one question. Always returns a dictionary and never raises:
        {"answer": text or None, "tools_used": [...], "error": text or None}"""
        global _server_questions
        question = (question or "").strip()
        if not question:
            return self._fail("Type a question first.")
        if not self.available:
            return self._fail("The AI coordinator is switched off: no GEMINI_API_KEY is set.")
        if self.asked >= self.max_questions:
            return self._fail("You have used all the questions for this session.")
        if _server_questions >= QUESTIONS_PER_SERVER:
            return self._fail("This demo has reached its question limit for now.")
        self.asked += 1
        _server_questions += 1
        try:
            answer, tools_used = self._run(session, question)
        except AgentError as e:
            return self._fail(str(e))
        return {"answer": answer, "tools_used": tools_used, "error": None}

    @staticmethod
    def _fail(message):
        return {"answer": None, "tools_used": [], "error": message}

    def _run(self, session, question):
        # Each question starts fresh. The tools return the current state every time.
        contents = [{"role": "user", "parts": [{"text": question}]}]
        tools_used = []
        for _ in range(MAX_STEPS):
            reply = _generate(self.model, self.api_key, contents)
            candidates = reply.get("candidates") or []
            if not candidates or "content" not in candidates[0]:
                raise AgentError("Gemini returned no answer (it may have blocked the "
                                 "request). Try rephrasing the question.")
            content = candidates[0]["content"]
            # Keep Gemini's reply EXACTLY as received. Newer models attach a hidden
            # "thought signature" that must be sent back, or the next request fails.
            contents.append(content)
            parts = content.get("parts", [])

            calls = [p["functionCall"] for p in parts if "functionCall" in p]
            if not calls:                                    # a plain-words answer: done
                text = "".join(p["text"] for p in parts if p.get("text") and not p.get("thought"))
                if not text.strip():
                    raise AgentError("Gemini returned an empty answer. Try again.")
                return text.strip(), tools_used

            results = []
            for call in calls:                               # Gemini asked for tools
                name = call.get("name")
                output = call_tool(session, name, call.get("args") or {})
                refused = "error" in output and "not a tool you can use" in str(output["error"])
                tools_used.append(f"{name} (refused)" if refused else name)
                results.append({"functionResponse": {"name": name, "response": output}})
            contents.append({"role": "user", "parts": results})
        raise AgentError("The coordinator needed too many steps and stopped. "
                         "Try a simpler question.")
