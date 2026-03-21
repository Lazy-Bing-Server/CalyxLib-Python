from optparse import Option
from mcdreforged.plugin.plugin_event import MCDREvent
from pathlib import Path
import re
from logging import Logger
from typing import List, Optional, Union, Type, Literal, Callable, Tuple
from pydantic import BaseModel

from mcdreforged import RTextMCDRTranslation, PlayerCommandSource, ConsoleCommandSource, Info
from mcdreforged.api.types import CommandSource
from mcdreforged.api.types import PluginServerInterface
from mcdreforged.api.rtext import RText, RAction, RTextBase
from mcdreforged.api.event import MCDRPluginEvents

from calyx_lib.config import CommentContext
from calyx_lib.interface.blossom_base_interface import BlossomBaseInterface, ModelType
from calyx_lib.logger import BlossomLogger
from calyx_lib.generic import MessageText, PathStr
from calyx_lib.widgets.rtext_split import split_rtext

__all__ = ["BlossomMCDRInterface"]


class BlossomMCDRInterface(BlossomBaseInterface):
    def __init__(self):
        self.__server = PluginServerInterface.psi_opt()
        self.__temp_logger = BlossomLogger("MCDR")._set_temp()
        self.__logger_warning_flag = False
        super().__init__()
        if self.__server is not None:
            self.__register_default_translations()
            self.__server.register_event_listener(MCDRPluginEvents.PLUGIN_LOADED, self.__on_load)

    @property
    def server(self):
        """
        `PluginServerInterface` instance
        raises `RuntimeError` when the instance is not initialized in single file plugin
        :return: `PluginServerInterface`
        """
        if self.__server is None:
            raise RuntimeError("BlossomMCDRInterface is not initialized")
        return self.__server

    @property
    def logger(self) -> Logger:
        if self.server is None:
            return self.__temp_logger
        return self.server.logger

    def get_language(self) -> str:
        if self.server is None:
            return 'en_us'
        return self.server.get_mcdr_language()

    def htr(
            self,
            translation_key: str,
            *args,
            prefixes: Optional[List[str]] = None,
            suggest_prefix: Optional[str] = None,
            add_meta_as_format_param: bool = True,
            **kwargs,
    ):
        """
        Translate method for help message
        This method will attach click event to lines starts with the pattern like`§7{prefix} ...§r`
        :param translation_key: Translation key
        :param args: Format args
        :param prefixes: Prefixes to detect in the translated texts
        :param suggest_prefix: Prefix used in suggested commands
        :param add_meta_as_format_param: `bool`, whether to add plugin metadata as formatting kwargs
        :param kwargs: Additional format kwargs
        :return:
        """
        prefixes = prefixes or [""]

        def __get_regex_result(line: str):
            pattern = r"(?<=§7){}[\S ]*?(?=§)"
            for prefix in prefixes:
                result = re.search(pattern.format(prefix), line)
                if result is not None:
                    return result
            return None

        def __htr(key: str, *inner_args, **inner_kwargs) -> MessageText:
            nonlocal suggest_prefix
            original = self.tr(key, *inner_args, **inner_kwargs)
            processed: List[MessageText] = []
            if not isinstance(original, str):
                return key
            for line in original.splitlines():
                result = __get_regex_result(line)
                if result is not None:
                    command = result.group().strip() + " "
                    if suggest_prefix is not None:
                        command = suggest_prefix.strip() + " " + command
                    elif prefixes is not None:
                        command = prefixes[0].strip() + " " + command
                    processed.append(
                        RText(line)
                        .c(RAction.suggest_command, command)
                        .h(self.rtr("calyx_lib.help_message.suggest", command))
                    )

                    self.logger.debug(f'Rich help line: "{line}"')
                    self.logger.debug(
                        "Suggest prefix: {}".format(
                            f'"{suggest_prefix}"'
                            if isinstance(suggest_prefix, str)
                            else suggest_prefix
                        )
                    )
                    self.logger.debug(f'Suggest command: "{command}"')
                else:
                    processed.append(line)
            return RTextBase.join("\n", processed)

        if add_meta_as_format_param:
            meta = self.server.get_self_metadata().to_dict()
            for k, v in meta.items():
                if k not in kwargs:
                    kwargs[k] = v
        return self.rtr(translation_key, *args, **kwargs).set_translator(__htr)

    def reply(self, source: Union[CommandSource, str], message: MessageText, *, encoding: Optional[str] = None):
        """
        Similar to `ServerInterface.reply()` or `CommandSource.reply()`
        The difference is that this method splits the message by `\\n` and sends it,
        regardless of whether the message type is str or RTextBase.

        :param source: CommandSource or str
        :param message: str or RTextBase
        :param encoding: encoding literal
        :return: No return
        """
        if isinstance(source, (PlayerCommandSource, ConsoleCommandSource, str)):
            lang: str = self.server.get_preference(source).language
        else:
            lang = self.get_language()
        with RTextMCDRTranslation.language_context(lang):
            for line in split_rtext(RTextBase.from_any(message), divider='\n'):
                if isinstance(source, CommandSource):
                    source.reply(line, encoding=encoding)
                elif isinstance(source, str):
                    self.server.tell(source, line, encoding=encoding)

    def broadcast(self, message: MessageText, *, encoding: Optional[str] = None):
        """
        Similar to `ServerInterface.broadcast`
        The difference is that this method splits the message by `\\n` and sends it,
        regardless of whether the message type is str or RTextBase.

        :param message: str or RTextBase
        :param encoding: encoding literal
        :return: No return
        """
        with RTextMCDRTranslation.language_context(self.get_language()):
            for line in split_rtext(RTextBase.from_any(message), divider='\n'):
                self.server.say(line, encoding=encoding)
                self.logger.info(line)

    def say(self, message: MessageText, *, encoding: Optional[str] = None):
        """
        Similar to `ServerInterface.say`
        The difference is that this method splits the message by `\\n` and sends it,
        regardless of whether the message type is str or RTextBase.

        :param message: str or RTextBase
        :param encoding: encoding literal
        :return: No return
        """
        with RTextMCDRTranslation.language_context(self.get_language()):
            for line in split_rtext(RTextBase.from_any(message), divider='\n'):
                self.server.say(line, encoding=encoding)

    def __register_default_translations(self):
        self_path = self.server.get_plugin_file_path(self.server.get_self_metadata().id)
        if self_path is not None:
            self.translator.register_bundled_translations(self_path, 'lang')

    def __on_load(self, server: PluginServerInterface, prev_module):
        self.bind_server(server)
        self.on_load(server, prev_module)

    def bind_server(self, server: PluginServerInterface):
        """
        This should be executed manually when `mcdr.plugin_loaded` event dispatched
        if creating BlossomMCDRInterface in a single file plugin
        or the interface instance will work incorrectly.

        :param server: PluginServerInterface
        :return: No return
        """
        if self.server is None:
            self.__server = server
            self.__register_default_translations()
        self.__register_event_listeners()

    def __register_event_listeners(self):
        events: List[Tuple[MCDREvent, Callable]] = [
            # Except PLUGIN_LOADED, self.on_load(), already registered this time
            (MCDRPluginEvents.PLUGIN_UNLOADED, self.on_unload),
            (MCDRPluginEvents.GENERAL_INFO, self.on_info),
            (MCDRPluginEvents.USER_INFO, self.on_user_info),
            (MCDRPluginEvents.SERVER_START_PRE, self.on_server_start_pre),
            (MCDRPluginEvents.SERVER_START, self.on_server_start),
            (MCDRPluginEvents.SERVER_STARTUP, self.on_server_startup),
            (MCDRPluginEvents.SERVER_STOP, self.on_server_stop),
            (MCDRPluginEvents.MCDR_START, self.on_mcdr_start),
            (MCDRPluginEvents.MCDR_STOP, self.on_mcdr_stop),
            (MCDRPluginEvents.PLAYER_JOINED, self.on_player_joined),
            (MCDRPluginEvents.PLAYER_LEFT, self.on_player_left)
        ]
        for event, callback in events:
            self.server.register_event_listener(event, callback)

    def on_load(self, server: PluginServerInterface, prev_module):
        """
        Inherit this message to register `mcdr.plugin_loaded`
        Almost the same as `on_load()` function in plugin entrypoint, but typed
        :param server: PluginServerInterface
        :param prev_module: Any, previous module
        :return: Doesn't have to return anything
        """
        pass

    def on_unload(self, server: PluginServerInterface):
        """
        Inherit this message to register `mcdr.plugin_unloaded`
        Almost the same as `on_unload()` function in plugin entrypoint, but typed
        :param server: PluginServerInterface
        :return: Doesn't have to return anything
        """
        pass

    def on_info(self, server: PluginServerInterface, info: Info):
        """
        Inherit this message to register `mcdr.general_info`
        Almost the same as `on_info()` function in plugin entrypoint, but typed
        :param server: PluginServerInterface
        :param info: Info
        :return: Doesn't have to return anything
        """
        pass

    def on_user_info(self, server: PluginServerInterface, info: Info):
        """
        Inherit this message to register `mcdr.user_info`
        Almost the same as `on_user_info()` function in plugin entrypoint, but typed
        :param server: PluginServerInterface
        :param info: Info
        :return: Doesn't have to return anything
        """
        pass

    def on_server_start_pre(self, server: PluginServerInterface):
        """
        Inherit this message to register `mcdr.server_start_pre`
        Almost the same as `on_server_start_pre()` function in plugin entrypoint, but typed
        :param server: PluginServerInterface
        :return: Doesn't have to return anything
        """
        pass

    def on_server_start(self, server: PluginServerInterface):
        """
        Inherit this message to register `mcdr.server_start`
        Almost the same as `on_server_start()` function in plugin entrypoint, but typed
        :param server: PluginServerInterface
        :return: Doesn't have to return anything
        """
        pass

    def on_server_startup(self, server: PluginServerInterface):
        """
        Inherit this message to register `mcdr.server_startup`
        Almost the same as `on_server_startup()` function in plugin entrypoint, but typed
        :param server: PluginServerInterface
        :return: Doesn't have to return anything
        """
        pass

    def on_server_stop(self, server: PluginServerInterface, server_return_code: int):
        """
        Inherit this message to register `mcdr.server_stop`
        Almost the same as `on_server_stop()` function in plugin entrypoint, but typed
        :param server: PluginServerInterface
        :return: Doesn't have to return anything
        """
        pass

    def on_mcdr_start(self, server: PluginServerInterface):
        """
        Inherit this message to register `mcdr.mcdr_start`
        Almost the same as `on_mcdr_start()` function in plugin entrypoint, but typed
        :param server: PluginServerInterface
        :return: Doesn't have to return anything
        """
        pass

    def on_mcdr_stop(self, server: PluginServerInterface):
        """
        Inherit this message to register `mcdr.mcdr_stop`
        Almost the same as `on_mcdr_stop()` function in plugin entrypoint, but typed
        :param server: PluginServerInterface
        :return: Doesn't have to return anything
        """
        pass

    def on_player_joined(self, server: PluginServerInterface, player: str, info: Info):
        """
        Inherit this message to register `mcdr.player_joined`
        Almost the same as `on_player_joined()` function in plugin entrypoint, but typed
        :param server: `PluginServerInterface`
        :param player: `str`, Player id
        :param info: `Info`
        :return: `Any`, Doesn't have to return anything
        """
        pass

    def on_player_left(self, server: PluginServerInterface, player: str):
        """
        Inherit this message to register `mcdr.player_left`
        Almost the same as `on_player_left()` function in plugin entrypoint, but typed
        :param server: `PluginServerInterface`
        :param player: `str`, Player id
        :return: `Any`, Doesn't have to return anything
        """
        pass

    def load_config(
            self,
            file_path: PathStr,
            model_class: Type[ModelType],
            *,
            echo_in_console: bool = True,
            source_to_reply: Optional[CommandSource] = None,
            encoding: str = "utf8",
            failure_policy: Literal['regen', 'raise'] = "regen",
            should_generate_comment: bool = True,
            in_data_folder: bool = True,
            pydantic_model_validate_kwargs: Optional[dict] = None,
            pydantic_model_dump_kwargs: Optional[dict] = None,
    ) -> ModelType:
        if in_data_folder and not Path(file_path).is_absolute():
            file_path = (Path(self.server.get_data_folder()) / file_path).resolve()
        return super().load_config(
            file_path, model_class,
            echo_in_console=echo_in_console,
            source_to_reply=source_to_reply,
            encoding=encoding,
            failure_policy=failure_policy,
            should_generate_comment=should_generate_comment,
            pydantic_model_validate_kwargs=pydantic_model_validate_kwargs,
            pydantic_model_dump_kwargs=pydantic_model_dump_kwargs,
        )

    def save_config(
            self,
            file_path: PathStr,
            config: BaseModel,
            *,
            echo_in_console: bool = True,
            source_to_reply: Optional[CommandSource] = None,
            failure_policy: "Literal['regen', 'raise']" = 'regen',
            encoding: str = 'utf8',
            should_generate_comment: bool = True,
            optional_context: Optional[CommentContext] = None,
            in_data_folder: bool = True,
            pydantic_model_dump_kwargs: Optional[dict] = None
    ):
        if in_data_folder and not Path(file_path).is_absolute():
            file_path = Path(self.server.get_data_folder()) / file_path
        return super().save_config(
            file_path, config,
            echo_in_console=echo_in_console,
            source_to_reply=source_to_reply,
            failure_policy=failure_policy,
            encoding=encoding,
            should_generate_comment=should_generate_comment,
            optional_context=optional_context,
            pydantic_model_dump_kwargs=pydantic_model_dump_kwargs
        )
