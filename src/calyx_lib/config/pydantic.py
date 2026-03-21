import dataclasses
from typing import Optional, Any, List, Union, TypeVar

from typing_extensions import final, Annotated

from pydantic import (
    BaseModel,
    field_validator,
    BeforeValidator,
    WrapSerializer,
    SerializerFunctionWrapHandler,
    ConfigDict,
    model_serializer,
    SerializationInfo
)

from calyx_lib.config.yaml import CommentCarrier, ConfigComment, CommentTextWrapper


__all__ = ["CommentedModel", "BLANK", "Blankable"]


T = TypeVar("T")


@final
class __Blank:
    @classmethod
    def ser_blank(cls, value: Any, handler: SerializerFunctionWrapHandler):
        return None if isinstance(value, cls) else handler(value)

    @classmethod
    def val_blank(cls, value: Any):
        return BLANK if value is None else value

    def __repr__(self):
        return "<Blank>"

    def __bool__(self):
        return False


BLANK = __Blank()
"""
The singleton `BLANK` object is used in configuration files 
for Pydantic serialization and deserialization to preserve None values.

The distinction from using `None` directly is as follows: 
a field assigned the `BLANK` object will be retained and dumped as None when calling `model_dump(exclude_none=True)`,
whereas a field directly set to `None` will be excluded entirely during that same dumping process.

Annotate the field type as `Blankable[T]` to allow the field to accept `BLANK` as a valid value.
Set model config `arbitrary_types_allowed=True` to allow the model to accept `BLANK` as a valid value.
"""


Blankable = Annotated[
    Union[T, __Blank],
    BeforeValidator(__Blank.val_blank),
    WrapSerializer(__Blank.ser_blank)
]
"""
Annotate the field type as `Blankable[T]` to allow the field to accept `BLANK` as a valid value.
"""


class PydanticValidationErrorMessage(BaseModel):
    ctx: Optional[Any] = None
    input: Any
    loc: List[Union[str, int]]
    msg: str
    type: str
    url: str

    @field_validator('loc', mode='before')
    @classmethod
    def model_val_loc(cls, v: Any):
        return list(v)


@dataclasses.dataclass
class ConfigSerializationContext:
    export_carrier: bool = True
    global_wrapper: "CommentTextWrapper" = lambda text: text


class CommentedModel(BaseModel):
    """
    This model is available to be attached with YAML comments.
    Annotate fields with `Annotated[T, ConfigComment(...)]`
    to make the serialization result `CommentedMap` contains the comment you want
    """
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra='ignore',
        use_enum_values=True
    )

    @model_serializer(mode='wrap')
    def ser_model(
            self, nxt, info: SerializationInfo
    ) -> Union[dict, CommentCarrier]:
        target_dict: dict = nxt(self)
        if not (
                isinstance(info.context, ConfigSerializationContext)
                and
                info.context.export_carrier
        ):
            return target_dict

        carrier = CommentCarrier(target_dict, self.__class__)
        carrier.global_wrapper = info.context.global_wrapper
        for k, f in self.model_fields.items():
            for meta in f.metadata:
                if isinstance(meta, ConfigComment):
                    carrier.set_comment_to_nested_key([k], meta)
        return carrier
