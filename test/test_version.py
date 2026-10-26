import importlib
from importlib.metadata import PackageNotFoundError
from unittest import mock

import pytest

import elekto.version


@pytest.fixture(autouse=True)
def restore_version():
    yield
    importlib.reload(elekto.version)


def test_version_comes_from_package_metadata():
    with mock.patch('importlib.metadata.version', return_value='0.8.0'):
        assert importlib.reload(elekto.version).__version__ == '0.8.0'


def test_version_falls_back_when_not_installed():
    with mock.patch('importlib.metadata.version', side_effect=PackageNotFoundError('elekto')):
        assert importlib.reload(elekto.version).__version__ == '0.0.0+unknown'
