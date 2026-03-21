from abc import ABC, abstractmethod
from datetime import datetime
from logging import Logger
from pathlib import Path
from typing import Optional, TYPE_CHECKING, Literal, Type, Iterable, List, Any, \
    TypeVar, Union

from mcdreforged.api.rtext import RTextBase, RColor, RTextMCDRTranslation
from mcdreforged.api.types import CommandSource, PlayerCommandSource, ConsoleCommandSource
from pydantic import BaseModel, ValidationError, TypeAdapter
from ruamel.yaml import YAML

from calyx_lib import constants
from calyx_lib.config.pydantic import PydanticValidationErrorMessage, \
    ConfigSerializationContext
from calyx_lib.config.yaml import any_to_yaml, ConfigComment, \
    CommentContext, CommentCarrier, adjust_comment_indentation
from calyx_lib.generic import MessageText, PathStr, Subscriptable, TranslationLanguageDict
from calyx_lib.translator import BlossomTranslator
from calyx_lib.utils import touch_directory
from calyx_lib.widgets.rtext_split import split_rtext

if TYPE_CHECKING:
    from typing import Dict


ModelType = TypeVar('ModelType', bound=BaseModel)


__all__ = ["BlossomBaseInterface"]


class BlossomBaseInterface(ABC):
    class __ConfigProcessLoggingHandler:
        def __init__(
                self,
                base: "BlossomBaseInterface",
                echo_in_console: bool,
                source_to_reply: Optional[CommandSource]
        ):
            self.base = base
            self.echo_in_console = echo_in_console
            self.source_to_reply: Optional[CommandSource]
            if isinstance(source_to_reply, CommandSource):
                self.source_to_reply = source_to_reply
            else:
                self.source_to_reply = None

        def info(self, msg: MessageText):
            if self.echo_in_console:
                self.base.logger.info(msg)
            if self.source_to_reply is not None:
                self.source_to_reply.reply(msg)

        def warning(self, msg: MessageText):
            if self.echo_in_console:
                self.base.logger.warning(msg)
            if self.source_to_reply is not None:
                msg = RTextBase.from_any(msg).set_color(RColor.yellow)
                self.source_to_reply.reply(msg)

    def __init__(self):
        self.translator = BlossomTranslator(self)
        for lang in ["zh_cn", "en_us"]:
            target_file_path = Path(constants.SELF_PACKAGE_PATH) / "lang" / f"{lang}.yml"
            if target_file_path.is_file():
                self.translator.register_translation_file(
                    target_file_path, encoding="utf8"
                )

    @property
    @abstractmethod
    def logger(self) -> Logger:
        """
        Logger of this interface
        Inherit this method to use your own custom logger
        :return: Logger
        """
        ...

    @abstractmethod
    def get_language(self):
        """
        Get language you currently configured
        When using MCDReforged, this should be the same as ServerInterface.get_mcdr_language()
        :return: str, Locale literal
        """
        ...

    def say(self, message: MessageText, *, encoding: Optional[str] = None):
        """
        Similar to `ServerInterface.say`
        In standalone programs, this will attach language context to RTextMCDRTranslation
        to avoid that the translation text can only be translated into `en_us`
        The difference is that this method splits the message by `\\n` and sends it,
        regardless of whether the message type is str or RTextBase.

        :param message: str or RTextBase
        :param encoding: encoding literal
        :return: No return
        """
        with RTextMCDRTranslation.language_context(self.get_language()):
            for line in split_rtext(RTextBase.from_any(message), divider='\n'):
                self.logger.info(line)

    def dtr(self, translation_dict: TranslationLanguageDict, *args, **kwargs):
        """
        Similar to `RTextMCDRTranslation.from_translation_dict()`
        But this use the individual translator of `BlossomBaseInterface`
        :param translation_dict: dict, language -> translated text
        :param args: The args to be formatted
        :param kwargs: The kwargs to be formatted
        :return: RTextMCDRTranslation
        """
        def fake_tr(
            translation_key: str,
            *inner_args,
            language: Optional[str] = None,
            _mcdr_tr_language: Optional[str] = None,
            _mcdr_tr_allow_failure: bool = True,
            _calyx_log_error_message: bool = True,
            _calyx_default_fallback: str = "<Translation failed>",
            **inner_kwargs,
        ) -> MessageText:
            language_order = self.translator.format_language_order(
                language=language, _mcdr_tr_language=_mcdr_tr_language)
            try:
                return self.translator.translate_from_dict(
                    translation_dict,
                    language_order,
                    *inner_args,
                    **inner_kwargs,
                )
            except Exception as e:
                lang_text = self.translator.format_language_text(language_order)
                error_message = (
                    f"Error translate text from dict to language {lang_text}: {str(e)}"
                )
                if _mcdr_tr_allow_failure:
                    if _calyx_log_error_message:
                        self.logger.error(error_message)
                    return _calyx_default_fallback
                else:
                    raise e

        return RTextMCDRTranslation("", *args, **kwargs).set_translator(fake_tr)  # ty:ignore[invalid-argument-type]

    def tr(
            self,
            translation_key: str,
            *args,
            language: Optional[str] = None,
            _mcdr_tr_language: Optional[str] = None,
            _mcdr_tr_allow_failure: bool = True,
            _calyx_default_fallback: Optional[MessageText] = None,
            _calyx_log_error_message: bool = True,
            **kwargs
    ) -> MessageText:
        """
        Similar to `ServerInterface.tr()`
        But this use the individual translator of `BlossomBaseInterface`

        Return a translated text corresponded to the translation key and format the text with given args and kwargs

        If args or kwargs contains :class:`RText <mcdreforged.minecraft.rtext.text.RTextBase>` element,
        then the result will be a :class:`RText <mcdreforged.minecraft.rtext.text.RTextBase>`,
        otherwise the result will be a regular str

        If the translation key is not recognized, the return value will be the translation key itself

        See :ref:`here <plugin-translation>` for the ways to register translations for your plugin


        :param translation_key: The key of the translation
        :param args: The args to be formatted
        :param language: The deprecated alias for `_mcdr_tr_language`, to keep the compatibility to some older MCDR extensions
        :param _mcdr_tr_language: Specific language to be used in this translation, or the language that MCDR is using will be used
        :param _mcdr_tr_allow_failure: `bool`, set it to `False` to raise an exception when it fails
        :param _calyx_default_fallback: Fallback text when it fails
        :param _calyx_log_error_message: `bool`, set it to `False` to make it silent when it fails
        :param kwargs: The kwargs to be formatted
        """
        target_lang = _mcdr_tr_language or language or self.get_language()
        return self.translator.translate(
            translation_key,
            *args,
            _mcdr_tr_language=target_lang,
            _mcdr_tr_allow_failure=_mcdr_tr_allow_failure,
            _calyx_default_fallback=_calyx_default_fallback,
            _calyx_log_error_message=_calyx_log_error_message,
            **kwargs
        )

    def rtr(
            self,
            translation_key: str,
            *args,
            _mcdr_tr_allow_failure: bool = True,
            _calyx_default_fallback: Optional[MessageText] = None,
            _calyx_log_error_message: bool = True,
            **kwargs
    ) -> "RTextMCDRTranslation":
        """
        Similar to `ServerInterface.rtr()`
        But this use the individual translator of `BlossomBaseInterface`

        Return a :class:`~mcdreforged.translation.translation_text.RTextMCDRTranslation` component,
        that only translates itself right before displaying or serializing

        Using this method instead of :meth:`tr` allows you to display your texts in :ref:`user's preferred language <preference-language>` automatically

        Of course, you can construct :class:`~mcdreforged.translation.translation_text.RTextMCDRTranslation` yourself instead of using this method if you want

        :param translation_key: The key of the translation
        :param args: The args to be formatted
        :param _mcdr_tr_allow_failure: `bool`, set it to `False` to raise an exception when it fails
        :param _calyx_default_fallback: Fallback text when it fails
        :param _calyx_log_error_message: `bool`, set it to `False` to make it silent when it fails
        :param kwargs: The kwargs to be formatted
        """
        return RTextMCDRTranslation(
            translation_key,
            *args,
            _mcdr_tr_allow_failure=_mcdr_tr_allow_failure,
            _calyx_default_fallback=_calyx_default_fallback,
            _calyx_log_error_message=_calyx_log_error_message,
            **kwargs,
        ).set_translator(self.tr)  # ty:ignore[invalid-argument-type]

    def __get_default_comment_context(self):
        def tr(
                translation_key: str,
                *args, **kwargs
        ):
            return self.tr(
                translation_key,
                *args,
                _calyx_default_fallback=translation_key,
                _calyx_log_error_message=False,
                **kwargs
            )
        headline = ConfigComment(
            text_getter=lambda: self.tr(
                'calyx_lib.config.saving.comments.saving_at',
                datetime.now().strftime(
                    str(self.tr('calyx_lib.general.format.datetime'))
                )
            ),
            priority=float('-inf'),
            ignore_global_wrapper=False,
        )

        return CommentContext(
            key_comments={}, global_wrapper=lambda x: x, headlines=[headline], eof=[]
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
            pydantic_model_dump_kwargs: Optional[dict] = None
    ):
        """
        A more advanced method to save your `pydantic.BaseModel` or `calyx_lib.config.CommentedModel` type config as a json file

        Supports attach the comment included in CommentedModel field annotations to the YAML files

        :param config: The config instance to be saved
        :param file_path: The name of the config file. It can also be a path to the config file
        :param encoding: The encoding method to write the config file. Default ``"utf8"``
        :param echo_in_console: Whether to echo saving log to console, `True` by default
        :param source_to_reply: Whether to echo saving log to command source, `None` by default
        :param failure_policy: The policy of handling a config loading error.
            ``"regen"`` (default): try to re-generate the config; ``"raise"``: directly raise the exception
        :param should_generate_comment: Whether to generate the comment, `True` by default.
            Comment in `CommentedModel` will be dumped into YAML file
        :param optional_context: Add additional comments with this context
        :param pydantic_model_dump_kwargs: Extra kwargs passed to the :meth:`pydantic.BaseModel.model_dump` method.
            Notes that the *mode* will always be set to ``"json"`` and the *exclude_none* will always be set to ``True``
            and context will be excluded from the dump.
        """
        log_handler = self.__ConfigProcessLoggingHandler(
            self, echo_in_console=echo_in_console, source_to_reply=source_to_reply
        )

        file_path = Path(file_path)
        if file_path.is_dir():
            file_path.rmdir()

        context = self.__get_default_comment_context()
        if should_generate_comment:
            context = optional_context or context
        if pydantic_model_dump_kwargs is None:
            pydantic_model_dump_kwargs = {}
        if 'context' in pydantic_model_dump_kwargs:
            pydantic_model_dump_kwargs.pop('context')
        if 'exclude_none' in pydantic_model_dump_kwargs:
            pydantic_model_dump_kwargs.pop('exclude_none')
        if 'mode' in pydantic_model_dump_kwargs:
            pydantic_model_dump_kwargs.pop('mode')
        try:
            serialized = config.model_dump(
                exclude_none=True,
                context=ConfigSerializationContext(
                    global_wrapper=context.global_wrapper
                ),
                mode='python',
                **pydantic_model_dump_kwargs
            )
        except Exception as exc:
            if failure_policy == 'raise':
                raise exc
            serialized = config.__class__().model_dump(
                exclude_none=True,
                context=ConfigSerializationContext(),
                mode='python',
                **pydantic_model_dump_kwargs
            )

        should_generate_comment = should_generate_comment and isinstance(
            serialized, CommentCarrier
        )
        if should_generate_comment:
            context.apply_comment_to_carrier(serialized)
        with open(file_path, mode='w', encoding=encoding) as f:
            if should_generate_comment:
                context.apply_comment_to_stream(context.headlines, f, self, None, None)
            f.write(adjust_comment_indentation(any_to_yaml(self, serialized)))
            if should_generate_comment:
                context.apply_comment_to_stream(context.eof, f, self, None, None)
        log_handler.info(
            self.rtr(
                'calyx_lib.config.saving.config_saved', file=str(file_path)
            )
        )

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
            pydantic_model_validate_kwargs: Optional[dict] = None,
            pydantic_model_dump_kwargs: Optional[dict] = None,
    ) -> ModelType:
        """
        A more advanced method to a :class:`pydantic.BaseModel` type config from a json file

        Default config is supported. Missing key-values in the loaded config object will be filled using the default config
        If anything is regenerated in config loading, the key will be marked with a line of comments

        :param file_path: The name of the config file. It can also be a path to the config file
        :param model_class: A class derived from :class:`pydantic.BaseModel`.
            When specified the loaded config data will be deserialized
        :param echo_in_console: If logging messages in console about config loading
        :param source_to_reply: The command source for replying logging messages
        :param encoding: The encoding method to read the config file. Default ``"utf8"``
        :param failure_policy: The policy of handling a config loading error.
            ``"regen"`` (default): try to re-generate the config; ``"raise"``: directly raise the exception
        :param should_generate_comment: Only when anything is going to be regenerated, this will take effect
            Whether to generate the comment, `True` by default.
            Comment in `CommentedModel` will be dumped into YAML file
        :param pydantic_model_dump_kwargs: Only when anything is going to be regenerated, this will take effect
            Extra kwargs passed to the :meth:`pydantic.BaseModel.model_dump` method.
            Notes that the *mode* will always be set to ``"json"`` and the *exclude_none* will always be set to ``True``
            and context will be excluded from the dump.
        :param pydantic_model_validate_kwargs: Extra kwargs passed to the :meth:`pydantic.BaseModel.model_validate` method.
            If not provided, ``{}`` will be used
        :return: Config instance in target model class
        """
        log_handler = self.__ConfigProcessLoggingHandler(
            self, echo_in_console=echo_in_console, source_to_reply=source_to_reply
        )
        file_path = Path(file_path)
        requires_save = False

        touch_directory(file_path.parent)
        if file_path.is_dir():
            file_path.rmdir()
        if not file_path.is_file():
            cfg_final = model_class()
            self.save_config(
                file_path, cfg_final,
                echo_in_console=echo_in_console,
                source_to_reply=source_to_reply,
                encoding=encoding,
                failure_policy=failure_policy,
                should_generate_comment=should_generate_comment
            )
            log_handler.warning(
                self.rtr('calyx_lib.config.loading.file_not_found', file=str(file_path))
            )
            return cfg_final

        default = model_class()
        default_dict_included_none = default.model_dump()
        default_dict_excluded_none = default.model_dump(exclude_none=True)

        comment_context = None
        if should_generate_comment:
            comment_context = self.__get_default_comment_context()

        try:
            with open(file_path, 'r', encoding=encoding) as f:
                raw_data = YAML(typ='safe').load(f)
            for k, v in default_dict_excluded_none.items():
                if k not in raw_data.keys():
                    raw_data[k] = v
                    log_handler.warning(
                        self.rtr('calyx_lib.config.loading.item_lost', key=k)
                    )
                    if comment_context is not None:
                        comment_context.add_comment(
                            (k, ),
                            ConfigComment(
                                text_getter=lambda: self.tr('calyx_lib.config.saving.comments.fixed_missing', key=k),
                                priority=float('-inf'),
                                ignore_global_wrapper=True
                            )
                        )
                    requires_save = True

            if pydantic_model_validate_kwargs is None:
                pydantic_model_validate_kwargs = {}

            try:
                cfg_final = model_class.model_validate(raw_data, **pydantic_model_validate_kwargs)
            except ValidationError as exc:
                requires_save = True
                errors = TypeAdapter(
                    List[PydanticValidationErrorMessage]
                ).validate_python(
                    exc.errors()
                )

                fixed = {}  # type: Dict[tuple, List[PydanticValidationErrorMessage]]

                def fix_nested_values(
                        error: PydanticValidationErrorMessage,
                        item: Subscriptable,
                        default_values: Subscriptable,
                        remaining: Iterable[Any],
                        consumed: Optional[List[Any]] = None,
                ) -> bool:
                    current_path = list(remaining)

                    if not current_path:
                        return True
                    current_index = current_path.pop(0)
                    consumed = consumed or []
                    try:
                        if isinstance(default_values, list):
                            current_default = default_values[0]
                        else:
                            current_default = default_values[current_index]
                    except:
                        return True
                    consumed.append(current_index)
                    try:
                        current_value = item[current_index]
                    except:
                        item[current_index] = current_default
                        return False
                    fix_this_layer = fix_nested_values(
                        error, current_value, current_default, current_path, consumed
                    )
                    path_tuple = tuple(consumed)
                    if fix_this_layer:
                        prev = item[current_index]
                        if path_tuple not in fixed:
                            item[current_index] = current_default
                        if fixed.get(path_tuple) is None:
                            fixed[path_tuple] = []
                        fixed[path_tuple].append(
                            error.model_copy(update={'input': prev})
                        )
                    return False

                self.logger.debug("  -- Pydantic validation errors -- ")
                for e in errors:
                    self.logger.debug(f'Error found at {".".join(str(i) for i in e.loc)}')
                    self.logger.debug(f'  Error message: {e.msg}')
                    self.logger.debug(f'  Type: {e.type}')
                    self.logger.debug(f'  Input value: {e.input}')
                    requires_fix = fix_nested_values(
                        e, raw_data, default_dict_included_none, e.loc
                    )
                    if requires_fix:
                        self.logger.debug(">> Error can't be fixed, regenerating... <<")
                        raise

                if comment_context is not None:
                    for k, error_list in fixed.items():
                        error_text = []
                        for e in error_list:
                            error_text.append('- ' + e.msg)
                        input_value = any_to_yaml(self, error_list[0].input)
                        if len(input_value.splitlines()) > 1:
                            input_value = '\n' + input_value
                        comment = ConfigComment(
                            lambda: self.rtr(
                                'calyx_lib.config.saving.comments.fixed_type_error',
                                key='.'.join([str(char) for char in k]),
                                errors='\n'.join(error_text),
                                value=input_value
                            ),
                            priority=float('-inf')
                        )
                        comment_context.add_comment(k, comment)

                for pt in fixed:
                    log_handler.warning(
                        self.rtr(
                            "calyx_lib.config.loading.type_fixed", key='.'.join(
                                [str(i) for i in pt]
                            )
                        )
                    )
                cfg_final = model_class.model_validate(raw_data)
        except Exception as e:
            if failure_policy == 'raise':
                raise
            requires_save = True
            cfg_final = model_class()
            log_handler.warning(self.rtr('calyx_lib.config.loading.yaml_syntax_error'))
            self.logger.debug(f"Error reason: {e}")
        if requires_save:
            self.save_config(
                file_path,
                cfg_final,
                echo_in_console=echo_in_console,
                source_to_reply=source_to_reply,
                encoding=encoding,
                failure_policy=failure_policy,
                should_generate_comment=should_generate_comment,
                optional_context=comment_context,
                pydantic_model_dump_kwargs=pydantic_model_dump_kwargs,
            )
        log_handler.info(self.rtr('calyx_lib.config.loading.config_loaded'))

        return cfg_final
