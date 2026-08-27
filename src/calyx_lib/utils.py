import logging

from mcdreforged import ServerInterface
import inspect
import os
import re
import functools
import threading
import sys
from pathlib import Path
from typing import Optional, Collection, Any, Callable, Union, TypeVar
from zipfile import ZipFile

from mcdreforged.api.decorator import FunctionThread
from calyx_lib.generic import PathStr

__all__ = [
    'touch_directory',
    'clean_console_color_code',
    'clean_minecraft_color_code',
    'capitalize',
    'to_camel_case',
    'list_bundled_file',
    'adaptive_call',
    'named_thread',
]

"""
touch_directory(), clean_minecraft_color_code(), clean_console_color_code(),
represent(), list_bundled_file
Copied from MCDReforged(https://mcdreforged.com) v2.14.7
Licensed under LGPL v3.0 (only)
"""


def touch_directory(directory_path: Union[Path, str]) -> None:
    """
    Ensure that a directory exists
    :param directory_path: Target directory path
    :return: Nothing
    """
    if not os.path.isdir(directory_path):
        os.makedirs(directory_path, exist_ok=True)


def clean_minecraft_color_code(text: str):
    """
    Remove all the minecraft formatting code in a string
    :param text: Target directory path
    :return: Result string
    """
    return re.compile(r'§[a-z0-9]').sub('', str(text))


def clean_console_color_code(text: str):
    """
    Remove all the console color code in a string
    :param text: Target directory path
    :return: Result string
    """
    return re.compile(r'\033\[(\d+(;\d+)*)?m').sub('', text)


def capitalize(string: str) -> str:
    """
    Capitalize a string
    :param string: Target string
    :return: Result string
    """
    char_list = list(string)
    if len(char_list) > 0:
        char_list[0] = char_list[0].upper()
    return "".join(char_list)


def to_camel_case(string: str, divider: str = " ", upper: bool = True) -> str:
    """
    Turn a string into CamelCase
    :param string: Target string
    :param divider: Separator of the original string, a space by default
    :param upper: Should the string be transformed into an UpperCamelCase or lowerCamelCase
    :return: CamelCase string
    """
    word_list = [capitalize(item) for item in string.split(divider)]
    if not upper:
        first_word_char_list = list(word_list[0])
        first_word_char_list[0] = first_word_char_list[0].lower()
        word_list[0] = "".join(first_word_char_list)
    return "".join(word_list)


def list_bundled_file(package_path: PathStr, directory_name: PathStr):
    """
    List all bundled files in a zip package
    :param package_path: Package path
    :param directory_name: Directory path in pack
    :return: File list
    """
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


def get_thread_prefix(name: str) -> str:
    return to_camel_case(name, divider="_") + "@"


def named_thread(arg: Optional[Union[str, Callable]] = None, logger: Optional[logging.Logger] = None, prefix: Optional[str] = None) -> Callable:
    """
    Similar to `mcdreforged.api.decorator.new_thread()`
    If no name provided, this will automatically combine the plugin name and function name as the thread name

    :param arg: Function or the name
    :param logger: Define which logger to use when exception occurred, PluginServerInterface.logger by default (in MCDR)
    :param prefix: Override the prefix, the default value is the plugin id in camel case
    :return: Wrapped function
    """
    # Get logger
    if logger is None:
        si = ServerInterface.psi_opt()
        if si is None:
            si = ServerInterface.si_opt()
        logger = si.logger if si is not None else logging.getLogger("Calyx")

    if prefix is None:
        psi = ServerInterface.psi_opt()
        if psi is not None:
            prefix = get_thread_prefix(psi.get_self_metadata().id)
        else:
            # Get caller module name
            frame = inspect.stack()[1]
            module = inspect.getmodule(frame[0])

            if module is not None and hasattr(module, '__name__'):
                module_name = module.__name__.split('.')[0]
                prefix = get_thread_prefix(module_name)
            elif module is not None and hasattr(module, '__file__'):
                file_name = Path(module.__file__).name
                if '.' in file_name:
                    base, _ = file_name.rsplit('.', 1)
                else:
                    base = file_name
                prefix = get_thread_prefix(base)
            else:
                prefix = 'CalyxLib@'


    def wrapper(func):
        @functools.wraps(func)
        def wrap(*args, **kwargs):
            def try_func():
                try:
                    return func(*args, **kwargs)
                finally:
                    if sys.exc_info()[0] is not None and logger is not None:
                        logger.exception(
                            f"Error running thread {threading.current_thread().name}"
                        )
            thread = FunctionThread(
                target=try_func, args=[], kwargs={}, name=thread_name
            )
            thread.start()
            return thread

        wrap.__signature__ = inspect.signature(func)  # ty:ignore[unresolved-attribute]
        wrap.original = func # ty:ignore[unresolved-attribute]
        return wrap

    # Directly use @new_thread without ending brackets case, e.g. @new_thread
    if callable(arg):
        thread_name = prefix + to_camel_case(arg.__name__, divider="_")  # ty:ignore[unresolved-attribute]
        return wrapper(arg)
    # Use @new_thread with ending brackets case, e.g. @new_thread('A'), @new_thread()
    elif arg is None:
        return lambda arg_: named_thread(arg=arg_, logger=logger, prefix=prefix)
    else:
        thread_name = arg
        return wrapper

