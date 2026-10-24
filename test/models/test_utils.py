import os
from unittest import mock

import pytest

from config import DATABASE_URL
from elekto.models.utils import (
    parse_yaml,
    parse_yaml_from_string,
    extract_candidate_info,
    extract_candidate_description,
    sync, parse_md,
)
from elekto.models.sql import Election, migrate
from elekto.models import meta


def test_parse_yaml_not_found():
    assert parse_yaml('nonexistent.yaml') is None


def test_parse_yaml(metadir):
    path = metadir / 'elections' / 'name_the_app' / 'election.yaml'
    assert parse_yaml(path)['name'] == 'Select The Name of the Application'


def test_parse_yaml_from_string():
    text = (
        'foo:\n'
        '  - bar\n'
        '  - baz\n'
        '  - 42\n'
    )
    assert parse_yaml_from_string(text) == {
        'foo': ['bar', 'baz', 42],
    }


@pytest.fixture
def candidate_md(metadir) -> str:
    with open(metadir / 'elections' / 'name_the_app' / 'candidate-notcivs.md', 'r') as f:
        return f.read()


def test_extract_candidate_info(candidate_md: str):
    info = extract_candidate_info(candidate_md)
    assert info == {
        'name': 'Not CIVS',
        'ID': 'notcivs',
        'info': [
            {
                'Language': 'English',
            }
        ]
    }


def test_extract_candidate_info_array_format():
    # This is the old/non-standard format, but we should still test for it for backwards compatibility.
    """Test parsing candidate info with array format"""
    candidate_md_array = """-------------------------------------------------------------
name: Jane Doe
ID: jdoe
info:
  - employer: Example Corp
  - slack: jane.doe
-------------------------------------------------------------

## Bio

Sample bio content here.
"""
    info = extract_candidate_info(candidate_md_array)
    assert info == {
        'name': 'Jane Doe',
        'ID': 'jdoe',
        'info': [
            {'employer': 'Example Corp'},
            {'slack': 'jane.doe'}
        ]
    }


def test_extract_candidate_info_object_format():
    # This is the proper yaml format
    """Test parsing candidate info with object format"""
    candidate_md_object = """-------------------------------------------------------------
name: John Smith
ID: jsmith
info:
  employer: Tech Company
  slack: john.smith
-------------------------------------------------------------

## Bio

Sample bio content here.
"""
    info = extract_candidate_info(candidate_md_object)
    assert info == {
        'name': 'John Smith',
        'ID': 'jsmith',
        'info': {
            'employer': 'Tech Company',
            'slack': 'john.smith'
        }
    }


def test_extract_candidate_description(candidate_md):
    assert extract_candidate_description(candidate_md) == (
        '## Reason for Name\n\n'
        'This name emphasizes that we are NOT CIVS, for folks who have PTSD from running large elections on CIVS.\n\n'
        '## Availability Search\n\n'
        'I didn\'t even try, really.'
    )


def test_sync(metadir):
    """
    Sync the meta dir, asserting all expected content is loaded into the database.

    Elections that were in the database but are no longer in the meta must be removed.
    Elections that are not in the database but are present in the meta must be added.
    """

    session = migrate(DATABASE_URL)

    # Elections table should be empty at first.
    assert session.query(Election).count() == 0

    assert len(meta.Election.all()) == 3
    sync(session, meta.Election.all())

    # Database now should hold three elections.
    election_keys = [
        raw[0]
        for raw in session.query().with_entities(Election.key).all()
    ]
    assert election_keys == ['2021---GB', '2021---TOC', 'name_the_app']

    # Change the name_the_app folder name, causing that election to be dropped from the database while the new name is
    # added as a new election.
    os.rename(
        metadir / 'elections' / 'name_the_app',
        metadir / 'elections' / 'name_the_website',
    )

    sync(session, meta.Election.all())
    assert len(meta.Election.all()) == 3

    election_keys = [
        raw[0]
        for raw in session.query().with_entities(Election.key).all()
    ]
    assert election_keys == ['2021---GB', '2021---TOC', 'name_the_website']


@mock.patch('sqlalchemy.orm.scoping.scoped_session.query')
def test_sync_deletion_exception(query_mock, metadir):
    query_mock.side_effect = Exception

    session = migrate(DATABASE_URL)
    logs = sync(session, meta.Election.all())
    assert ' x Error while querying to the database.\n' in logs


@mock.patch('sqlalchemy.orm.scoping.scoped_session.add')
def test_sync_add_exception(add_mock, metadir):
    add_mock.side_effect = Exception

    session = migrate(DATABASE_URL)
    logs = sync(session, meta.Election.all())
    assert ' x while adding {} in the database, application ran in to error.\n' in logs


def test_parse_md(metadir):
    path = metadir / 'elections' / 'name_the_app' / 'election_desc.md'
    assert '<h1>Help Name the App!</h1>' in parse_md(path)


def test_parse_md_file_error(metadir):
    path = metadir / 'elections' / 'name_the_app' / 'does_not_exist.md'
    assert parse_md(path) is None


@mock.patch('elekto.models.utils.open')
def test_parse_md_generic_error(open_mock):
    open_mock.side_effect = Exception
    assert parse_md('') == 'Markdown format not Correct'


def candidate_md_with_info(info_block: str) -> str:
    sep = '-' * 61
    return f'{sep}\nname: Jane Doe\nID: jdoe\n{info_block}{sep}\n\n## Bio\n'


@pytest.mark.parametrize('info_block,expected', [
    ('info:\n  slack: @jdoe\n', {'slack': '@jdoe'}),
    ('info:\n  - slack: @jdoe\n', [{'slack': '@jdoe'}]),
    ("info:\n  slack: '@jdoe'\n", {'slack': '@jdoe'}),
    ('info:\n  slack: "@jdoe"\n', {'slack': '@jdoe'}),
    ('info:\n  slack: jdoe@example.com\n', {'slack': 'jdoe@example.com'}),
])
def test_extract_candidate_info_at_sign(info_block, expected):
    info = extract_candidate_info(candidate_md_with_info(info_block))
    assert info['info'] == expected


def test_extract_candidate_info_malformed_still_raises():
    with pytest.raises(Exception):
        extract_candidate_info(candidate_md_with_info('info:\n  slack: [unclosed\n'))
