import threading

from contextlib import contextmanager
from typing import Callable, List, Optional, Union, Iterable
from typing_extensions import Self, override, Unpack

from mcdreforged.api.rtext import RTextBase, RStyle, RColor, RAction, RTextMCDRTranslation

from calyx_lib import utils
from calyx_lib.typing import TranslateFunc


class RTextBlossomTranslation(RTextBase):
    """
    The alternative translation text component out of MCDR for plugins

    When MCDR is running, it will use the :meth:`~mcdreforged.plugin.si.server_interface.ServerInterface.tr` method
    in :class:`~mcdreforged.plugin.si.server_interface.ServerInterface` class as the translating method,
    and the language of MCDR as the fallback translation language

    .. versionadded:: v2.1.0
    """

    __TLS = threading.local()
    __TLS.language = None

    def __init__(self, translation_key: str, *args, **kwargs):
        """
        Create a :class:`RTextBlossomTranslation` component
        with necessary parameters for translation

        :param translation_key: The translation key
        :param args: The translation arguments
        :param kwargs: The translation keyword arguments
        """
        def default_tr_func(key: str, *va, **kw) -> str:
            return str(key)

        self.translation_key: str = translation_key
        self.args = args
        self.kwargs = kwargs
        self.__tr_func: TranslateFunc = default_tr_func
        self.__post_process: List[Callable[[RTextBase], RTextBase]] = []
        self.__language_getter: Callable[[], str] = lambda: 'en_us'

    def set_translator(self, translate_function: TranslateFunc) -> 'Self':
        self.__tr_func = translate_function
        return self

    def set_language_getter(self, language_getter: Callable[[], str]):
        self.__language_getter = language_getter
        return self

    def get_language(self):
        return self.__language_getter()

    def __get_translated_text(self) -> RTextBase:
        language = getattr(self.__TLS, 'language', None)
        if language is None:
            language = self.get_language()
        processed_text = self.__tr_func(
            self.translation_key,
            *self.args,
            **self.kwargs,
            _mcdr_tr_language=language
        )
        processed_text = RTextBase.from_any(processed_text)
        for process in self.__post_process:
            processed_text = process(processed_text)
        return processed_text

    @classmethod
    @contextmanager
    def language_context(cls, language: str):
        """
        Create a context where all :class:`RTextBlossomTranslation`
        will use the given language to translate within

        It's mostly used when you want a translated str or Minecraft json text object
        corresponding to this component under a specific language

        MCDR will automatically apply this context with :ref:`user's
        preferred language <preference-language>`
        right before sending messages to a player or the console

        Example::

            def log_message_line_by_line(server: ServerInterface):
                with RTextMCDRTranslation.language_context('en_us'):
                    text: RTextMCDRTranslation = server.rtr('my_plugin.some_message')
                    # The translation operation happens here
                    text_as_str: str = text.to_plain_text()
                    server.logger.info('Lines of my translation')
                    for line in text_as_str.splitlines():
                        server.logger.info('- {}'.format(line))


        :param language: The language to be used during translation inside the context
        """
        prev = getattr(cls.__TLS, 'language', None)
        cls.__TLS.language = language
        try:
            yield
        finally:
            cls.__TLS.language = prev

    @override
    def to_json_object(self, **kwargs: Unpack[RTextBase.ToJsonKwargs]) -> Union[dict, list]:
        return self.__get_translated_text().to_json_object(**kwargs)

    @override
    def to_plain_text(self) -> str:
        return self.__get_translated_text().to_plain_text()

    @override
    def to_colored_text(self) -> str:
        return self.__get_translated_text().to_colored_text()

    @override
    def to_legacy_text(self) -> str:
        return self.__get_translated_text().to_legacy_text()

    @override
    def copy(self) -> 'Self':
        copied = self.__class__(self.translation_key, *self.args, **self.kwargs)
        copied.__tr_func = self.__tr_func
        copied.__post_process = self.__post_process.copy()
        return copied

    @override
    def set_color(self, color: RColor) -> Self:
        def add_color(rt: RTextBase):
            return rt.set_color(color)
        self.__post_process.append(add_color)
        return self

    @override
    def set_styles(self, styles: Union[RStyle, Iterable[RStyle]]) -> Self:
        def set_styles(rt: RTextBase):
            return rt.set_styles(styles)
        self.__post_process.append(set_styles)
        return self

    @override
    def set_click_event(self, action: RAction, value: str) -> Self:
        def set_click_event(rt: RTextBase):
            return rt.set_click_event(action, value)
        self.__post_process.append(set_click_event)
        return self

    @override
    def set_hover_text(self, *args) -> Self:
        def set_hover_text(rt: RTextBase):
            return rt.set_hover_text(*args)
        self.__post_process.append(set_hover_text)
        return self

    def __repr__(self) -> str:
        return utils.represent(self)
