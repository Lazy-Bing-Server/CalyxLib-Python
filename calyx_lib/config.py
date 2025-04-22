from pathlib import Path
from typing import TypeVar, Union, Any, Optional, List, Iterable, TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, SerializerFunctionWrapHandler, \
    ValidationError, TypeAdapter
from pydantic.functional_serializers import WrapSerializer, model_serializer
from pydantic.functional_validators import BeforeValidator
from ruamel.yaml import YAML, CommentedMap
from typing_extensions import Annotated, final

from calyx_lib.translator import calyx_translator
from calyx_lib.utils import PathStr, set_value_to_nested_subscriptable_item, \
    get_value_from_nested_subscriptable_item

if TYPE_CHECKING:
    from typing import Literal
    from logging import Logger


__all__ = [
    "BLANK",
    "Blankable",
    "ConfigModel"
]


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
    loc: Iterable[str]
    msg: str
    type: str
    url: str


class CommentedModel(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra='ignore',
        use_enum_values=True,
        use_attribute_docstrings=True
    )

    @model_serializer(mode='wrap')
    def ser_desc(self, nxt: SerializerFunctionWrapHandler):
        fields = CommentedModel.model_fields
        serialized = CommentedMap(nxt(self))
        for k, f in fields.items():
            if k in serialized.keys():
                serialized.yaml_set_comment_before_after_key(k, before=f.description)
        return serialized


class ConfigModel(CommentedModel):
    def model_save_config(
            self,
            file_name: PathStr,
            logger: Optional[Logger] = None,
            failure_policy: "Literal['regen', 'raise']" = 'regen',
            encoding: str = 'utf8',
    ):
        file_path = Path(file_name)
        if logger is None:
            logger = calyx_translator.logger
        if file_path.is_dir():
            file_path.rmdir()
        try:
            serialized = self.model_dump()
        except Exception as exc:
            if failure_policy == 'raise':
                raise exc
            serialized = self.__class__().model_dump()
        yaml = YAML(typ='rt')
        yaml.width = 1048576
        yaml.allow_unicode = True
        with open(file_path, mode='r', encoding=encoding) as f:
            yaml.dump(serialized, f)
        logger.info(
            calyx_translator.rtr(
                'config.saving.config_saved', file=str(file_path)
            )
        )

    @classmethod
    def model_load_config(
            cls,
            file_name: PathStr,
            logger: Optional[Logger] = None,
            encoding: str = 'utf8',
            failure_policy: "Literal['regen', 'raise']" = 'regen',
    ):
        file_path = Path(file_name)
        requires_save = False
        if logger is None:
            logger = calyx_translator.logger

        if file_path.is_dir():
            file_path.rmdir()
        if not file_path.is_file():
            cfg_final = cls()
            cfg_final.model_save_config(
                file_path, logger=logger, encoding=encoding
            )
            logger.warning(
                calyx_translator.rtr('config.loading.file_not_found', file=str(file_path))
            )
            return cfg_final

        try:
            with open(file_name, 'r', encoding=encoding) as f:
                raw_data = YAML(typ='safe').load(f)
            try:
                cfg_final = cls.model_validate(raw_data)
            except ValidationError as exc:
                requires_save = True
                exc: ValidationError    # type: ignore
                # Yeet both pycharm and mypy warnings :<
                errors = TypeAdapter(
                    List[PydanticValidationErrorMessage]
                ).validate_python(
                    exc.errors()
                )
                default_dict = cls().model_dump()
                for e in errors:
                    default_value = get_value_from_nested_subscriptable_item(
                        default_dict, e.loc
                    )
                    if default_value is None:
                        raise KeyError(
                            f"Default value not found for key {'.'.join(e.loc)}"
                        )
                    fixed = set_value_to_nested_subscriptable_item(
                        raw_data, e.loc, default_value
                    )
                    if not fixed:
                        raise KeyError(
                            f"Config value not found for key {'.'.join(e.loc)}"
                        )
                    logger.warning(
                        calyx_translator.rtr(
                            "config.loading.item_fixed", key='.'.join(e.loc)
                        )
                    )
                cfg_final = cls.model_validate(raw_data)
        except Exception as exc:
            if failure_policy == 'raise':
                raise
            requires_save = True
            cfg_final = cls()
            logger.warning(calyx_translator.rtr('config.loading.yaml_syntax_error'))
            logger.debug(f"Error reason: {exc}")
        if requires_save:
            cfg_final.model_save_config(
                file_name, logger,
            )
        logger.info(calyx_translator.rtr('config.loading.config_loaded'))

        return cfg_final
