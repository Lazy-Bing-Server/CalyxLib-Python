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

T = TypeVar("T")


@final
class __Blank:
    @classmethod
    def ser_blank(cls, value: Any, handler: SerializerFunctionWrapHandler):
        return None if isinstance(value, cls) else handler(value)

    @classmethod
    def val_blank(cls, value: Any):
        return BLANK if value is None else value


BLANK = __Blank()
Blankable = Annotated[
    Union[T, __Blank],
    BeforeValidator(__Blank.val_blank),
    WrapSerializer(__Blank.ser_blank)
]


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

        carrier = CommentCarrier(target_dict)
        carrier.global_wrapper = info.context.global_wrapper
        for k, f in self.model_fields.items():
            for meta in f.metadata:
                if isinstance(meta, ConfigComment):
                    carrier.set_comment_to_nested_key([k], meta)
        return carrier
