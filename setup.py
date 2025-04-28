import os

from setuptools import setup, find_packages

from calyx_lib import constants


here = os.path.abspath(os.path.dirname(__file__))

with open(os.path.join(here, 'requirements.txt')) as f:
    REQUIRED = list(filter(None, map(str.strip, f)))
    print('REQUIRED = {}'.format(REQUIRED))

with open(os.path.join(here, 'README.md'), encoding='utf8') as f:
    LONG_DESCRIPTION = f.read()

CLASSIFIERS = [
    # https://pypi.org/classifiers/
    'License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)',
    'Operating System :: OS Independent',
    'Programming Language :: Python',
    'Programming Language :: Python :: 3',
    # 'Programming Language :: Python :: 3.8',
    'Programming Language :: Python :: 3.9',
    'Programming Language :: Python :: 3.10',
    'Programming Language :: Python :: 3.11',
    'Programming Language :: Python :: 3.12',
    'Programming Language :: Python :: 3.13',
]

setup(
    name=constants.PACKAGE_NAME,
    version=constants.VERSION_PYPI,
    description=constants.DESCRIPTION,
    long_description=LONG_DESCRIPTION,
    long_description_content_type='text/markdown',
    url=constants.GITHUB_URL,
    author_email="ra1ny_yuki@outlook.com",
    author="Ra1ny_Yuki",
    classifiers=CLASSIFIERS,
    install_requires=REQUIRED,
    packages=find_packages(exclude=['tests', '*.tests', '*.tests.*', 'tests.*'])
)
