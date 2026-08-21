from colorlog import debug
from typing import Optional, Any, Union, Type, List
import logging
import json
import os
from pathlib import Path

from mcdreforged import RTextBase

# Debug configuration
DEBUG = True  # Set to True to enable debug logging

# Setup debug logger
def setup_debug_logger():
    if not DEBUG:
        return None

    # Create debug directory if it doesn't exist
    debug_dir = Path("./debug")
    debug_dir.mkdir(exist_ok=True)

    # Create logger
    logger = logging.getLogger("rtext_split_debug")
    logger.setLevel(logging.DEBUG)

    # Create file handler
    log_file = debug_dir / "rtext.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)

    # Create formatter
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)

    # Add handler to logger
    logger.addHandler(file_handler)

    return logger

# Initialize debug logger
debug_logger = setup_debug_logger()


class MetaString(str):
    meta: Optional[dict]

    def __new__(cls, *args, **kwargs):
        target = list(args).pop(0)
        if isinstance(target, dict) and 'text' in target.keys():
            meta = target.copy()
            text = meta.pop('text')

            inst = super().__new__(cls, text)
            inst.meta = meta
        else:
            inst = super().__new__(cls, target)
            inst.meta = None
        return inst

    def split(self, sep = None, maxsplit = -1):
        result = super().split(sep, maxsplit)
        for item in result:
            item = MetaString(item)
            item.meta = self.meta
            yield item

    def rsplit(self, sep = None, maxsplit = -1):
        result = super().rsplit(sep, maxsplit)
        for item in result:
            item = MetaString(item)
            item.meta = self.meta
            yield item

    def dump(self) -> Union[dict, str]:
        if self.meta is not None:
            result = self.meta.copy()
            result['text'] = str(self)
            return result
        else:
            return str(self)


class HeaderList(list):
    # Private singleton class
    class _Sentinel:
        def __repr__(self): return "<No Header>"

        def __bool__(self): return False

    _NO_HEADER = _Sentinel()

    def __init__(self, iterable=None):
        self.header = self._NO_HEADER
        super().__init__()
        if iterable is not None:
            self.extend(iterable)

    # --- Cut the header ---
    def append(self, item):
        if self.header is self._NO_HEADER:
            self.header = item
        else:
            super().append(item)

    def extend(self, iterable):
        it = iter(iterable)
        if self.header is self._NO_HEADER:
            try:
                self.header = next(it)
            except StopIteration:
                return
        super().extend(it)

    # --- Functions that can touch headers ---
    def __iter__(self):
        if self.header is not self._NO_HEADER:
            yield self.header
        yield from super().__iter__()

    def __repr__(self):
        h_info = "EMPTY" if self.header is self._NO_HEADER else repr(self.header)
        return f"HeaderList(header={h_info}, data={super().__repr__()})"

    # --- Class/Staticmethod ---
    @classmethod
    def from_nested(cls, data):
        if isinstance(data, list):
            return cls(cls.from_nested(x) for x in data)
        return data

    # --- Recursive split ---
    def recursive_split(self, split_callback, maxsplit=-1, right=False):
        # Cast all the nested lists into HeaderList
        root = self.from_nested(self)
        remaining = [maxsplit]

        def _create_fragment(source_obj):
            # Share header with a new HeaderList object
            new_obj = self.__class__()
            new_obj.header = source_obj.header
            return new_obj

        def _process(item):
            # Process Non-list element
            debug_logger.debug(f"Before split: {item}")
            if not isinstance(item, HeaderList):
                result = None
                if remaining[0] == 0:
                    result = [item]
                res = list(split_callback(item, remaining[0], right))
                debug_logger.debug(f"res: {res}")
                res_len = len(res)
                debug_logger.debug(f'len = {res_len}')
                if res_len > 1:
                    actual_splits = res_len - 1 if res_len >= 1 else res_len
                    debug_logger.debug(f'actual_splits = {res_len}')
                    if maxsplit >= 0:
                        remaining[0] = max(0, remaining[0] - actual_splits)
                    result = res
                if result is None:
                    result = [item]
                debug_logger.debug(f"Non-list item slices: {result}")
                return result
            else:
                # Process recursive element
                data_elements = list(super(HeaderList, item).__iter__())
                if right:
                    data_elements.reverse()

                # Attach header when the new list initializing
                chunks = [_create_fragment(item)]

                for element in data_elements:
                    sub_parts = _process(element)

                    chunks[-1].append(sub_parts[0])

                    # Split father item when its children split
                    if len(sub_parts) > 1:
                        for extra in sub_parts[1:]:
                            new_chunk = _create_fragment(item)
                            new_chunk.append(extra)
                            chunks.append(new_chunk)

                if right:
                    chunks.reverse()
                result = chunks

                debug_logger.debug(f"HeaderList slices: {result}")
                return result

        # Execute all the split
        final_chunks = _process(root)

        # Cast the result into HeaderList
        return self.__class__(final_chunks)


def split_single_element(item: Any, divider: str, max_split: int, from_right: bool):
    if isinstance(item, list):
        raise TypeError("List is not supported")
    debug_logger.debug("Current single element: {}".format(item))
    debug_logger.debug("max_split: {}".format(max_split))
    if from_right:
        slices = list(MetaString(item).rsplit(divider, maxsplit=max_split))
    else:
        slices = list(MetaString(item).split(divider, maxsplit=max_split))
    debug_logger.debug(f"Current slices: {slices}")
    result = [s.dump() if isinstance(s, MetaString) else s for s in slices]
    debug_logger.debug("Current result: {}".format(result))
    return result


def split_raw_json(item: Any, divider: str, max_split: int, from_right: bool = False):
    callback = lambda i, m, r: split_single_element(i, divider, m, r)
    if isinstance(item, list):
        item = HeaderList(item)
        return item.recursive_split(callback, max_split, from_right)
    else:
        return split_single_element(item, divider, max_split, from_right)


def split_rtext(any_rtext: RTextBase, divider: str, max_split: int = -1, from_right: bool = False):
    raw_json = any_rtext.to_json_object()

    # Debug logging: log raw_json before splitting
    if DEBUG and debug_logger:
        debug_logger.debug("=== SPLIT OPERATION START ===")
        debug_logger.debug(f"Input raw_json (before split): {json.dumps(raw_json, ensure_ascii=False, indent=2)}")
        debug_logger.debug(f"Divider: {repr(divider)}")
        debug_logger.debug(f"Max split: {max_split}")
        debug_logger.debug(f"From right: {from_right}")

    result = split_raw_json(raw_json, divider, max_split, from_right)
    
    # Debug logging: log result after splitting
    if DEBUG and debug_logger:
        debug_logger.debug("Output raw_json (after split + purge): ")
        for num, item in enumerate(result):
            debug_logger.debug(f"Output item {num}: {json.dumps(item, ensure_ascii=False)}")
        debug_logger.debug(f"Split count: {len(result)}")
        debug_logger.debug("=== SPLIT OPERATION END ===")
    
    for item in result:
        yield RTextBase.from_json_object(item)
