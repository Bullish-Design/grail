"""Deterministic type-stub generation for Monty type checking."""

from __future__ import annotations

import dataclasses
import inspect
from collections.abc import Callable
from types import GenericAlias, NoneType, UnionType
from typing import Any, Union, get_args, get_origin
from typing import Callable as TypingCallable

from pydantic import BaseModel


class StubGenerator:
    """Generate minimal deterministic type stubs for models and tools."""

    def __init__(self) -> None:
        self._uses_any = False
        self._new_types: dict[str, Any] = {}
        self._type_aliases: dict[str, Any] = {}
        self._base_models: dict[str, type[BaseModel]] = {}
        self._dataclasses: dict[str, type[Any]] = {}

    def generate(
        self,
        *,
        input_model: type[BaseModel],
        output_model: type[BaseModel] | None,
        tools: list[Callable[..., Any]],
    ) -> str:
        self._reset()
        self._collect_model_annotations(input_model)
        if output_model is not None:
            self._collect_model_annotations(output_model)

        for tool in tools:
            self._collect_tool_annotations(tool)

        import_names = ["TypedDict"]
        if self._uses_any:
            import_names.insert(0, "Any")
        if self._new_types:
            import_names.append("NewType")

        lines = [f"from typing import {', '.join(import_names)}", ""]

        custom_blocks = self._render_custom_definitions(
            skip_model_names={
                input_model.__name__,
                output_model.__name__ if output_model is not None else "",
            }
        )
        if custom_blocks:
            lines.extend(["", "\n\n".join(custom_blocks)])

        lines.extend(["", self._model_stub(input_model)])
        if output_model is not None:
            lines.extend(["", self._model_stub(output_model)])

        for tool in sorted(tools, key=lambda item: item.__name__):
            lines.extend(["", self._tool_stub(tool)])

        return "\n".join(lines).strip() + "\n"

    def _reset(self) -> None:
        self._uses_any = False
        self._new_types = {}
        self._type_aliases = {}
        self._base_models = {}
        self._dataclasses = {}

    def _render_custom_definitions(self, *, skip_model_names: set[str]) -> list[str]:
        rendered: list[str] = []
        emitted: set[str] = set()

        for name in sorted(self._new_types):
            if name in emitted:
                continue
            new_type = self._new_types[name]
            self._collect_annotation(new_type.__supertype__)
            supertype = self._annotation_to_stub(new_type.__supertype__)
            rendered.append(f'{name} = NewType("{name}", {supertype})')
            emitted.add(name)

        for alias_name in sorted(self._type_aliases):
            if alias_name in emitted:
                continue
            alias = self._type_aliases[alias_name]
            self._collect_annotation(alias.__value__)
            rendered.append(f"{alias_name} = {self._annotation_to_stub(alias.__value__)}")
            emitted.add(alias_name)

        for model_name in sorted(self._base_models):
            if model_name in skip_model_names or model_name in emitted:
                continue
            rendered.append(self._model_stub(self._base_models[model_name]))
            emitted.add(model_name)

        for dataclass_name in sorted(self._dataclasses):
            if dataclass_name in emitted:
                continue
            rendered.append(self._dataclass_stub(self._dataclasses[dataclass_name]))
            emitted.add(dataclass_name)

        return rendered

    def _model_stub(self, model: type[BaseModel]) -> str:
        lines = [f"class {model.__name__}(TypedDict):"]
        for field_name, field_info in model.model_fields.items():
            annotation = self._annotation_to_stub(field_info.annotation)
            lines.append(f"    {field_name}: {annotation}")
        if len(lines) == 1:
            lines.append("    pass")
        return "\n".join(lines)

    def _dataclass_stub(self, item: type[Any]) -> str:
        lines = [f"class {item.__name__}:"]
        for field in dataclasses.fields(item):
            annotation = self._annotation_to_stub(field.type)
            lines.append(f"    {field.name}: {annotation}")
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

    def _collect_model_annotations(self, model: type[BaseModel]) -> None:
        for field_info in model.model_fields.values():
            self._collect_annotation(field_info.annotation)

    def _collect_tool_annotations(self, tool: Callable[..., Any]) -> None:
        signature = inspect.signature(tool)
        for parameter in signature.parameters.values():
            self._collect_annotation(parameter.annotation)
        self._collect_annotation(signature.return_annotation)

    def _collect_annotation(self, annotation: Any) -> None:
        if annotation is inspect.Signature.empty:
            return
        if annotation is Any:
            self._uses_any = True
            return
        if annotation is NoneType or annotation is type(None):
            return

        if self._is_new_type(annotation):
            self._new_types[annotation.__name__] = annotation
            self._collect_annotation(annotation.__supertype__)
            return

        if self._is_type_alias(annotation):
            self._type_aliases[annotation.__name__] = annotation
            self._collect_annotation(annotation.__value__)
            return

        if self._is_plain_class(annotation) and issubclass(annotation, BaseModel):
            self._base_models[annotation.__name__] = annotation
            self._collect_model_annotations(annotation)
            return

        if self._is_plain_class(annotation) and dataclasses.is_dataclass(annotation):
            self._dataclasses[annotation.__name__] = annotation
            for field in dataclasses.fields(annotation):
                self._collect_annotation(field.type)
            return

        origin = get_origin(annotation)
        if origin is None:
            return
        for arg in get_args(annotation):
            if arg is Ellipsis:
                continue
            self._collect_annotation(arg)

    def _annotation_to_stub(self, annotation: Any) -> str:
        if annotation is inspect.Signature.empty or annotation is Any:
            self._uses_any = True
            return "Any"
        if annotation is NoneType or annotation is type(None):
            return "None"

        if self._is_new_type(annotation):
            self._new_types[annotation.__name__] = annotation
            return annotation.__name__

        if self._is_type_alias(annotation):
            self._type_aliases[annotation.__name__] = annotation
            return annotation.__name__

        if self._is_plain_class(annotation) and issubclass(annotation, BaseModel):
            self._base_models[annotation.__name__] = annotation
            return annotation.__name__

        if self._is_plain_class(annotation) and dataclasses.is_dataclass(annotation):
            self._dataclasses[annotation.__name__] = annotation
            return annotation.__name__

        if self._is_plain_class(annotation):
            return annotation.__name__

        origin = get_origin(annotation)
        if origin is None:
            text = str(annotation).replace("typing.", "")
            if text == "Any":
                self._uses_any = True
            return text

        if origin in {UnionType, Union}:
            return self._render_union(get_args(annotation))

        args = [
            self._annotation_to_stub(item)
            for item in get_args(annotation)
            if item is not Ellipsis
        ]
        if origin in {list, set, frozenset}:
            inner = args[0] if args else "Any"
            self._uses_any = self._uses_any or not args
            return f"{origin.__name__}[{inner}]"
        if origin is dict:
            left = args[0] if args else "Any"
            right = args[1] if len(args) > 1 else "Any"
            self._uses_any = self._uses_any or len(args) < 2
            return f"dict[{left}, {right}]"
        if origin is tuple:
            tuple_args = get_args(annotation)
            if len(tuple_args) == 2 and tuple_args[1] is Ellipsis:
                return f"tuple[{self._annotation_to_stub(tuple_args[0])}, ...]"
            return f"tuple[{', '.join(args)}]" if args else "tuple[Any, ...]"
        if origin in {Callable, TypingCallable}:
            call_args = get_args(annotation)
            if len(call_args) != 2:
                self._uses_any = True
                return "Callable[..., Any]"
            param_spec, ret_spec = call_args
            if param_spec is Ellipsis:
                params_text = "..."
            else:
                params_text = ", ".join(self._annotation_to_stub(item) for item in param_spec)
                params_text = f"[{params_text}]"
            return_text = self._annotation_to_stub(ret_spec)
            if params_text == "...":
                return f"Callable[..., {return_text}]"
            return f"Callable[{params_text}, {return_text}]"

        origin_name = self._annotation_to_stub(origin)
        return f"{origin_name}[{', '.join(args)}]" if args else origin_name

    def _render_union(self, union_args: tuple[Any, ...]) -> str:
        rendered = [self._annotation_to_stub(item) for item in union_args]
        non_none = sorted({item for item in rendered if item != "None"})
        has_none = "None" in rendered

        if has_none and len(non_none) == 1:
            return f"{non_none[0]} | None"
        if has_none:
            return " | ".join([*non_none, "None"])
        return " | ".join(non_none)

    def _is_new_type(self, annotation: Any) -> bool:
        return callable(annotation) and hasattr(annotation, "__name__") and hasattr(
            annotation, "__supertype__"
        )

    def _is_type_alias(self, annotation: Any) -> bool:
        return type(annotation).__name__ == "TypeAliasType"

    def _is_plain_class(self, annotation: Any) -> bool:
        return isinstance(annotation, type) and not isinstance(annotation, GenericAlias)
