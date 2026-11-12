"""Tests for the Neon PostgreSQL backend's connect retry."""

from unittest.mock import patch

import pytest

from Verity.db.backends.postgresql import base as neon_base

OperationalError = neon_base.postgresql_base.Database.OperationalError

DNS_ERROR = ('could not translate host name "ep-example-pooler.neon.tech" '
             "to address: Temporary failure in name resolution\n")


def _connect_with(side_effect):
    wrapper = neon_base.DatabaseWrapper.__new__(neon_base.DatabaseWrapper)
    parent = neon_base.postgresql_base.DatabaseWrapper
    with (
            patch.object(parent, "get_new_connection",
                         side_effect=side_effect) as mock_connect,
            patch.object(neon_base.time, "sleep") as mock_sleep,
    ):
        try:
            return wrapper.get_new_connection({}), mock_connect, mock_sleep
        except OperationalError as exc:
            return exc, mock_connect, mock_sleep


def test_retries_dns_failure_then_connects():
    result, mock_connect, mock_sleep = _connect_with(
        [OperationalError(DNS_ERROR)] * 3 + ["conn"])
    assert result == "conn"
    assert mock_connect.call_count == 4
    assert [c.args[0] for c in mock_sleep.call_args_list] == [0.5, 1.0, 2.0]


def test_retry_window_covers_five_second_outage():
    result, mock_connect, mock_sleep = _connect_with(
        OperationalError(DNS_ERROR))
    assert isinstance(result, OperationalError)
    assert mock_connect.call_count == neon_base._MAX_ATTEMPTS
    total_sleep = sum(c.args[0] for c in mock_sleep.call_args_list)
    assert total_sleep >= 5


@pytest.mark.parametrize("message", [
    'password authentication failed for user "verity"',
    "SSL error: certificate verify failed",
])
def test_non_transient_error_raises_immediately(message):
    result, mock_connect, mock_sleep = _connect_with(OperationalError(message))
    assert isinstance(result, OperationalError)
    assert mock_connect.call_count == 1
    mock_sleep.assert_not_called()
