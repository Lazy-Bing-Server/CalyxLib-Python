import json

from typing import Any, Optional, List
from io import StringIO
from ruamel import yaml

from pydantic import ValidationError

from calyx_lib.config import ConfigModel, BLANK, Blankable


class J:
    pass


class ThirdField(ConfigModel):
    primary: int = 1


class Config(ConfigModel):
    first_field: Optional[str] = None
    second_field: Blankable[str] = BLANK
    """
    Yet another field
    """
    third_field: List[ThirdField] = []


class DebugEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        try:
            return super().default(o)
        except Exception:
            return str(o)


with StringIO() as stream:
    try:
        summary_ = ValidationContext(policy='raise')
        model = Config.model_validate({'second_field': "1", 'third_field': [{'primary': J}]}, context=summary_)
        yaml.YAML().dump(model.model_dump(exclude_none=True), stream)
    except ValidationError as e:
        print(e.errors())
    print(summary_.errors)
    stream.seek(0)
    print(stream.read())