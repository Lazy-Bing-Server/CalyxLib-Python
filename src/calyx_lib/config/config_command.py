from pydantic_core import PydanticSerializationError
import dataclasses
import weakref
from typing import TYPE_CHECKING, Dict, Iterable, Optional, Any, List, Annotated, Union, Callable
from pydantic import BaseModel, TypeAdapter, ValidationError, ConfigDict

from mcdreforged.api.command import QuotableText, CommandContext, ParseResult, CountingLiteral, GreedyText
from mcdreforged.api.types import CommandSource
from mcdreforged.api.rtext import RText, RColor, RStyle, RAction, RTextList

from calyx_lib.config.utils import get_value_from_nested_model, get_field_from_nested_model, set_value_to_nested_model
from calyx_lib.generic import MessageText
from calyx_lib.utils import adaptive_call

if TYPE_CHECKING:
    from typing import Self  # ty:ignore[unresolved-import]  Future features / Compatibility for Python 3.9
    from pydantic.fields import FieldInfo
    from calyx_lib.interface.blossom_base_interface import BlossomBaseInterface
    from calyx_lib.interface.impl.mcdr import BlossomMCDRInterface


"""
Make your plugin can be configured in game
"""

__all__ = [
    "InGameConfigItemMark",
    "ConfigKeyNode",
    "ConfigValueNode",
]


CONFIG_COMMAND_KEY = '_calyx_config_command'
CONFIG_VALUE = 'config_value'
TEMP_FLAG_KEY = '_calyx_temp_flag'
TEMP_FLAG = ['--temp', '-t']
SAVE_FLAG_KEY = '_calyx_save_flag'
SAVE_FLAG = ['--save', '-s']


def is_field_available_in_game(field: "FieldInfo") -> bool:
    for item in field.metadata:
        if isinstance(item, InGameConfigItemMark):
            return True
    return False



