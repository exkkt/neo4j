"""Exercise the generated connection cell without credentials or a live database."""
from types import SimpleNamespace
from unittest.mock import MagicMock
import traceback

import pytest
from neo4j.exceptions import AuthError, ServiceUnavailable
from scripts.build_notebooks import connection


@pytest.fixture
def cell():
    source = ''.join(connection()[1]['source'])
    namespace = {}
    exec(source.split('\ndriver = connect_hidden()')[0], namespace)
    namespace['hidden_setting'] = lambda name: {
        'NEO4J_URI': 'neo4j+s://example.invalid',
        'NEO4J_USERNAME': 'test-user', 'NEO4J_PASSWORD': 'dummy-test-only',
    }[name]
    return namespace


@pytest.mark.parametrize('error, category', [
    (AuthError('dummy-test-only'), '[AUTH]'),
    (ServiceUnavailable('dummy-test-only'), '[UNREACHABLE]'),
    (ValueError('dummy-test-only'), '[CONFIG]'),
    (RuntimeError('dummy-test-only'), '[NEO4J_OTHER]'),
])
def test_connection_failure_is_actionable_and_redacted(cell, error, category):
    driver = MagicMock()
    driver.verify_connectivity.side_effect = error
    cell['GraphDatabase'] = SimpleNamespace(driver=MagicMock(return_value=driver))
    with pytest.raises(RuntimeError) as result:
        cell['connect_hidden']()
    rendered = ''.join(traceback.format_exception(result.value))
    assert category in str(result.value)
    assert 'dummy-test-only' not in rendered
    driver.close.assert_called_once()


def test_connection_checks_default_database(cell):
    driver = MagicMock()
    cell['GraphDatabase'] = SimpleNamespace(driver=MagicMock(return_value=driver))
    assert cell['connect_hidden']() is driver
    driver.session.assert_called_once_with(database=None)
    driver.session.return_value.__enter__.return_value.run.assert_called_once_with('RETURN 1 AS ok')
    driver.close.assert_not_called()


def test_console_url_is_rejected_before_connecting(cell):
    cell['hidden_setting'] = lambda name: 'https://console.neo4j.io/'
    factory = MagicMock()
    cell['GraphDatabase'] = SimpleNamespace(driver=factory)
    with pytest.raises(RuntimeError, match=r'\[CONFIG\]'):
        cell['connect_hidden']()
    factory.assert_not_called()
