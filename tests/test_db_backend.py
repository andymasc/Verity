"""Retry behaviour of the Neon-tolerant PostgreSQL backend."""

from unittest.mock import patch

import pytest
from django.db.backends.postgresql import base as postgresql_base

from Verity.db.backends.postgresql import base as neon_base

OperationalError = postgresql_base.Database.OperationalError

DNS_TEMPORARY = (
    'could not translate host name "db.example.neon.tech" to '
    "address: Temporary failure in name resolution\n"
)
DNS_UNKNOWN = (
    'could not translate host name "db.example.neon.tech" to address: Name or service not known\n'
)


def _connect(side_effect):
    wrapper = neon_base.DatabaseWrapper.__new__(neon_base.DatabaseWrapper)
    with (
        patch.object(
            postgresql_base.DatabaseWrapper, "get_new_connection", side_effect=side_effect
        ) as parent,
        patch.object(neon_base.time, "sleep") as sleep,
    ):
        try:
            return wrapper.get_new_connection({}), parent, sleep
        except OperationalError as exc:
            exc.parent, exc.sleep = parent, sleep
            raise


def test_retries_temporary_dns_failure_then_connects():
    connection = object()

    result, parent, sleep = _connect([OperationalError(DNS_TEMPORARY), connection])

    assert result is connection
    assert parent.call_count == 2
    sleep.assert_called_once_with(neon_base._BASE_BACKOFF)


def test_gives_up_after_max_attempts_on_persistent_dns_failure():
    with pytest.raises(OperationalError) as excinfo:
        _connect(OperationalError(DNS_TEMPORARY))

    assert excinfo.value.parent.call_count == neon_base._MAX_ATTEMPTS
    assert excinfo.value.sleep.call_count == neon_base._MAX_ATTEMPTS - 1


def test_unknown_hostname_raises_without_retry():
    with pytest.raises(OperationalError) as excinfo:
        _connect(OperationalError(DNS_UNKNOWN))

    assert excinfo.value.parent.call_count == 1
    excinfo.value.sleep.assert_not_called()
