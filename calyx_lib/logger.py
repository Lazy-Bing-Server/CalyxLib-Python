"""
Custom logger for MCDR

Modified from https://github.com/MCDReforged/MCDReforged/
Lesser GNU Public License v3
"""
import datetime
import itertools
import logging
import os
import sys
import time
import zipfile
from contextlib import contextmanager
from pathlib import Path
from threading import local, Lock
from typing import Dict, Optional, IO, Type, Any

from colorama import Fore, Style
from colorlog import ColoredFormatter
from mcdreforged.api.types import ServerInterface

from calyx_lib.utils import (
    clean_minecraft_color_code,
    clean_console_color_code,
    touch_directory
)


class ZippingDayRotatingFileHandler(logging.FileHandler):
    def __init__(self, file_path: str, rotate_day_count: int):
        self.rotate_day_count = rotate_day_count
        self.file_path = Path(file_path)
        self.dir_path = self.file_path.parent

        self.last_rover_date: Optional[datetime.date] = None
        self.last_record_date: Optional[datetime.date] = None
        self.try_rotate()

        super().__init__(file_path, encoding='utf8')

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.try_rotate()
            super().emit(record)
        except Exception:       # type: ignore
            self.handleError(record)

    def try_rotate(self):
        current = datetime.datetime.now().date()

        if (
            self.last_rover_date is None
            or
            (current - self.last_rover_date).days >= self.rotate_day_count
        ):
            self.do_rotate(
                self.last_record_date and self.last_record_date.strftime('%Y-%m-%d')
            )
            self.last_rover_date = current

        self.last_record_date = current

    def do_rotate(self, base_name: Optional[str] = None):
        if not self.file_path.is_file():
            return

        inited = hasattr(self, 'stream')
        if inited:
            self.stream.close()
        try:
            if base_name is None:
                try:
                    log_time = time.localtime(self.file_path.stat().st_mtime)
                except (OSError, OverflowError, ValueError):
                    log_time = time.localtime()
                base_name = time.strftime('%Y-%m-%d', log_time)
            for counter in itertools.count(start=1):
                zip_path = self.dir_path / '{}-{}.zip'.format(base_name, counter)
                if not zip_path.is_file():
                    break
            else:
                raise RuntimeError('should already able to get a valid zip path')
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                zipf.write(
                    self.file_path,
                    arcname=self.file_path.name,
                    compress_type=zipfile.ZIP_DEFLATED
                )

            try:
                self.file_path.unlink()
            except OSError:
                # failed to delete the old log file
                # might due to another MCDR instance being running
                # delete the rotated zip file to avoid duplication
                try:
                    zip_path.unlink()
                except OSError:
                    pass
                raise
        finally:
            if inited:
                self.stream = self._open()


class _SyncWriteStream:
    """
    A stream wrapper with its method "write" synchronized.
    All accesses to other attributes are forwarded to the wrapped stream
    """
    def __init__(self, stream: IO[str]):
        self.sws_stream = stream
        self.sws_lock = Lock()

    def write(self, s: str):
        with self.sws_lock:
            self.sws_stream.write(s)

    def __getattribute__(self, item: str):
        if item in ('write', 'sws_stream', 'sws_lock'):
            return object.__getattribute__(self, item)
        else:
            return self.sws_stream.__getattribute__(item)


class SyncStdoutStreamHandler(logging.StreamHandler):
    __sws = _SyncWriteStream(sys.stdout)

    def __init__(self):
        super().__init__(type(self).__sws)

    @classmethod
    def update_stdout(cls, stream: IO[str]):
        cls.__sws.sws_stream = stream

    @classmethod
    def write_direct(cls, s: str):
        cls.__sws.write(s)


class MCColorFormatControl:
    MC_CODE_ITEMS: Dict[str, Fore] = {
        '§0': Fore.BLACK,
        '§1': Fore.BLUE,
        '§2': Fore.GREEN,
        '§3': Fore.CYAN,
        '§4': Fore.RED,
        '§5': Fore.MAGENTA,
        '§6': Fore.YELLOW,
        '§7': Fore.WHITE + Style.DIM,
        '§8': Fore.WHITE + Style.DIM,
        '§9': Fore.LIGHTBLUE_EX,
        '§a': Fore.LIGHTGREEN_EX,
        '§b': Fore.LIGHTCYAN_EX,
        '§c': Fore.LIGHTRED_EX,
        '§d': Fore.LIGHTMAGENTA_EX,
        '§e': Fore.LIGHTYELLOW_EX,
        '§f': Fore.WHITE,
    }

    # global flag
    console_color_disabled = False

    __TLS = local()

    @classmethod
    @contextmanager
    def disable_minecraft_color_code_transform(cls):
        cls.__set_mc_code_trans_disable(True)
        try:
            yield
        finally:
            cls.__set_mc_code_trans_disable(False)

    @classmethod
    def __is_mc_code_trans_disabled(cls) -> bool:
        try:
            return cls.__TLS.mc_code_trans
        except AttributeError:
            cls.__set_mc_code_trans_disable(False)
            return False

    @classmethod
    def __set_mc_code_trans_disable(cls, state: bool):
        cls.__TLS.mc_code_trans = state

    @classmethod
    def modify_message_text(cls, text: str) -> str:
        if not cls.__is_mc_code_trans_disabled():
            # minecraft code -> console code
            if '§' in text:
                for mc_code, console_code in cls.MC_CODE_ITEMS.items():
                    if mc_code in text:
                        text = text.replace(mc_code, console_code)
                # clean the rest of minecraft codes
                text = clean_minecraft_color_code(text)
        if cls.console_color_disabled:
            text = clean_console_color_code(text)
        return text


