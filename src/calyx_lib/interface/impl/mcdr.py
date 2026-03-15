import re
from logging import Logger
from typing import List, Optional

from mcdreforged import RTextMCDRTranslation
from mcdreforged.api.types import CommandSource
from mcdreforged.api.types import PluginServerInterface
from mcdreforged.api.rtext import RText, RAction, RTextBase

from calyx_lib.interface.blossom_base_interface import BlossomBaseInterface
from calyx_lib.generic import MessageText


class BlossomMCDRInterface(BlossomBaseInterface):
    def __init__(self):
        self.server = PluginServerInterface.psi()
        super().__init__()

    def get_logger(self) -> Logger:
        return self.server.logger

    def get_language(self):
        return self.server.get_mcdr_language()

    def htr(
            self,
            translation_key: str,
            *args,
            prefixes: Optional[List[str]] = None,
            suggest_prefix: Optional[str] = None,
            **kwargs,
    ):
        prefixes = prefixes or [""]

        def __get_regex_result(line: str):
            pattern = r"(?<=§7){}[\S ]*?(?=§)"
            for prefix in prefixes:
                result = re.search(pattern.format(prefix), line)
                if result is not None:
                    return result
            return None

        def __htr(key: str, *inner_args, **inner_kwargs) -> MessageText:
            nonlocal suggest_prefix
            original = self.tr(key, *inner_args, **inner_kwargs)
            processed: List[MessageText] = []
            if not isinstance(original, str):
                return key
            for line in original.splitlines():
                result = __get_regex_result(line)
                if result is not None:
                    command = result.group().strip() + " "
                    if suggest_prefix is not None:
                        command = suggest_prefix.strip() + " " + command
                    processed.append(
                        RText(line)
                        .c(RAction.suggest_command, command)
                        .h(self.rtr("calyx_lib.help_message.suggest", command))
                    )

                    self.logger.debug(f'Rich help line: "{line}"')
                    self.logger.debug(
                        "Suggest prefix: {}".format(
                            f'"{suggest_prefix}"'
                            if isinstance(suggest_prefix, str)
                            else suggest_prefix
                        )
                    )
                    self.logger.debug(f'Suggest command: "{command}"')
                else:
                    processed.append(line)
            return RTextBase.join("\n", processed)

        return self.rtr(translation_key, *args, **kwargs).set_translator(__htr)

    def reply(self, source: CommandSource, text: MessageText):
        with RTextMCDRTranslation.language_context(source.get_preference().language):
            for line in self.split_rtext_into_raw_json_list(RTextBase.from_any(text), divider='\n'):
                source.reply(RTextBase.from_json_object(line))
