from typing import Tuple, Iterable, Generic, Callable, Optional, List, TypeVar
from typing import Literal as LiteralType
from types import MethodType
from math import ceil

from mcdreforged.api.rtext import *
from mcdreforged.api.command import CommandContext, AbstractNode, Literal, Integer


from calyx_lib.interface.blossom_base_interface import BlossomBaseInterface
from calyx_lib.generic import MessageText

PAGE_ARG = '--page'
PAGE_NUM = "page_num"
ITEM_ARG = '--per-page'
ITEM_PER_PAGE = "item_count"
LIST_COMMAND = '_calyx_list_command_without_params'
T = TypeVar("T")


__all__ = [
    "PagedListWidget"
]


class PagedListWidget(Generic[T]):
    def __init__(
        self,
        base_interface: "BlossomBaseInterface",
        object_list: Iterable[T],
        factory: Callable[[T], RTextBase],
        default_item_per_page: int,
        context: CommandContext
    ):
        self.__interface = base_interface
        self.__list = list(object_list)
        self.__factory = factory
        self.__default_item_per_page = default_item_per_page
        self.__ctx = context

    def __build(self, head: Optional[int] = None, tail: Optional[int] = None):
        lines: List[RTextBase] = []
        for item in self.__list[head:tail]:
            line = self.__factory(item)
            if line is not None:
                lines.append(line)
        return lines

    def get_max_page(self, item_per_page: Optional[int] = None):
        """
        Calculate how many pages this list being divided into
        :param item_per_page: Input a item count per page to override the default one
        :return: `int`, number of pages
        """
        item_per_page = item_per_page or self.__default_item_per_page
        return ceil(len(self) / item_per_page)

    def get_head_tail_index(self, page: int, item_per_page: Optional[int] = None):
        """
        Calculate index of the first and the last item of this page
        :param page: Requested page index
        :param item_per_page: Input a item count per page to override the default one
        :return: `tuple[int, int]` Head index and tail index
        """
        if page > self.get_max_page(item_per_page):
            raise IndexError("Page index out of range")
        item_per_page = item_per_page or self.__default_item_per_page
        head_index = (page - 1) * item_per_page
        tail_index = head_index + item_per_page
        if tail_index >= self.length:
            tail_index = self.length
        self.__interface.logger.debug(f"Page: {page} Item per page: {item_per_page}")
        self.__interface.logger.debug(f"Head: {head_index} Tail: {tail_index}")
        return head_index, tail_index

    def __get_page_line_list(
        self,
        page: int,
        item_per_page: Optional[int] = None,
    ) -> List[MessageText]:
        if page > self.get_max_page(item_per_page=item_per_page):
            return []
        return self.__build(*self.get_head_tail_index(page, item_per_page))

    @staticmethod
    def __format_command(command: str, page: int, item_per_page: Optional[int] = None):
        command = command.strip() + f' {PAGE_ARG} {page}'
        if item_per_page is not None:
            command += f' {ITEM_PER_PAGE} {item_per_page}'
        return command

    def get_page_hint_line(
        self,
        page: int,
        item_per_page: Optional[int] = None,
        command: Optional[str] = None,
        action: RAction = RAction.run_command,
    ):
        interface = self.__interface
        actual_item_per_page: int = item_per_page or self.__default_item_per_page
        max_page = self.get_max_page(actual_item_per_page)
        prev_button = RText("<-")
        if page == 1:
            prev_button.set_color(RColor.dark_gray)
        elif command is not None:
            prev_button.c(
                action,
                self.__format_command(command, page - 1, item_per_page=item_per_page),
            ).h(interface.rtr(f"calyx_lib.list_widget.prev_button.hover"))
        next_button = RText("->")
        if page >= max_page:
            next_button.set_color(RColor.dark_gray)
        elif command is not None:
            next_button.c(
                action,
                self.__format_command(command, page + 1, item_per_page=item_per_page),
            ).h(interface.rtr(f"calyx_lib.list_widget.next_button.hover"))
        return RTextBase.join(' ', (prev_button, f"§d{page}§7/§5{max_page}§r", next_button))

    @staticmethod
    def __get_page_arguments(context: CommandContext) -> Tuple[int, Optional[int], Optional[str]]:
        return (
            context.get(PAGE_NUM, 1),
            context.get(ITEM_PER_PAGE, None),
            context.get(LIST_COMMAND, None),
        )

    def get_full_page_lines(self, hint_line: LiteralType['header', 'footer', 'disabled'] = 'footer') -> List[MessageText]:
        """
        Get full page text in a list of these lines.
        :param hint_line: Specified where the page index hint will be, as `footer` (by default) or `header`.
        Or you can input a `disabled` to get a list without page hint line
        :return: List of full page text
        """
        page_num, item_per_page, command = self.__get_page_arguments(self.__ctx)
        page_lines = self.__get_page_line_list(page_num, item_per_page=item_per_page)
        if hint_line == 'disabled':
            return page_lines
        page_hint = self.get_page_hint_line(page_num, item_per_page=item_per_page, command=command)
        if hint_line == 'header':
            page_lines = [page_hint] + page_lines
        elif hint_line == 'footer':
            page_lines.append(page_hint)
        else:
            raise ValueError("Invalid hint line status provided")
        return page_lines

    def get_full_page_text(self, hint_line: LiteralType['header', 'footer', 'disabled'] = 'footer') -> MessageText:
        """
        Get full page text. Connect all these lines with line feed(LF or `\n`)
        Line feed mark may not be displayed correctly as a line break in older Minecraft versions.
        Use `get_full_page_lines()` and send them separately instead if the problem occurs.
        :param hint_line: Specified where the page index hint will be, as `footer` (by default) or `header`.
        Or you can input a `disabled` to get a text without page hint line
        :return: List of full page text
        """
        return RTextBase.join('\n', self.get_full_page_lines(hint_line=hint_line))

    @staticmethod
    def list_command_wrapper(target_node: AbstractNode) -> AbstractNode:
        """
        This wrapper will just attach page param nodes as its children,
        and the wrapped node will make this class able to get next/previous page command automatically
        :param target_node:
        :return:
        """
        old_method = target_node._on_visited

        def _on_visited(self: AbstractNode, context: CommandContext, *args, **kwargs) -> AbstractNode:
            context[LIST_COMMAND] = context.command_read
            return old_method(context, *args, **kwargs)

        target_node._on_visited = MethodType(_on_visited, target_node)

        target_node.then(
            Literal(PAGE_ARG).then(
                Integer(PAGE_NUM).redirects(target_node)
            )
        )
        target_node.then(
            Literal(ITEM_ARG).then(
                Integer(ITEM_PER_PAGE).redirects(target_node)
            )
        )
        return target_node

    @property
    def length(self):
        """
        :return: The length of the list
        """
        return len(self.__list)

    def __len__(self):
        return self.length
