import re
from logging import Logger
from threading import RLock
from typing import List, Optional

from mcdreforged.api.decorator import new_thread
from mcdreforged.api.event import MCDRPluginEvents
from mcdreforged.api.types import PluginServerInterface

from calyx_lib.query import CommandQueries
from calyx_lib.utils import to_camel_case


ONLINE_PLAYER_MATCH_PATTERN = [
    # <1.16
    # There are 6 of a max 100 players online: 122, abc, xxx, www, QwQ, bot_tob
    r"There are (?P<amount>[0-9]+) of a max (?P<limit>[0-9]+) players online:("
    r"?P<players>[\s\S]+)",
    # >=1.16
    # There are 2 of a max of 20 players online: Ra1ny_Yuki, xinbing
    r'There are (?P<amount>[0-9]+) of a max of (?P<limit>[0-9]+) players online:('
    r'?P<players>[\s\S]+)',
]


class OnlinePlayerRecorder:
    def __init__(
            self, server: "PluginServerInterface", logger: Optional["Logger"] = None
    ):
        self.__lock = RLock()
        self.__players: List[str] = []
        self.__server = server
        self.__logger = logger or server.logger
        self.__thread_prefix = to_camel_case(self.__server.get_self_metadata().id) + '@'
        self.__limit = 0
        self.__enabled = False
        self.__command = 'list'
        self.__queries = CommandQueries(self.__server, self.__logger)
        self.__patterns = ONLINE_PLAYER_MATCH_PATTERN

        self.register_event_listeners()

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

    def get_player_list(self, refresh: bool = False) -> List[str]:
        """
        Get player list in server
        :param refresh: If this is `true`, the values will be refreshed before return
        :return: List of player names
        """
        with self.__lock:
            if refresh:
                self.__refresh_online_players()
            return self.__players.copy()

    def get_player_limit(self, refresh: bool = False) -> int:
        """
        Get the maximum player count for this server
        :param refresh: If this is `true`, the values will be refreshed before return
        :return: Player limit value
        """
        with self.__lock:
            if refresh or self.__limit is None:
                self.__refresh_online_players()
            return self.__limit

    def __add_player(self, player: str):
        @new_thread(self.__thread_prefix + "AddOnlinePlayer")
        def __execute():
            with self.__lock:
                if self.__enabled and player not in self.__players:
                    self.__players.append(player)

        return __execute()

    def __remove_player(self, player: str):
        @new_thread(self.__thread_prefix + "RemoveOnlinePlayer")
        def __execute():
            with self.__lock:
                if self.__enabled and player in self.__players:
                    self.__players.remove(player)

        return __execute()

    def __refresh_online_players(self, timeout: int = 3):
        @new_thread(self.__thread_prefix + "RefreshOnlinePlayers")
        def __execute():
            with self.__lock:
                self.__logger.debug("Refreshing online players")
                if not self.__server.is_server_startup():
                    return

                self.__logger.debug(f"Player list command query timeout = {timeout}")
                match: Optional[re.Match] = self.__queries.query(   # type: ignore
                    self.__command, ONLINE_PLAYER_MATCH_PATTERN, timeout=timeout
                )

                if match is not None:
                    amount = match['amount']
                    self.__limit = match['limit']
                    players_string = match['players'].strip()
                    self.__players = players_string.split(', ')
                    self.__logger.debug(
                        "Player list refreshed: "
                        + ", ".join(self.__players)
                        + f" (max {self.__limit})"
                    )
                    if amount != len(self.__players):
                        self.__logger.warning(
                            "Incorrect player count found while refreshing player list"
                        )
                self.__enabled = True
        return __execute()

    def __enable_player_join(self):
        @new_thread(self.__thread_prefix + "EnablePlayerJoin")
        def __execute():
            with self.__lock:
                self.__enabled = True
                self.__logger.debug("Player list counting enabled")

        return __execute()

    def __clear_online_players(self):
        @new_thread(self.__thread_prefix + "ClearOnlinePlayers")
        def __execute():
            with self.__lock:
                self.__limit, self.__players = None, []
                self.__enabled = False
                self.__logger.debug(
                    "Cleared online player cache, player list counting disabled"
                )

        return __execute()

    def register_event_listeners(self) -> None:
        """
        If you want to make a recorder instance work in your plugin,
        This must be called in your plugin
        when plugin loaded event (on_load()) is dispatched
        :return: None
        """
        self.__queries.register_event_listeners()
        self.__server.register_event_listener(
            MCDRPluginEvents.PLUGIN_LOADED,
            lambda *args, **kwargs: self.__refresh_online_players(),
        )
        self.__server.register_event_listener(
            MCDRPluginEvents.SERVER_START,
            lambda *args, **kwargs: self.__enable_player_join(),
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