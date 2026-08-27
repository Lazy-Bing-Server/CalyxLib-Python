import json
import os
from logging import Logger
from pathlib import Path
from threading import RLock
from typing import Optional, List, Callable, Any, TYPE_CHECKING
from zipfile import ZipFile

from mcdreforged.api.rtext import RTextBase
from ruamel.yaml import YAML

from calyx_lib.utils import list_bundled_file
from calyx_lib.generic import (
    PathStr,
    MessageText,
    TranslationKeyDictNested,
    TranslationKeyDict,
    TranslationLanguageDict,
    TranslationStorage
)

if TYPE_CHECKING:
    from calyx_lib.interface.blossom_base_interface import BlossomBaseInterface

_NONE = object()
FALLBACK_LANGUAGE_ORDER = ['en_us']

__all__ = [
    "BlossomTranslator"
]


class BlossomTranslator:
    yaml = YAML(typ='safe')

    def __init__(self, base_interface: "BlossomBaseInterface"):
        self.__base_interface = base_interface
        self.__storage: TranslationStorage = {}
        self.__lock = RLock()

    @property
    def logger(self) -> Logger:
        return self.__base_interface.logger

    @property
    def available(self) -> bool:
        return len(self.__storage) != 0

    def register_translation(
            self, translation_dict: TranslationKeyDictNested, language: str
    ):
        def get_full_key_value_map(
                target_dict: TranslationKeyDictNested,
                result_dict: Optional[TranslationKeyDict] = None,
                current_layer: Optional[List[str]] = None
        ):
            if current_layer is None:
                current_layer = []
            if result_dict is None:
                result_dict = {}
            for k, v in target_dict.items():
                this_layer = current_layer.copy()
                this_layer.append(k)
                if isinstance(v, dict):
                    get_full_key_value_map(
                        v, result_dict=result_dict, current_layer=this_layer
                    )
                else:
                    result_dict['.'.join(this_layer)] = str(v)
            return result_dict

        translation_dict = get_full_key_value_map(translation_dict)
        for key, value in translation_dict.items():
            if (
                    key not in self.__storage.keys()
                    or
                    not isinstance(self.__storage[key], dict)
            ):
                self.__storage[key] = {}
            self.__storage[key][language] = value  # type: ignore

    def register_translation_file(
            self,
            file_path: PathStr,
            bundle_path: Optional[PathStr] = None,
            error_handler: Optional[Callable[[Exception], Any]] = None,
            encoding: str = 'utf8'
    ) -> bool:
        file_name = os.path.basename(file_path)
        if '.' not in list(file_name):
            return False
        language, file_extension = file_name.rsplit('.', 1)
        if file_extension in ['json', 'yml', 'yaml']:
            try:
                if bundle_path is not None:
                    with ZipFile(bundle_path).open(str(file_path)) as file:
                        text = file.read().decode(encoding=encoding)
                else:
                    with open(file_path, 'r', encoding=encoding) as f:
                        text = f.read()
                if file_extension == 'json':
                    translation_dict = json.loads(text)
                else:
                    translation_dict = self.yaml.load(text)
                if isinstance(translation_dict, dict):
                    self.register_translation(translation_dict, language)
                return True
            except Exception as e:
                if error_handler is not None:
                    error_handler(e)
        return False

    def register_bundled_translations(self, package: PathStr, target_folder: PathStr):
        package_path = Path(package)
        target_folder_path = Path(target_folder)
        for file_name in list_bundled_file(package_path, target_folder_path):
            if package_path.is_dir():
                translation_file_path = package_path / target_folder_path / file_name
                registered = self.register_translation_file(translation_file_path)
            else:
                registered = self.register_translation_file(
                    target_folder_path / file_name, package_path
                )
            if not registered:
                self.logger.debug(
                    'Skipping unknown translation file {} in {}'.format(
                        file_name, repr(self))
                )

    def has_translation(self, translation_key: str, language: str):
        trans = self.__storage.get(translation_key)
        if isinstance(trans, dict):
            return language in trans.keys()
        return False

    @staticmethod
    def translate_from_dict(
            translation_dict: TranslationLanguageDict, language_order: List[str], *args, **kwargs
    ):
        translated_raw_text = _NONE
        for lang in language_order:
            translated_raw_text = translation_dict.get(lang, _NONE)
            if translated_raw_text is not _NONE:
                break
        # Allow null value in translation files
        if translated_raw_text is None:
            translated_formatter = ''
        elif isinstance(translated_raw_text, str):
            translated_formatter = translated_raw_text
        elif translated_raw_text is _NONE:
            raise KeyError("Translation key does not exist")
        else:
            raise TypeError("Unexpected type found in translation storage")

        use_rtext = any(
            [isinstance(e, RTextBase) for e in list(args) + list(kwargs.values())]
        )
        try:
            if use_rtext:
                return RTextBase.format(translated_formatter, *args, **kwargs)
            else:
                return translated_formatter.format(*args, **kwargs)
        except Exception as e:
            raise ValueError(f'Failed to apply args {args} and kwargs {kwargs} '
                             f'to translated_text {translated_raw_text}: {str(e)}')

    @staticmethod
    def format_language_order(language: Optional[str] = None, _mcdr_tr_language: Optional[str] = None) -> List[str]:
        _mcdr_tr_language = _mcdr_tr_language or language
        language_order = FALLBACK_LANGUAGE_ORDER.copy()
        if _mcdr_tr_language is not None and _mcdr_tr_language not in language_order:
            language_order = [_mcdr_tr_language] + language_order
        return language_order

    @staticmethod
    def format_language_text(language_order: List[str]):
        return ', '.join([f'"{lang}"' for lang in language_order])

    def translate(
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
        if not self.available:
            raise RuntimeError('Illegal translate request before translation loading')
        language_order = self.format_language_order(language=language, _mcdr_tr_language=_mcdr_tr_language)
        _calyx_default_fallback = _calyx_default_fallback or translation_key
        translation_dict = self.__storage.get(translation_key, {})

        try:
            if _mcdr_tr_language is None:
                raise ValueError("Language not specified")
            return self.translate_from_dict(translation_dict, language_order, *args, **kwargs)
        except Exception as e:
            lang_text = self.format_language_text(language_order)
            error_message = 'Error translate text "{}" to language {}: {}'.format(
                translation_key, lang_text, str(e)
            )
            if _mcdr_tr_allow_failure:
                if _calyx_log_error_message:
                    self.logger.error(error_message)
                return _calyx_default_fallback
            else:
                raise e
