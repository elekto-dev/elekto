from unittest import mock

from bs4 import BeautifulSoup
from flask.testing import FlaskClient
from freezegun import freeze_time

from .utils import provision_session


def title(response) -> str:
    return BeautifulSoup(response.data, 'html.parser').find('title').text.strip()


def test_unknown_path_returns_404(client: FlaskClient):
    response = client.get('/no-such-page')

    assert response.status_code == 404
    assert title(response) == '404 Not Found | Elekto'


def test_unauthorized_returns_401(client: FlaskClient, load_metadir):
    provision_session(client, token='...')  # signed in, but not an election officer

    response = client.get('/app/elections/name_the_app/admin/')

    assert response.status_code == 401
    assert title(response) == '401 - Unauthorized | Elekto'


@mock.patch('elekto.models.meta.Election.candidate', side_effect=RuntimeError('boom'))
def test_unhandled_exception_returns_500(candidate_mock, client: FlaskClient, load_metadir):
    provision_session(client, token='...')

    response = client.get('/app/elections/name_the_app/candidates/e6n')

    assert response.status_code == 500
    assert title(response) == '500 - Server Error | Elekto'


@freeze_time('2023-08-04')
def test_missing_csrf_token_returns_400(client: FlaskClient, load_metadir):
    provision_session(client, token='...', username='kalkayan')

    response = client.post('/app/elections/name_the_app/vote', data={'password': ''})

    assert response.status_code == 400
    assert title(response) == '400 - CSRF Error | Elekto'
    assert 'Bad Request' in response.data.decode('utf8')
