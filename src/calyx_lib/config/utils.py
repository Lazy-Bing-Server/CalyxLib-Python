from typing import List, Any, Callable, Optional, TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from pydantic.fields import FieldInfo

"""
Not API
"""


def get_field_from_nested_model(
        model: BaseModel,
        keys: List[str],
        field_filter: "Callable[[FieldInfo], bool]" = lambda x: True
) -> Optional["FieldInfo"]:
    father_model = get_value_from_nested_model(
        model, keys[:-1], field_filter=field_filter
    )
    if isinstance(father_model, BaseModel):
        field = father_model.__class__.model_fields.get(keys[-1])
        if field is not None and field_filter(field):
            return field
    return None


def get_value_from_nested_model(
        model: BaseModel,
        keys: List[str],
        default: Any = None,
        field_filter: "Callable[[FieldInfo], bool]" = lambda x: True
) -> Any:
    current_model = model
    key_list = keys.copy()
    while True:
        if len(key_list) == 0:
            return current_model
        current_key = key_list.pop(0)
        if isinstance(current_model, BaseModel):
            target_field = current_model.__class__.model_fields.get(current_key)
            if target_field is not None and field_filter(target_field):
                current_model = getattr(current_model, current_key)
            else:
                return default
        else:
            return default


def set_value_to_nested_model(
        model: BaseModel, keys: List[str], value: Any,
        field_filter: "Callable[[FieldInfo], bool]" = lambda x: True
) -> bool:
    key_list = keys.copy()
    target_key = key_list.pop()
    father_model = get_value_from_nested_model(model, key_list, field_filter=field_filter)
    if isinstance(father_model, BaseModel):
        target_field = father_model.__class__.model_fields.get(target_key)
        if target_field is None or not field_filter(target_field):
            return False
        try:
            setattr(father_model, target_key, value)
        except:
            return False
    return True