import os
import re
from pathlib import Path
from typing import Iterable, Protocol, Any
from typing import Union
from zipfile import ZipFile

from mcdreforged.api.rtext import RTextBase

PathStr = Union[str, Path]
MessageText = Union[RTextBase, str]


__all__ = [
    'touch_directory',
    'clean_console_color_code',
    'clean_minecraft_color_code',
    'capitalize',
    'to_camel_case',
    'list_bundled_file',
    'get_value_from_nested_subscriptable_item',
    'set_value_to_nested_subscriptable_item'
]


class Subscriptable(Protocol):
    def __getitem__(self, item) -> Any:
        pass

    def __setitem__(self, item, value) -> Any:
        pass


def touch_directory(directory_path: Union[Path, str]) -> None:
    if not os.path.isdir(directory_path):
        os.makedirs(directory_path, exist_ok=True)


def clean_minecraft_color_code(text: str):
    return re.compile(r'§[a-z0-9]').sub('', str(text))


def clean_console_color_code(text: str):
    return re.compile(r'\033\[(\d+(;\d+)*)?m').sub('', text)


def capitalize(string: str) -> str:
    char_list = list(string)
    if len(char_list) > 0:
        char_list[0] = char_list[0].upper()
    return "".join(char_list)


def to_camel_case(string: str, divider: str = " ", upper: bool = True) -> str:
    word_list = [capitalize(item) for item in string.split(divider)]
    if not upper:
        first_word_char_list = list(word_list[0])
        first_word_char_list[0] = first_word_char_list[0].lower()
        word_list[0] = "".join(first_word_char_list)
    return "".join(word_list)


def list_bundled_file(package_path: PathStr, directory_name: PathStr):
    if os.path.isdir(package_path):
        return os.listdir(os.path.join(package_path, directory_name))
    with ZipFile(package_path, 'r') as zip_file:
        result = []
        directory_name = str(directory_name).replace('\\', '/').rstrip('/\\') + '/'
        for file_info in zip_file.infolist():
            # is inside the dir and is directly inside
            if file_info.filename.startswith(directory_name):
                file_name = file_info.filename.replace(directory_name, '', 1)
                if len(file_name) > 0 and '/' not in file_name.rstrip('/'):
                    result.append(file_name)
    return result


def get_value_from_nested_subscriptable_item(
    item: Subscriptable, path: Iterable[str], default: Any = None
) -> Any:
    operating_path = list(path)
    current_index = operating_path.pop(0)
    try:
        current_value = item[current_index]
    except:
        return default
    if not operating_path:
        return current_value
    return get_value_from_nested_subscriptable_item(
        current_value, operating_path, default=default
    )


def set_value_to_nested_subscriptable_item(
    item: Subscriptable, path: Iterable[str], value: Any, default: Any = None
) -> Any:
    operating_path = list(path)
    current_index = operating_path.pop(0)
    try:
        current_value = item[current_index]
    except:
        return False
    if not operating_path:
        item[current_index] = value
        return True
    else:
        return set_value_to_nested_subscriptable_item(
            current_value, operating_path, value, default=default
        )
