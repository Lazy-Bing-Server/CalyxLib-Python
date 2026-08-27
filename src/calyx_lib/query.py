import asyncio
import re
from contextlib import contextmanager
from logging import Logger
from queue import Queue
from typing import Union, Optional, List

from mcdreforged.api.event import MCDRPluginEvents
from mcdreforged.api.types import PluginServerInterface, Info


__all__ = [
    'CommandQueries'
]


class QueryItem:
    def __init__(self, command: str, patterns: List[Union[str, re.Pattern]]):
        self.command = command
        self.patterns = [re.compile(pattern) for pattern in patterns]
        self.queue: Queue[re.Match] = Queue()

    def get(self, timeout: float = 3.0) -> Optional[re.Match]:
        """Synchronous blocking get"""
        return self.queue.get(block=True, timeout=timeout)

    async def async_get(self, timeout: float = 3.0) -> Optional[re.Match]:
        """Async non-blocking get"""
        try:
            # Run the blocking queue.get in a thread to avoid blocking the event loop
            loop = asyncio.get_running_loop()
            return await asyncio.wait_for(
                loop.run_in_executor(None, self.queue.get, True, timeout),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            return None


class CommandQueries:
    def __init__(
            self,
            server: "PluginServerInterface",
            logger: Optional[Logger] = None,
            allow_use_same_line: bool = True
    ):
        self.__server = server
        self.__logger = logger or server.logger
        self.__items: List[QueryItem] = []
        self.allow_use_same_line = allow_use_same_line
        self.register_event_listeners()

    @contextmanager
    def work_context(self, command: str, patterns: List[Union[str, re.Pattern]]):
        item = QueryItem(command, patterns)
        try:
            self.__items.append(item)
            yield item
        finally:
            self.__items.remove(item)

    def query(
            self,
            command: str,
            patterns: List[Union[str, re.Pattern]],
            timeout: float = 3.0
    ) -> Optional[re.Match]:
        """
        Synchronous query. Blocks the current thread until response or timeout.
        
        :param command: Command string to execute
        :param patterns: List of regex patterns to match
        :param timeout: Timeout in seconds (default: 3.0)
        :return: Match object or None if timeout
        :raises RuntimeError: If this method is called on executor thread
        """
        if self.__server.is_on_executor_thread():
            raise RuntimeError("Can't run query operation on executor thread")
        # noinspection PyArgumentList
        with self.work_context(command=command, patterns=patterns) as item:
            self.__server.execute(item.command)
            return item.get(timeout=timeout)

    async def async_query(
            self,
            command: str,
            patterns: List[Union[str, re.Pattern]],
            timeout: float = 3.0
    ) -> Optional[re.Match]:
        """
        Async query. Non-blocking, can be used in async context.
        
        :param command: Command string to execute
        :param patterns: List of regex patterns to match
        :param timeout: Timeout in seconds (default: 3.0)
        :return: Match object or None if timeout
        """
        # noinspection PyArgumentList
        with self.work_context(command=command, patterns=patterns) as item:
            self.__server.execute(item.command)
            return await item.async_get(timeout=timeout)

    def on_info(self, server: "PluginServerInterface", info: "Info"):
        if info.is_from_server:
            for item in self.__items:
                match = None
                for p in item.patterns:
                    match = p.fullmatch(str(info.content))
                    if match is not None:
                        break
                if match is not None:
                    item.queue.put(match)
                    if not self.allow_use_same_line:
                        break

    def register_event_listeners(self):
        self.__server.register_event_listener(MCDRPluginEvents.GENERAL_INFO, self.on_info)
