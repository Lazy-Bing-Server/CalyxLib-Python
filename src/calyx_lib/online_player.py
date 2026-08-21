import asyncio
import re
from logging import Logger
from threading import RLock
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor

from mcdreforged import FunctionThread
from mcdreforged.api.decorator import new_thread
from mcdreforged.api.event import MCDRPluginEvents
from mcdreforged.api.types import PluginServerInterface

from calyx_lib.query import CommandQueries
from calyx_lib.utils import to_camel_case


__all__ = ['OnlinePlayerRecorder']


ONLINE_PLAYER_MATCH_PATTERN = [
    # <1.16
    # There are 6 of a max 100 players online: 122, abc, xxx, www, QwQ, bot_tob
    r"There are (?P<amount>[0-9]+) of a max (?P<limit>[0-9]+) players online:("
    r"?P<players>[\s\S]+)",
    # >=1.16
    # There are 2 of a max of 20 players online: Jeb, Notch
    r'There are (?P<amount>[0-9]+) of a max of (?P<limit>[0-9]+) players online:('
    r'?P<players>[\s\S]+)',
]

class _Unset:
    pass

_UNSET = _Unset()

class OnlinePlayerRecorder:
    def __init__(
            self,
            server: "PluginServerInterface",
            logger: Optional["Logger"] = None,
            refresh_on_server_starts: bool = False,
            command_list_patterns: Optional[List[str]] = None,
            list_command: str = 'list',
            thread_prefix: Optional[str] = None,
    ):
        self.__sync_lock = RLock()
        self.__players: List[str] = []
        self.__server = server
        self.__logger = logger or server.logger
        self.__thread_prefix = thread_prefix or to_camel_case(self.__server.get_self_metadata().id) + '@'
        self.__limit: Optional[int, "_Unset"] = None
        self.__enabled = False
        self.__command = list_command
        self.__queries = CommandQueries(self.__server, self.__logger)
        self.__patterns = command_list_patterns or ONLINE_PLAYER_MATCH_PATTERN
        self.__executor = ThreadPoolExecutor(thread_name_prefix=self.__thread_prefix + "GetPlayerList")

        self.register_event_listeners(refresh_on_server_start=refresh_on_server_starts)

    @property
    def on_executor_thread(self) -> bool:
        return self.__server.is_on_executor_thread() or self.__server.is_on_async_executor_thread()

    def set_player_list_query_patterns(self, patterns: List[str]) -> None:
        """
        If the default patterns work fine, this method is not required to be called.
        Unless these patterns can't match your server return message for command list
        :param patterns: The patterns to replace the default ones
        :return: None
        """
        self.__patterns = patterns

    def set_player_list_command(self, command: str):
        self.__command = command


    async def async_get_player_list(self) -> List[str]:
        """
        Asynchronous get player list in server
        :return: List of player names
        """
        return await asyncio.get_event_loop().run_in_executor(self.__executor, self.get_player_list)

    def get_player_list(self) -> List[str]:
        """
        Get player list in server
        :return: List of player names
        """
        with self.__sync_lock:
            if self.__players is None:
                raise RuntimeError("OnlinePlayerRecorder is not initialized yet")
            return self.__players.copy()

    async def async_get_player_limit(self) -> Optional[int]:
        """
        Asynchronous get the maximum player count for this server
        :return: Player limit value, or None if the limit is not provided by the server
        """
        return await asyncio.get_event_loop().run_in_executor(self.__executor, self.get_player_limit)

    def get_player_limit(self) -> Optional[int]:
        """
        Get the maximum player count for this server
        :return: Player limit value, or None if the limit is not provided by the server
        """
        with self.__sync_lock:
            if self.__limit is _UNSET:
                return None
            elif self.__limit is None:
                raise RuntimeError("OnlinePlayerRecorder is not initialized yet")
            return self.__limit

    def __add_player(self, player: str):
        @new_thread(self.__thread_prefix + "AddOnlinePlayer")
        def __execute():
            with self.__sync_lock:
                if self.__enabled and player not in self.__players:
                    self.__players.append(player)

        return __execute()

    def __remove_player(self, player: str):
        @new_thread(self.__thread_prefix + "RemoveOnlinePlayer")
        def __execute():
            with self.__sync_lock:
                if self.__enabled and player in self.__players:
                    self.__players.remove(player)

        return __execute()

    def __refresh_online_players(self, timeout: int = 3) -> FunctionThread:
        @new_thread(self.__thread_prefix + "RefreshOnlinePlayers")
        def __execute():
            with self.__sync_lock:
                self.__logger.debug("Refreshing online players")
                if not self.__server.is_server_startup():
                    return

                self.__logger.debug(f"Player list command query timeout = {timeout}")
                match: Optional[re.Match] = self.__queries.query(
                    self.__command, self.__patterns, timeout=timeout  # ty:ignore[invalid-argument-type]
                )

                if isinstance(match, re.Match):
                    match_dict= match.groupdict()
                    amount_str = match_dict.get('amount')
                    amount = int(amount_str) if amount_str is not None and amount_str.isdigit() else 0
                    limit = match_dict.get('limit')
                    if limit is not None and limit.isdigit():
                        self.__limit = int(limit)
                    else:
                        self.__limit = _UNSET
                    players_string = match_dict['players'].strip()
                    self.__players = []
                    if players_string != "":
                        self.__players = list(players_string.split(', '))
                    self.__logger.debug(
                        "Player list refreshed: "
                        + ", ".join(self.__players)
                        + f" (max {self.__limit})"
                    )
                    if amount_str is not None and amount != len(self.__players):
                        self.__logger.warning(f"Parsed player counts: {amount}")
                        self.__logger.warning(f"Parsed player list length: {len(self.__players)}")
                        self.__logger.warning(
                            f"Incorrect player count found while refreshing player list"
                        )
                self.__enabled = True
        return __execute() # type: ignore   fk decorator no type hint :<  what the fk does "unused blanket" mean, ty?

    def __enable_player_join(self):
        @new_thread(self.__thread_prefix + "EnablePlayerJoin")
        def __execute():
            with self.__sync_lock:
                self.__enabled = True
                self.__logger.debug("Player list counting enabled")
        return __execute()

    def __clear_online_players(self):
        @new_thread(self.__thread_prefix + "ClearOnlinePlayers")
        def __execute():
            with self.__sync_lock:
                self.__limit, self.__players = None, []
                self.__enabled = False
                self.__logger.debug(
                    "Cleared online player cache, player list counting disabled"
                )

        return __execute()

    def __shutdown_executor(self):
        self.__executor.shutdown(wait=False)
        self.__logger.debug("Shutdown executor for online player recorder")

    def register_event_listeners(self, refresh_on_server_start: bool = False) -> None:
        self.__queries.register_event_listeners()
        self.__server.register_event_listener(
            MCDRPluginEvents.PLUGIN_LOADED,
            lambda *args, **kwargs: self.__refresh_online_players(),
        )
        if not refresh_on_server_start:
            self.__server.register_event_listener(
                MCDRPluginEvents.SERVER_START,
                lambda *args, **kwargs: self.__enable_player_join(),
            )
        else:
            self.__server.register_event_listener(
                MCDRPluginEvents.SERVER_STARTUP,
                lambda *args, **kwargs: self.__refresh_online_players(),
            )
        self.__server.register_event_listener(
            MCDRPluginEvents.PLAYER_JOINED,
            lambda _, player, __: self.__add_player(player),
        )
        self.__server.register_event_listener(
            MCDRPluginEvents.PLAYER_LEFT, lambda _, player: self.__remove_player(player)
        )
        self.__server.register_event_listener(
            MCDRPluginEvents.SERVER_STOP,
            lambda *args, **kwargs: self.__clear_online_players(),
        )
        self.__server.register_event_listener(
            MCDRPluginEvents.PLUGIN_UNLOADED,
            lambda *args, **kwargs: self.__shutdown_executor(),
        )