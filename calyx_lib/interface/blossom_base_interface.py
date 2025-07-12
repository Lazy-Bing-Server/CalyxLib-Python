from abc import ABC, abstractmethod
from datetime import datetime
from logging import Logger
from pathlib import Path
from typing import Optional, Union, TYPE_CHECKING, Literal, Type, Iterable, List, Any, \
    TypeVar

from mcdreforged.api.rtext import RTextBase, RColor
from mcdreforged.api.types import CommandSource
from pydantic import BaseModel, ValidationError, TypeAdapter
from ruamel.yaml import YAML

from calyx_lib import constants
from calyx_lib.config.pydantic import PydanticValidationErrorMessage, \
    ConfigSerializationContext
from calyx_lib.config.yaml import any_to_yaml, ConfigComment, \
    CommentContext, CommentCarrier, adjust_comment_indentation
from calyx_lib.translation.text import RTextBlossomTranslation
from calyx_lib.translation.translator import BlossomTranslator
from calyx_lib.typing import MessageText, PathStr, Subscriptable, TranslationKeyDictRich
from calyx_lib.utils import touch_directory

if TYPE_CHECKING:
    from mcdreforged.api.rtext import RTextMCDRTranslation
    from typing import Dict


ModelType = TypeVar('ModelType', bound=BaseModel)


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
        self.logger = self.get_logger()
        self.translator = BlossomTranslator(self)
        for lang in ["zh_cn", "en_us"]:
            target_file_path = Path(constants.SELF_PACKAGE_PATH) / "lang" / f"{lang}.yml"
            if target_file_path.is_file():
                self.translator.register_translation_file(
                    target_file_path, encoding="utf8"
                )

    @abstractmethod
    def get_logger(self) -> Logger:
        ...

    @abstractmethod
    def get_language(self):
        ...

    def dtr(self, translation_dict: TranslationKeyDictRich, *args, **kwargs):
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
            if language is not None and _mcdr_tr_language is None:
                _mcdr_tr_language = language
            try:
                return self.translator.translate_from_dict(
                    translation_dict,
                    *inner_args,
                    _mcdr_tr_language=_mcdr_tr_language,
                    **inner_kwargs,
                )
            except Exception as e:
                lang_text = ", ".join(
                    [f'"{lang}"' for lang in self.translator.fallback_language_order]
                )
                error_message = (
                    f"Error translate text from dict to language {lang_text}: {str(e)}"
                )
                if _mcdr_tr_allow_failure:
                    if _calyx_log_error_message:
                        self.logger.error(error_message)
                    return _calyx_default_fallback
                else:
                    raise e

        return RTextBlossomTranslation(
            "", *args, **kwargs
        ).set_translator(fake_tr).set_language_getter(self.get_language)

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
    ) -> Union["RTextMCDRTranslation", "RTextBlossomTranslation"]:
        return RTextBlossomTranslation(
            translation_key,
            *args,
            _mcdr_tr_allow_failure=_mcdr_tr_allow_failure,
            _calyx_default_fallback=_calyx_default_fallback,
            _calyx_log_error_message=_calyx_log_error_message,
            **kwargs,
        ).set_language_getter(self.get_language).set_translator(self.tr)

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
            text=self.tr(
                'config.saving.comments.saving_at',
                datetime.now().strftime(
                    str(self.tr('general.format.datetime'))
                )
            ),
            priority=float('-inf'),
            ignore_global_wrapper=False,
        )

        return CommentContext(
            key_comments={}, global_wrapper=tr, headlines=[headline], eof=[]
        )

    def save_config(
            self,
            file_name: PathStr,
            config: BaseModel,
            echo_in_console: bool = True,
            source_to_reply: Optional[CommandSource] = None,
            failure_policy: "Literal['regen', 'raise']" = 'regen',
            encoding: str = 'utf8',
            should_generate_comment: bool = True,
            optional_context: Optional[CommentContext] = None
    ):
        log_handler = self.__ConfigProcessLoggingHandler(
            self, echo_in_console=echo_in_console, source_to_reply=source_to_reply
        )

        file_path = Path(file_name)
        if file_path.is_dir():
            file_path.rmdir()

        context = self.__get_default_comment_context()
        if should_generate_comment:
            context = optional_context or context
        try:
            serialized = config.model_dump(
                exclude_none=True,
                context=ConfigSerializationContext(
                    global_wrapper=context.global_wrapper
                )
            )
        except Exception as exc:
            if failure_policy == 'raise':
                raise exc
            serialized = config.__class__().model_dump(
                exclude_none=True,
                context=ConfigSerializationContext()
            )

        should_generate_comment = should_generate_comment and isinstance(
            serialized, CommentCarrier
        )
        if should_generate_comment:
            context.apply_comment_to_carrier(serialized)
        with open(file_path, mode='w', encoding=encoding) as f:
            if should_generate_comment:
                context.apply_comment_to_stream(context.headlines, f)
            f.write(adjust_comment_indentation(any_to_yaml(serialized)))
            if should_generate_comment:
                context.apply_comment_to_stream(context.eof, f)
        log_handler.info(
            self.rtr(
                'config.saving.config_saved', file=str(file_path)
            )
        )

    def load_config(
            self,
            file_path: PathStr,
            model_class: Type[ModelType],
            echo_in_console: bool = True,
            source_to_reply: Optional[CommandSource] = None,
            encoding: str = "utf8",
            failure_policy: Literal['regen', 'raise'] = "regen",
            should_generate_comment: bool = True,
    ) -> ModelType:
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
                self.rtr('config.loading.file_not_found', file=str(file_path))
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
                        self.rtr('config.loading.item_lost', key=k)
                    )
                    if comment_context is not None:
                        comment_context.add_comment(
                            (k, ),
                            ConfigComment(
                                self.tr('config.saving.comments.fixed_missing', key=k),
                                priority=float('-inf'),
                                ignore_global_wrapper=True
                            )
                        )
                    requires_save = True

            try:
                cfg_final = model_class.model_validate(raw_data)
            except ValidationError as exc:
                requires_save = True
                exc: ValidationError    # type: ignore
                # Yeet both pycharm and mypy warnings :<
                errors = TypeAdapter(
                    List[PydanticValidationErrorMessage]
                ).validate_python(
                    exc.errors()
                )

                fixed = {}  # type: Dict[tuple, List[PydanticValidationErrorMessage]]

                def fix_nested_values(
                        error: PydanticValidationErrorMessage,
                        item: Subscriptable,
                        default: Subscriptable,
                        remaining: Iterable[Any],
                        consumed: Optional[List[Any]] = None,
                ) -> bool:
                    current_path = list(remaining)

                    if not current_path:
                        return True
                    current_index = current_path.pop(0)
                    consumed = consumed or []
                    try:
                        if isinstance(default, list):
                            current_default = default[0]
                        else:
                            current_default = default[current_index]
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
                        input_value = any_to_yaml(error_list[0].input)
                        if len(input_value.splitlines()) > 1:
                            input_value = '\n' + input_value
                        comment = ConfigComment(
                            self.rtr(
                                'config.saving.comments.fixed_type_error',
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
                            "config.loading.type_fixed", key='.'.join(
                                [str(i) for i in pt]
                            )
                        )
                    )
                cfg_final = model_class.model_validate(raw_data)
        except Exception as exc:
            if failure_policy == 'raise':
                raise
            requires_save = True
            cfg_final = model_class()
            log_handler.warning(self.rtr('config.loading.yaml_syntax_error'))
            self.logger.debug(f"Error reason: {exc}")
        if requires_save:
            self.save_config(
                file_path,
                cfg_final,
                echo_in_console=echo_in_console,
                source_to_reply=source_to_reply,
                encoding=encoding,
                failure_policy=failure_policy,
                should_generate_comment=should_generate_comment,
                optional_context=comment_context
            )
        log_handler.info(self.rtr('config.loading.config_loaded'))

        return cfg_final
