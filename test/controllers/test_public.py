from bs4 import BeautifulSoup
from freezegun import freeze_time

from flask.testing import FlaskClient

from elekto import constants


def test_welcome(client: FlaskClient):
    response = client.get('/')
    assert response.status_code == 302
    assert response.headers['Location'] == '/app'


@freeze_time('2023-08-21')
def test_public_elections(client: FlaskClient, load_metadir):
    response = client.get('/elections')
    assert response.status_code == 200
    soup = BeautifulSoup(response.data.decode('utf-8'), 'html.parser')

    sorted_names = [
        'Select The Name of the Application',
        'Select our 2021 General Board Rep',
        '2021 Steering Committee Election',
    ]
    h2s = soup.find_all('h2', attrs={'class': 'title pb-0 mb-0'})

    for name, h2 in zip(sorted_names, h2s):
        assert h2.text.strip() == name

    # Filter on active elections
    response = client.get(f'/elections?status={constants.ELEC_STAT_COMPLETED}')
    assert response.status_code == 200
    soup = BeautifulSoup(response.data.decode('utf-8'), 'html.parser')

    h2s = soup.find_all('h2', attrs={'class': 'title pb-0 mb-0'})
    assert len(h2s) == 1
    assert h2s[0].text.strip() == '2021 Steering Committee Election'

def test_public_election(client: FlaskClient, load_metadir):
    response = client.get('/elections/name_the_app')
    assert response.status_code == 200
    soup = BeautifulSoup(response.data.decode('utf-8'), 'html.parser')
    title_text = soup.find('h1', attrs={'class': 'banner-title space-lr'}).text.strip()
    assert title_text == 'Select The Name of the Application'


def test_health_check(client: FlaskClient):
    response = client.get('/health')
    assert response.status_code == 200