class ConfigKeyNode(QuotableText):
    def __init__(self, name, config: BaseModel, **kwargs):
        super().__init__(name, **kwargs)
        self.config = config
        self.__value_node: Optional[ConfigValueNode] = None

    @property
    def value_node(self) -> Optional["ConfigValueNode"]:
        return self.__value_node

    def parse(self, text: str) -> ParseResult:
        parsed = super().parse(text)
        return ParseResult(value=list(str(parsed.value).strip().split('.')), char_read=parsed.char_read)

    def _on_visited(self, context: CommandContext, parsed_result: ParseResult):
        context[CONFIG_COMMAND_KEY] = context.command_read
        return super()._on_visited(context, parsed_result)

    def __suggester(self, src: CommandSource, context: CommandContext) -> Iterable[str]:
        try:
            full_key = context.get(self.get_name())
            if not isinstance(full_key, list):
                full_key = []

            # Check if its father model exists
            father_model = get_value_from_nested_model(
                self.config, full_key[:-1], field_filter=InGameConfigItemMark.is_field_available_in_game
            )
            if len(full_key) > 0:
                # Check if current node exists
                current_exist = full_key[-1] in father_model.__class__.model_fields.keys()
                # Check if it requires suggesting the next layer
                if current_exist:
                    current_value = getattr(father_model, full_key[-1])
                    if isinstance(current_value, BaseModel):
                        father_model = current_value

            if not isinstance(father_model, BaseModel):
                return []

            fields: "Dict[str, FieldInfo]" = father_model.__class__.model_fields  # type: ignore
            filtered_fields = filter(
                lambda field_tuple: InGameConfigItemMark.is_field_available_in_game(field_tuple[1]),
                fields.items()
            )
            return map(lambda field_tuple: f".".join(full_key + [field_tuple[0]]), filtered_fields)
        except Exception as e:
            src.get_server().logger.exception(f"Failed to suggest command", exc_info=e)
            return []

    def __is_key_exists(self, src, context: CommandContext) -> bool:
        full_key = context[self.get_name()]
        return isinstance(full_key, list) and get_field_from_nested_model(
            self.config, full_key, field_filter=InGameConfigItemMark.is_field_available_in_game
        ) is not None

    def __invalid_key_msg_getter(self, base_interface: "BlossomMCDRInterface", src, ctx: CommandContext):
        full_key = '.'.join(ctx[self.get_name()])
        return base_interface.rtr("calyx_lib.config.in_game.invalid_key", full_key)

    def __show_config_key_description(
            self, source: CommandSource, context: CommandContext, base_interface: "BlossomMCDRInterface"
    ):
        full_key = context[self.get_name()]
        full_key_string = '.'.join(full_key)
        field = get_field_from_nested_model(self.config, full_key)
        father_model: BaseModel = get_value_from_nested_model(self.config, full_key[:-1])
        if field is None:
            # Although it's useless, invalid situation will be filtered in command parsing
            source.reply(
                base_interface.rtr("calyx_lib.config.in_game.invalid_key", full_key_string).set_color(RColor.red)
            )
            return
        in_game_mark_result = InGameConfigItemMark.get_instance_from_field(field)
        in_game_mark = in_game_mark_result or InGameConfigItemMark()
        title = adaptive_call(in_game_mark.item_display_name_getter, [base_interface, full_key, field], {})
        desc_line = adaptive_call(in_game_mark.item_description_getter, [base_interface, full_key, field], {})
        if isinstance(desc_line, str) and len(desc_line) == 0:
            desc_line = base_interface.rtr("calyx_lib.config.in_game.default_desc")

        suggested_values = in_game_mark.get_suggested_values(base_interface, full_key, field)
        current_value = father_model.model_dump(include={full_key[-1]}, mode='json')[full_key[-1]]

        father_cls = father_model.__class__
        default_value = father_cls().model_dump(include={full_key[-1]}, mode='json')[full_key[-1]]
        is_default_value = default_value == current_value

        color = RColor.green if is_default_value else RColor.yellow
        default_value_hint = base_interface.rtr('calyx_lib.config.in_game.default_value_hint', _mcdr_tr_allow_failure=False) \
            if is_default_value else base_interface.rtr('calyx_lib.config.in_game.modified_value_hint')
        default_value_hint.set_color(RColor.yellow).set_styles(RStyle.bold)
        current_value_text = RTextList(RText(current_value, color, RStyle.bold), ' ', default_value_hint)
        if context.get(CONFIG_VALUE) in suggested_values:
            suggested_values.remove(CONFIG_VALUE)
        suggested_values_text_list = list(map(
            lambda v: RText(v, RColor.gray, RStyle.underlined).c(
                RAction.run_command, context.command.strip() + f" {v}"
            ).h(
                base_interface.rtr("calyx_lib.config.in_game.suggested_value_hover", key=title, value=v)
            ),
            suggested_values
        ))[:in_game_mark.suggested_values_max_amount]
        suggested_values_text = RText.join(' ', suggested_values_text_list)
        value_line = RTextList(current_value_text, ' ', suggested_values_text)
        base_interface.reply(source, RTextList(title, '\n', desc_line, '\n', value_line))

    def bind_default_methods(
            self, base_interface: "BlossomMCDRInterface",
            config_path: str,
            save_config_by_default: bool = True,
            reload_plugin_after_save: bool = False,
            **additional_save_kwargs
    ):
        return self.suggests(
            self.__suggester
        ).requires(
            self.__is_key_exists,
            lambda src, ctx: self.__invalid_key_msg_getter(base_interface, src, ctx),
        ).then(
            CountingLiteral(TEMP_FLAG, TEMP_FLAG_KEY).redirects(self)
        ).then(
            CountingLiteral(SAVE_FLAG, SAVE_FLAG_KEY).redirects(self)
        ).then(
            ConfigValueNode(CONFIG_VALUE, self.config, self).bind_default_methods(
                base_interface, config_path,
                save_config_by_default=save_config_by_default,
                reload_plugin_after_save=reload_plugin_after_save,
                **additional_save_kwargs)
        ).runs(
            lambda src, ctx: self.__show_config_key_description(src, ctx, base_interface)
        )


