from pathlib import Path
from typing import Union, Callable, Any, Dict, Protocol

from mcdreforged.api.rtext import RTextBase
from mypy_extensions import VarArg, KwArg

PathStr = Union[str, Path]

MessageText = Union[str, RTextBase]
TranslateFunc = Callable[
    [str, VarArg(Any), KwArg(Any)], MessageText
]

# language -> text
TranslationLanguageDict = Dict[str, str]
# key -> text
TranslationKeyDict = Dict[str, str]
# key -> text/(key -> text/(...))
TranslationKeyDictNested = Dict[str, Union[str, 'TranslationKeyDictNested']]
# language -> text
TranslationKeyDictRich = Dict[str, MessageText]
# key -> (language -> text)
TranslationStorage = Dict[str, TranslationLanguageDict]


class Subscriptable(Protocol):
    def __getitem__(self, item) -> Any:
        pass

    def __setitem__(self, item, value) -> Any:
        pass


CommentTextWrapper = Callable[[MessageText], MessageText]
