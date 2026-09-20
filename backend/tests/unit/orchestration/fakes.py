"""Stand-ins for the chat model, so no test ever touches the network."""

from langchain_core.messages import AIMessage


class FakeLLM:
    """Quacks like ChatOpenAI for the two ways the orchestration code calls it.

    structured -- results handed back, in order, by `with_structured_output(schema).invoke(...)`.
                  Each item is a schema instance, a dict of its fields, or an Exception to raise.
    replies    -- strings returned, in order, as AIMessage content by a plain `.invoke(...)`.
    native     -- False makes `with_structured_output` raise, as an endpoint without support would.
    prompts    -- everything passed to `.invoke`, in order (a string, or a list of messages).
    """

    def __init__(self, structured=(), replies=(), native=True):
        self.structured = list(structured)
        self.replies = list(replies)
        self.native = native
        self.prompts: list = []

    def with_structured_output(self, schema, **_):
        if not self.native:
            raise NotImplementedError("no native structured output")
        return _StructuredCall(self, schema)

    def invoke(self, prompt, *args, **kwargs):
        self.prompts.append(prompt)
        if not self.replies:
            raise AssertionError("FakeLLM: unexpected plain invoke")
        return AIMessage(content=self.replies.pop(0))


class _StructuredCall:
    def __init__(self, llm: FakeLLM, schema):
        self.llm = llm
        self.schema = schema

    def invoke(self, prompt, *args, **kwargs):
        self.llm.prompts.append(prompt)
        if not self.llm.structured:
            raise AssertionError("FakeLLM: unexpected structured invoke")
        item = self.llm.structured.pop(0)
        if isinstance(item, Exception):
            raise item
        return self.schema(**item) if isinstance(item, dict) else item


class ForbiddenLLM:
    """The default for every node module in tests: any use is a test that forgot to install a fake."""

    def with_structured_output(self, *args, **kwargs):
        raise AssertionError("a unit test reached a real LLM")

    def invoke(self, *args, **kwargs):
        raise AssertionError("a unit test reached a real LLM")
