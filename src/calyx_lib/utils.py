import inspect
import os
import re
from pathlib import Path
from typing import Optional, Collection, Any, Callable, Union, TypeVar
from zipfile import ZipFile

from calyx_lib.generic import PathStr

__all__ = [
    'touch_directory',
    'clean_console_color_code',
    'clean_minecraft_color_code',
    'capitalize',
    'to_camel_case',
    'list_bundled_file',
    'represent'
]

"""
touch_directory(), clean_minecraft_color_code(), clean_console_color_code(),
represent(), list_bundled_file
Copied from MCDReforged(https://mcdreforged.com) v2.14.7
Licensed under LGPL v3.0 (only)
"""


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


def represent(
        obj: Any,
        fields: Optional[dict] = None,
        *,
        blacklist: Collection[str] = (),
        parentheses: str = '()'
) -> str:
    """
    aka repr
    """
    if fields is None:
        fields = {k: v for k, v in vars(obj).items() if not k.startswith('_')}
    blacklist = set(blacklist)
    return ''.join([
        type(obj).__name__,
        parentheses[0],
        ', '.join([
            f'{k}={v!r}'
            for k, v in fields.items()
            if k not in blacklist
        ]),
        parentheses[1],
    ])


T = TypeVar('T')

def adaptive_call(func: Callable[..., T], args: list, kwargs: dict) -> T:
    """
    Adaptive call functions

    All the positional and keyword args will adapt signature of the function
    All the parameters that are out of bound or not found in keyword arguments will be ignored
    :param func: Callable
    :param args: Positional arguments
    :param kwargs: Keyword arguments
    :return: Any
    """
    sig = inspect.signature(func)
    params = list(sig.parameters.values())

    final_args = []
    pos_names = [
        p.name for p in params
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]
    has_var_args = any(p.kind == p.VAR_POSITIONAL for p in params)
    has_var_kwargs = any(p.kind == p.VAR_KEYWORD for p in params)

    for i, arg_value in enumerate(args):
        if i >= len(pos_names):
            if has_var_args:
                final_args.append(arg_value)
            else:
                break
        elif pos_names[i] in kwargs:
            break
        else:
            final_args.append(arg_value)

    if has_var_kwargs:
        final_kwargs = kwargs
    else:
        valid_keys = {p.name for p in params}
        final_kwargs = {k: v for k, v in kwargs.items() if k in valid_keys}

    return func(*final_args, **final_kwargs)

