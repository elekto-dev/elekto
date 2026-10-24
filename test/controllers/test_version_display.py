import importlib
import importlib.metadata

import pytest
from bs4 import BeautifulSoup
from flask.testing import FlaskClient
from freezegun import freeze_time
from pytest_mock import MockerFixture

import elekto.version
from .utils import provision_session


@pytest.fixture(autouse=True)
def restore_version_module():
    yield
    importlib.reload(elekto.version)


@freeze_time('2026-03-01')
def test_sidebar_shows_version_and_copyright_range(client: FlaskClient, mocker: MockerFixture):
    # The context processor reads the name bound in elekto/__init__.py at request time.
    mocker.patch('elekto.__version__', '1.2.3')
    provision_session(client, 'token')

    response = client.get('/app')

    assert response.status_code == 200
    footer = BeautifulSoup(response.data, 'html.parser').select_one('.sidebar__footer')
    text = ' '.join(footer.get_text().split())
    assert text == 'Elekto v1.2.3 — copyright 2020–2026 © elekto'


def test_version_falls_back_when_package_not_installed(mocker: MockerFixture):
    mocker.patch('importlib.metadata.version', side_effect=importlib.metadata.PackageNotFoundError('elekto'))

    importlib.reload(elekto.version)

    assert elekto.version.__version__ == '0.0.0'
