"""Deterministic type-stub generation for Monty type checking."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from types import NoneType
from typing import Any, get_args, get_origin

from pydantic import BaseModel


class StubGenerator:
    """Generate minimal deterministic type stubs for models and tools."""

    def generate(
        self,
        *,
        input_model: type[BaseModel],
        output_model: type[BaseModel] | None,
        tools: list[Callable[..., Any]],
    ) -> str:
        lines = [
            "from typing import Any, TypedDict",
            "",
            self._model_stub(input_model),
        ]
        if output_model is not None:
            lines.extend(["", self._model_stub(output_model)])

        for tool in sorted(tools, key=lambda item: item.__name__):
            lines.extend(["", self._tool_stub(tool)])

        return "\n".join(lines).strip() + "\n"

    def _model_stub(self, model: type[BaseModel]) -> str:
        lines = [f"class {model.__name__}(TypedDict):"]
        for field_name, field_info in model.model_fields.items():
            annotation = self._annotation_to_stub(field_info.annotation)
            lines.append(f"    {field_name}: {annotation}")
        if len(lines) == 1:
            lines.append("    pass")
        return "\n".join(lines)

    def _tool_stub(self, tool: callable) -> str:
        signature = inspect.signature(tool)
        params: list[str] = []
        for name, param in signature.parameters.items():
            if param.kind in {param.VAR_POSITIONAL, param.VAR_KEYWORD}:
                params.append(f"*{name}" if param.kind is param.VAR_POSITIONAL else f"**{name}")
                continue
            annotation = self._annotation_to_stub(param.annotation)
            params.append(f"{name}: {annotation}")

        return_annotation = self._annotation_to_stub(signature.return_annotation)
        return f"def {tool.__name__}({', '.join(params)}) -> {return_annotation}: ..."

    def _annotation_to_stub(self, annotation: Any) -> str:
        if annotation is inspect.Signature.empty:
            return "Any"
        if annotation is Any:
            return "Any"
        if annotation is NoneType:
            return "None"
        if annotation is type(None):
            return "None"
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return annotation.__name__
        if isinstance(annotation, type):
            return annotation.__name__

        origin = get_origin(annotation)
        if origin is None:
            return str(annotation).replace("typing.", "")

        args = [self._annotation_to_stub(item) for item in get_args(annotation)]
        origin_name = str(origin).replace("typing.", "")

        if origin_name in {"<class 'list'>", "list"}:
            return f"list[{args[0] if args else 'Any'}]"
        if origin_name in {"<class 'dict'>", "dict"}:
            left = args[0] if args else "Any"
            right = args[1] if len(args) > 1 else "Any"
            return f"dict[{left}, {right}]"
        if origin_name in {"<class 'tuple'>", "tuple"}:
            return f"tuple[{', '.join(args)}]" if args else "tuple[Any, ...]"
        if origin_name.endswith("Union"):
            if len(args) == 2 and "None" in args:
                core = args[0] if args[1] == "None" else args[1]
                return f"{core} | None"
            return " | ".join(args)

        return str(annotation).replace("typing.", "")
