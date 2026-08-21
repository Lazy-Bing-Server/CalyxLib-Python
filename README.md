# CalyxLib-Python
Alternative MCDReforged API for MCDR plugins that requires running in other environments

## Introduction

The core of CalyxLib is `BlossomBaseInterface`, you need to inherit 
it and create an instance to use a lot of feature of CalyxLib.
In MCDReforged, use its subclass `BlossomMCDRInterface` instead.

### Config

#### Config Serialization & Comment

- `CommentedModel` / `ConfigComment`

Subclass of `pydantic.BaseModel`. Attach comments to YAML file 
by simply annotate fields from these models with `Annotated[..., ConfigComment(...)]`

- `BlossomBaseInterface.load_config()` & `BlossomBaseInterface.save_config()`

These 2 methods can load & save the `pydantic.BaseModel` / `CommentedModel` from/into the YAML file.
Add header or footer with `CommentContext`. Pass the `CommentContext` instance
to these 2 methods to add header and footer.

- `InGameConfigItemMark`

Add this in the annotation `Annotated` type to mark a field that this item is available to be configured in game,
and you can configure how this item info displayed ingame here. 

Usage: `Annotated[..., InGameConfigItem(...)]`

- `ConfigKeyNode`

Subclass of `mcdreforged.api.command.QuotableText`

Automatically check the item that annotated with `InGameConfigItemMark`

All the config API Basic usage: 

``` 
from calyx_lib.config import CommentedModel, InGameConfigMark, ConfigKeyNode, ConfigComment, ConfigComment

def get_ingame_mark(value_suggester: Union[
        Callable[["BlossomBaseInterface", List[str], "FieldInfo"], Iterable[Any]],
        Callable[["BlossomBaseInterface", List[str]], Iterable[Any]],
        Callable[["BlossomBaseInterface"], Iterable[Any]],
        Callable[[], Iterable[Any]],
    ], max_amount: int = 3):
    return InGameConfigItemMark(
        item_display_name_getter=lambda cbi, keys: cbi.rtr(
            f'calyx_lib_example_plugin.config.{".".join(keys)}.title'
        ) + ' ({})'.format('.'.join(keys)),
        item_description_getter=lambda cbi, keys: cbi.rtr(
            f'calyx_lib_example_plugin.config.{".".join(keys)}.desc'
        ),
        value_suggester=value_suggester,
        suggested_values_max_amount=max_amount,
    )


universal_comment = ConfigComment(
    text_getter=lambda cbi, keys: cbi.rtr(f"calyx_lib_example_plugin.config.{'.'.join(keys)}.desc")
)

# TODO: Serialize into visual strings for ingame
force_string = PlainSerializer(lambda v: str(v))


class Config(CommentedModel):
    prefixes: Annotated[Union[str, List[str]], get_ingame_mark(lambda: []), universal_comment, force_string] = "!!clep"
    permission: Annotated[int, get_ingame_mark(lambda: [0, 1, 2, 3, 4], 5), universal_comment, force_string] = 4
    default_page_size: Annotated[Blankable[int], get_ingame_mark(lambda: [10, 15, 20]), universal_comment, force_string] = BLANK
    verbose: Optional[bool] = None

CONFIG_FILE = 'config.yml'

class AnyPlugin(BlossomMCDRInterface):
    def __init__():
        super().__init__()
        self.config = self.load_config(CONFIG_FILE, Config)

    def on_load(server: PluginServerInterface, prev_module):
        self.server.register_command(
            Literal('!!any_command').then(
                ConfigKeyNode('config_key').bind_default_methods(self, CONFIG_FILE)
            )
        )
```
