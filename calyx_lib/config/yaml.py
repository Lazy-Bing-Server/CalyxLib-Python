import copy
import dataclasses
from io import StringIO
from typing import Any, Literal, Union, List, Dict, Iterable, Optional, IO

from mcdreforged.api.rtext import RTextBase
from ruamel.yaml import YAML, CommentedMap, RoundTripRepresenter

from calyx_lib.typing import MessageText, CommentTextWrapper, Subscriptable


class ConfigComment:
    def __init__(
        self,
        text: MessageText,
        loc: Literal['before', 'eol'] = 'before',
        wrapper: CommentTextWrapper = lambda text: text,
        priority: Union[int, float] = 1000,
        ignore_global_wrapper: bool = False
    ):
        self.text = text
        self.loc = loc
        self.wrapper = wrapper
        self.priority = priority
        self.ignore_global_wrapper = ignore_global_wrapper

    def get_text(self):
        return self.wrapper(self.text)

    @property
    def is_before(self):
        return self.loc == 'before'

    @property
    def is_eol(self):
        return self.loc == "eol"

    def copy(self):
        return copy.copy(self)


@dataclasses.dataclass
class CommentContext:
    key_comments: Dict[tuple, List[ConfigComment]]
    global_wrapper: CommentTextWrapper
    headlines: List[ConfigComment]
    eof: List[ConfigComment]

    def add_comment(self, key: tuple, comment: ConfigComment):
        if key not in self.key_comments.keys():
            self.key_comments[key] = []
        self.key_comments[key].append(comment)

    def __get_comment_text(self, comment: ConfigComment):
        text = comment.get_text()
        if not comment.ignore_global_wrapper:
            text = self.global_wrapper(text)
        return RTextBase.from_any(text).to_plain_text()

    def apply_comment_to_stream(
            self, comments: List[ConfigComment], stream: IO, indent: int = 0
    ):
        raw_text_lines = []
        for comment in comments:
            raw_text_lines += list(self.__get_comment_text(comment).splitlines())

        line_prefix = indent * ' ' + "# "
        comment_lines = []
        for line in raw_text_lines:
            if str(line).strip() != '':
                comment_lines.append(line_prefix + line)
            else:
                comment_lines.append(line)
        if comment_lines:
            stream.write('\n'.join(comment_lines) + '\n\n')

    def apply_comment_to_carrier(self, carrier: "CommentCarrier"):
        for key, comments in self.key_comments.items():
            for comment in comments:
                carrier.set_comment_to_nested_key(key, comment)


class CommentCarrier:
    def __init__(self, data: dict):
        self.data = data
        self.comments = {}  # type: Dict[str, List[ConfigComment]]
        self.global_wrapper = lambda text: text

    def get_comment_text(self, comment: ConfigComment):
        text = comment.get_text()
        if not comment.ignore_global_wrapper:
            text = self.global_wrapper(text)
        return RTextBase.from_any(text).to_plain_text()

    def to_commented_map(self):
        data = CommentedMap(self.data)

        for key, comments in self.comments.items():
            before_comments = []
            for cmt in sorted(comments, key=lambda item: item.priority):
                if cmt.is_before:
                    before_comments.append(self.get_comment_text(cmt))
                elif cmt.is_eol:
                    data.yaml_add_eol_comment(
                        key=key, comment=self.get_comment_text(cmt)
                    )
            if before_comments:
                before_comments.reverse()
                before_comment_text = '\n'.join(before_comments)
                data.yaml_set_comment_before_after_key(
                    key=key, before=before_comment_text
                )
        return data

    def set_comment_to_nested_key(
            self, key: Iterable[str], comment: ConfigComment
    ):
        key_list = list(key)
        data: Subscriptable = self.data
        comment = comment.copy()
        while True:
            current_key = key_list.pop(0)
            try:
                current_value = data[current_key]
                if not key_list:
                    if current_key not in self.comments.keys():
                        self.comments[current_key] = []
                    self.comments[current_key].append(comment)
                    break
                elif isinstance(current_value, CommentCarrier):
                    current_value.set_comment_to_nested_key(
                        key_list, comment
                    )
                    break
                else:
                    data = current_value
            except:
                break

    @staticmethod
    def represent(representer: RoundTripRepresenter, item: "CommentCarrier"):
        return representer.represent_dict(item.to_commented_map())

    def __iter__(self):
        for item in self.data.items():
            yield item


def get_yaml():
    yaml = YAML(typ='rt')
    yaml.width = 1048576
    yaml.allow_unicode = True
    yaml.representer.add_representer(CommentCarrier, CommentCarrier.represent)
    return yaml


def any_to_yaml(any_item: Any):
    yaml = get_yaml()
    with StringIO() as stream:
        yaml.dump(any_item, stream)
        stream.seek(0)
        return stream.read().strip()


# Thanks to gemini
def adjust_comment_indentation(yaml_string: str):
    lines = list(yaml_string.strip().splitlines())
    lines.reverse()
    adjusted_lines = []
    indentation_level = 0
    indentation_char = ' '  # Assuming spaces for indentation

    for i, line in enumerate(lines):
        stripped_line = line.lstrip()
        current_indentation = len(line) - len(stripped_line)

        if stripped_line.startswith('#'):
            # It's a comment
            if i > 0:
                # Get the indentation of the previous non-comment line
                prev_indentation = indentation_level * len(indentation_char)
                adjusted_lines.append(
                    f"{indentation_char * prev_indentation}{stripped_line}"
                )
            else:
                # First line comment, keep its original indentation
                adjusted_lines.append(line)
        else:
            # It's a non-comment line, update the indentation level
            indentation_level = current_indentation // len(indentation_char)
            adjusted_lines.append(line)

    adjusted_lines.reverse()
    return '\n'.join(adjusted_lines)
