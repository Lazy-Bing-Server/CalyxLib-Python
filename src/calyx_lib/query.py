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
        return self.queue.get(block=True, timeout=timeout)


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
        if self.__server.is_on_executor_thread():
            raise RuntimeError("Can't run query operation on executor thread")
        with self.work_context(command, patterns) as item:  # type: QueryItem
            self.__server.execute(item.command)
            return item.get(timeout=timeout)

    def on_info(self, server: "PluginServerInterface", info: "Info"):
        # print(f"Received info from server: {info.content}")
        if info.is_from_server:
            for item in self.__items:
                match = None
                for p in item.patterns:
                    # print(p)
                    match = p.fullmatch(str(info.content))
                    if match is not None:
                        break
                if match is not None:
                    item.queue.put(match)
                    if not self.allow_use_same_line:
                        break

    def register_event_listeners(self):
        self.__server.register_event_listener(MCDRPluginEvents.GENERAL_INFO, self.on_info)
