import os

NAME = 'CalyxLib'
PACKAGE_NAME = 'calyx_lib'

VERSION = '0.1.0-alpha.6'
# Requires "" here to make regex work in publish action
VERSION_PYPI = "0.1.0a6"

GITHUB_URL = 'https://github.com/Lazy-Bing-Server/CalyxLib-Python'

SELF_PACKAGE_PATH = os.path.abspath(os.path.dirname(__file__))
LANGUAGE_FILE_SUFFIX = '.yml'
DEFAULT_LANGUAGE = 'en_us'

SELF_LANG_FOLDER = 'resources/lang'
DESCRIPTION = ("Alternative MCDReforged API for MCDR plugins that "
               "requires running in other environments")

