"""@target classes for prompt strategy comparison.

Calls GPT-4.1-mini via Foundry with different prompt strategies:
- baseline: just answer the question
- single_shot: one example shown
- few_shot: multiple examples shown
"""
from __future__ import annotations
from typing import Any, Dict
from azure.ai.evaluation._engine.decorators import target, BaseTarget


SYSTEM_PROMPTS = {
    "baseline": "Answer the question concisely and accurately.",
    "single_shot": """Answer the question concisely and accurately.

Example:
Q: What is Python?
A: Python is a high-level, interpreted programming language known for its readability and versatility, widely used in web development, data science, and automation.""",
    "few_shot": """Answer the question concisely and accurately.

Example 1:
Q: What is Python?
A: Python is a high-level, interpreted programming language known for its readability and versatility, widely used in web development, data science, and automation.

Example 2:
Q: What is Docker?
A: Docker is a platform for building, shipping, and running applications in lightweight, isolated containers that package code with all its dependencies.

Example 3:
Q: What is REST?
A: REST (Representational State Transfer) is an architectural style for designing networked applications using stateless HTTP requests to access and manipulate resources.""",
}


@target(name="prompt_compare")
class PromptCompareModel(BaseTarget):
    """Calls GPT-4.1-mini with configurable prompt strategy."""

    def __init__(self, prompt: str = "baseline", temperature: float = 0.7,
                 max_tokens: int = 200, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.prompt_strategy = prompt
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.system_prompt = SYSTEM_PROMPTS.get(prompt, SYSTEM_PROMPTS["baseline"])

        # Create Azure OpenAI client
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
        from openai import AzureOpenAI
        token_provider = get_bearer_token_provider(
            DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
        )
        self._client = AzureOpenAI(
            azure_endpoint="https://foundry-evee-ko9z2s7c.cognitiveservices.azure.com/",
            azure_ad_token_provider=token_provider,
            api_version="2024-10-21",
        )

    def infer(self, input: Dict[str, Any]) -> Dict[str, Any]:
        question = input.get("question", "")
        response = self._client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": question},
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return {"answer": response.choices[0].message.content}