class ConfigValueNode(GreedyText):
    def __init__(self, name, config: BaseModel, key_node: ConfigKeyNode, **kwargs):
        super().__init__(name, **kwargs)
        self.config = config
        self.__key_node: weakref.ref[ConfigKeyNode] = weakref.ref(key_node)

    @property
    def key_node(self) -> Optional[ConfigKeyNode]:
        return self.__key_node()

    def __get_keys(self, context: CommandContext) -> Optional[List[str]]:
        if self.key_node is None:
            return None
        return context[self.key_node.get_name()]

    def __get_value(self, context: CommandContext) -> Any:
        return context[self.get_name()]

    def __check_value(self, src, context: CommandContext):
        keys = self.__get_keys(context)
        if keys is None:
            return False
        target_field = get_field_from_nested_model(
            self.config, keys, field_filter=InGameConfigItemMark.is_field_available_in_game)
        if target_field is None:
            return False
        try:
            # Compatibility for lower python versions
            # target_type = Annotated[target_field.annotation, *target_field.metadata]
            target_type = target_field.annotation
            for item in target_field.metadata:
                target_type = Annotated[target_type, item]  # ty:ignore[invalid-type-form]
            TypeAdapter(target_type, config=ConfigDict(arbitrary_types_allowed=True)).validate_python(self.__get_value(context))
        except ValidationError:
            return False
        return True

    def __set_value(
            self,
            source: CommandSource,
            context: CommandContext,
            base_interface: "BlossomMCDRInterface",
            config_path: str,
            save_config_by_default: bool = True,
            reload_plugin_after_save: bool = False,
            **additional_save_kwargs
    ):
        full_key = self.__get_keys(context)
        if full_key is None:
            raise RuntimeError("Father node not set yet, is it a illegal call?")
        target_value = self.__get_value(context)
        is_a_temp_change = context.get(TEMP_FLAG_KEY, 0) > 0
        requires_save: bool = context.get(SAVE_FLAG_KEY, 0) > 0
        if is_a_temp_change and requires_save:
            # Although it's useless, invalid situation will be filtered in command parsing
            base_interface.reply(source, base_interface.rtr("calyx_lib.config.in_game.conflict_args").set_color(RColor.red))
        if context.get(TEMP_FLAG_KEY, 0) + context.get(SAVE_FLAG_KEY, 0) > 1:
            base_interface.reply(source, base_interface.rtr("calyx_lib.config.in_game.duplicated_args").set_color(RColor.yellow))

        father_model: BaseModel = get_value_from_nested_model(self.config, full_key[:-1])
        field = get_field_from_nested_model(self.config, full_key)
        requires_save = (requires_save or save_config_by_default) and not is_a_temp_change
        target_field = get_field_from_nested_model(
            father_model, [full_key[-1]], field_filter=InGameConfigItemMark.is_field_available_in_game)
        if target_field is None:
            source.reply(
                base_interface.rtr("calyx_lib.config.in_game.invalid_key", '.'.join(full_key)).set_color(RColor.red)
            )
            return

        current_value = father_model.model_dump(include={full_key[-1]}, mode='json')[full_key[-1]]
        in_game_mark = InGameConfigItemMark.get_instance_from_field(target_field)
        if in_game_mark is None:
            raise RuntimeError("In game mark must be ensured to be not none, is it a illegal call?")
        title = adaptive_call(in_game_mark.item_display_name_getter, [base_interface, full_key, field], {})
        try:
            succeeded = set_value_to_nested_model(self.config, full_key, target_value)
        except ValidationError:
            base_interface.reply(source, base_interface.rtr("calyx_lib.config.in_game.illegal_value").set_color(RColor.red))
            return

        if succeeded:
            command_header = get_clean_config_key_command(context)
            succeeded_text = base_interface.rtr("calyx_lib.config.in_game.value_set", key=title, value=target_value)
            if isinstance(command_header, str):
                succeeded_text += ' ' + base_interface.rtr("calyx_lib.config.in_game.undo_modify").c(
                    RAction.run_command, command_header.strip() + ' ' + str(current_value)
                ).h(
                    base_interface.rtr("calyx_lib.config.in_game.undo_hover", key=title, value=str(current_value))
                )
            base_interface.reply(source, succeeded_text)
        else:
            base_interface.reply(
                source, base_interface.rtr("calyx_lib.config.in_game.set_failed")
            )
            return

        if requires_save:
            base_interface.save_config(config_path, self.config, **additional_save_kwargs)
            base_interface.reply(
                source, base_interface.rtr("calyx_lib.config.in_game.config_saved")
            )
            if reload_plugin_after_save:
                base_interface.server.reload_plugin(base_interface.server.get_self_metadata().id)
        else:
            base_interface.reply(
                source, base_interface.rtr("calyx_lib.config.in_game.config_not_saved")
            )

    def __suggester(self, src, context: CommandContext, base_interface: "BlossomBaseInterface"):
        try:
            full_key = self.__get_keys(context)
            if not full_key:
                return []
            field = get_field_from_nested_model(self.config, full_key)
            if field is None:
                return []
            ingame_mark: Optional[InGameConfigItemMark] = InGameConfigItemMark.get_instance_from_field(field)
            if ingame_mark is None:
                return []
            items = ingame_mark.get_suggested_values(base_interface, full_key, field)
            for item in items.copy():
                # Filter non-string items, this would raise exceptions when suggesting
                if not isinstance(item, str):
                    items.remove(item)
            return items
        except Exception as e:
            base_interface.logger.exception("Unexpected suggest error", exc_info=e)

    def bind_default_methods(
            self,
            base_interface: "BlossomMCDRInterface",
            config_path: str,
            save_config_by_default: bool = True,
            reload_plugin_after_save: bool = False,
            **additional_save_kwargs
    ):
        return self.suggests(
            lambda src, ctx: self.__suggester(src, ctx, base_interface),
        ).requires(
            lambda src, ctx: not (ctx.get(SAVE_FLAG_KEY, 0) > 0 and ctx.get(TEMP_FLAG_KEY, 0) > 0),
            lambda: base_interface.rtr("calyx_lib.config.in_game.conflict_args"),
        ).requires(
            self.__check_value,
            lambda: base_interface.rtr("calyx_lib.config.in_game.illegal_value"),
        ).runs(
            lambda src, ctx: self.__set_value(
                src, ctx, base_interface, config_path,
                save_config_by_default=save_config_by_default,
                reload_plugin_after_save=reload_plugin_after_save,
                **additional_save_kwargs
            )
        )