class MCDReforgedFormatter(ColoredFormatter):
    def formatMessage(self, record: logging.LogRecord):
        text = super().formatMessage(record)
        return MCColorFormatControl.modify_message_text(text)


class NoColorFormatter(logging.Formatter):
    def formatMessage(self, record: logging.LogRecord):
        return clean_console_color_code(super().formatMessage(record))


class PluginIdAwareFormatter(logging.Formatter):
    PLUGIN_ID_KEY = 'plugin_id'

    def __init__(
            self, fmt_class: Type[logging.Formatter], fmt_str_with_key: str, **kwargs
    ):
        super().__init__()
        fmt_str_without_key = fmt_str_with_key.replace(' [%(plugin_id)s]', '')
        if fmt_str_without_key == fmt_str_with_key:
            raise ValueError(fmt_str_with_key)

        self.fmt_with_key = fmt_class(fmt_str_with_key, **kwargs)
        self.fmt_without_key = fmt_class(fmt_str_without_key, **kwargs)

    def format(self, record: logging.LogRecord):
        if hasattr(record, self.PLUGIN_ID_KEY):
            return self.fmt_with_key.format(record)
        else:
            return self.fmt_without_key.format(record)


class BlossomLogger(logging.Logger):
    DEFAULT_NAME = "Calyx"
    ROTATE_DAY_COUNT = 7
    LOG_COLORS = {
        'DEBUG': 'blue',
        'INFO': 'green',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'bold_red',
    }
    SECONDARY_LOG_COLORS = {
        'message': {
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red'
        }
    }

    FILE_FORMATTER = PluginIdAwareFormatter(
        NoColorFormatter,
        '[%(name)s] [%(asctime)s.%(msecs)d] [%(threadName)s/%(levelname)s] [%('
        'filename)s:%(lineno)d(%(funcName)s)] [%(plugin_id)s]: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    CONSOLE_FORMATTER = PluginIdAwareFormatter(
        MCDReforgedFormatter,
        '[%(name)s] [%(asctime)s] [%(threadName)s/%(log_color)s%(levelname)s%(reset)s] '
        '[%(plugin_id)s]: %(message_log_color)s%(message)s%(reset)s',
        log_colors=LOG_COLORS,
        secondary_log_colors=SECONDARY_LOG_COLORS,
        datefmt='%H:%M:%S',
    )

    def __init__(self, plugin_id: Optional[str] = None):
        super().__init__(self.DEFAULT_NAME)
        self.file_handler: Optional[logging.FileHandler] = None
        self.__plugin_id = plugin_id

        self.console_handler = SyncStdoutStreamHandler()
        self.console_handler.setFormatter(self.CONSOLE_FORMATTER)

        self.addHandler(self.console_handler)
        self.setLevel(logging.INFO)
        self.__verbosity: bool = False

    def set_verbosity(self, verbosity: bool):
        self.__verbosity = verbosity

    def should_log_debug(self, *args, **kwargs):
        mcdr_should_log = False
        try:
            psi = ServerInterface.psi_opt()
            if psi is not None:
                mcdr_should_log = psi.logger.should_log_debug()  # type: ignore
        except:
            pass
        return self.__verbosity or mcdr_should_log

    def _log(self, level: int, msg: Any, args: tuple, **kwargs) -> None:
        if self.__plugin_id is not None:
            extra_args = kwargs.get('extra', {})
            extra_args[PluginIdAwareFormatter.PLUGIN_ID_KEY] = self.__plugin_id
            kwargs['extra'] = extra_args

        # noinspection PyProtectedMember
        super()._log(level, msg, args, **kwargs)

    def mdebug(self, msg: Any, *args, no_check: bool = False):
        """
        mcdr debug logging
        """
        if no_check or self.isEnabledFor(logging.DEBUG) or self.should_log_debug():
            with MCColorFormatControl.disable_minecraft_color_code_transform():
                self._log(logging.DEBUG, msg, args, stacklevel=2)

    def debug(self, msg: Any, *args, **kwargs):
        if self.isEnabledFor(logging.DEBUG) or self.should_log_debug():
            with MCColorFormatControl.disable_minecraft_color_code_transform():
                self._log(logging.DEBUG, msg, args, **kwargs, stacklevel=2)

    def set_file(self, file_path: str, no_zip_archive: bool = False):
        """

        :param file_path:
        :param no_zip_archive:
        :return:
        """
        if self.file_handler is not None:
            self.unset_file()

        if no_zip_archive:
            self.file_handler = logging.FileHandler(file_path, encoding='UTF-8')
        else:
            touch_directory(os.path.dirname(file_path))
            self.file_handler = ZippingDayRotatingFileHandler(
                file_path, self.ROTATE_DAY_COUNT
            )

        self.file_handler.setFormatter(self.FILE_FORMATTER)
        self.addHandler(self.file_handler)

    def unset_file(self):
        """
        **Not public API**

        :meta private:
        """
        if self.file_handler is not None:
            self.removeHandler(self.file_handler)
            self.file_handler.close()
            self.file_handler = None