@dataclasses.dataclass
class InGameConfigItemMark:
    item_display_name_getter: Union[
        Callable[["BlossomBaseInterface", List[str], "FieldInfo"], MessageText],
        Callable[["BlossomBaseInterface", List[str]], MessageText],
        Callable[["BlossomBaseInterface"], MessageText],
        Callable[[], MessageText],
    ] = lambda _, x: '.'.join(x),  # ty:ignore[invalid-assignment]
    item_description_getter: Union[
        Callable[["BlossomBaseInterface", List[str], "FieldInfo"], MessageText],
        Callable[["BlossomBaseInterface", List[str]], MessageText],
        Callable[["BlossomBaseInterface"], MessageText],
        Callable[[], MessageText],
    ] = lambda: ""
    value_suggester: Union[
        Callable[["BlossomBaseInterface", List[str], "FieldInfo"], Iterable[Any]],
        Callable[["BlossomBaseInterface", List[str]], Iterable[Any]],
        Callable[["BlossomBaseInterface"], Iterable[Any]],
        Callable[[], Iterable[Any]],
    ] = lambda: []
    suggested_values_max_amount: int = 3

    @classmethod
    def is_field_available_in_game(cls, field: "FieldInfo") -> bool:
       return cls.get_instance_from_field(field) is not None

    @classmethod
    def get_instance_from_field(cls, field: "FieldInfo") -> Optional["Self"]:
        for item in field.metadata:
            if isinstance(item, cls):
                return item
        return None

    def get_suggested_values(self, base_interface: "BlossomBaseInterface", full_key: List[str], field: "FieldInfo") -> List[Any]:
        suggested_values = list(adaptive_call(self.value_suggester, [base_interface, full_key, field], {}))
        result = []
        for value in suggested_values:
            try:
                result.append(get_type_adapter_from_field(field).dump_python(value, mode='json'))
            except PydanticSerializationError:
                continue
        return result


def get_type_adapter_from_field(field: "FieldInfo") -> TypeAdapter:
    target_type = field.annotation
    for type_ in field.metadata:
        target_type = Annotated[target_type, type_]  # ty:ignore[invalid-type-form]
    return TypeAdapter(target_type, config=ConfigDict(arbitrary_types_allowed=True))


def get_clean_config_key_command(context: CommandContext):
    return context.get(CONFIG_COMMAND_KEY)
