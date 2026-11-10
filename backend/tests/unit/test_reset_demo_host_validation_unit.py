from unittest.mock import MagicMock
import pytest

from backend.app.db.reset_demo import reset_and_seed_demo


def test_reset_demo_blocks_non_local_migration_host(monkeypatch):
    """
    Verifies reset_and_seed_demo immediately aborts with RuntimeError
    if the migration host is not 127.0.0.1 or localhost.
    """
    mock_m_url = MagicMock(database="ledgerline", host="192.168.1.150")
    mock_r_url = MagicMock(database="ledgerline", host="127.0.0.1")

    urls = [mock_m_url, mock_r_url]
    monkeypatch.setattr("backend.app.db.reset_demo.make_url", lambda uri: urls.pop(0))

    with pytest.raises(RuntimeError) as exc_info:
        reset_and_seed_demo()

    assert "Destructive reset blocked: Target host must be local (127.0.0.1/localhost)" in str(exc_info.value)
    assert "192.168.1.150" in str(exc_info.value)


def test_reset_demo_blocks_non_local_runtime_host(monkeypatch):
    """
    Verifies reset_and_seed_demo immediately aborts with RuntimeError
    if the runtime host is not 127.0.0.1 or localhost.
    """
    mock_m_url = MagicMock(database="ledgerline", host="127.0.0.1")
    mock_r_url = MagicMock(database="ledgerline", host="db.production.internal")

    urls = [mock_m_url, mock_r_url]
    monkeypatch.setattr("backend.app.db.reset_demo.make_url", lambda uri: urls.pop(0))

    with pytest.raises(RuntimeError) as exc_info:
        reset_and_seed_demo()

    assert "Destructive reset blocked: Target host must be local (127.0.0.1/localhost)" in str(exc_info.value)
    assert "db.production.internal" in str(exc_info.value)


def test_reset_demo_blocks_non_ledgerline_database(monkeypatch):
    """
    Verifies reset_and_seed_demo immediately aborts if target database is not 'ledgerline'.
    """
    mock_m_url = MagicMock(database="ledgerline_test", host="127.0.0.1")
    mock_r_url = MagicMock(database="ledgerline_test", host="127.0.0.1")

    urls = [mock_m_url, mock_r_url]
    monkeypatch.setattr("backend.app.db.reset_demo.make_url", lambda uri: urls.pop(0))

    with pytest.raises(RuntimeError) as exc_info:
        reset_and_seed_demo()

    assert "Target database must be 'ledgerline'" in str(exc_info.value)


def test_reset_demo_passes_host_validation_for_local_hosts(monkeypatch):
    """
    Verifies reset_and_seed_demo accepts local hosts (127.0.0.1 and localhost)
    and proceeds past target validation.
    """
    mock_m_url = MagicMock(database="ledgerline", host="localhost")
    mock_r_url = MagicMock(database="ledgerline", host="127.0.0.1")

    urls = [mock_m_url, mock_r_url]
    monkeypatch.setattr("backend.app.db.reset_demo.make_url", lambda uri: urls.pop(0))

    backup_invoked = False

    def fake_execute_backup():
        nonlocal backup_invoked
        backup_invoked = True
        raise StopIteration("Validation passed, safely halting before backup execution")

    monkeypatch.setattr("backend.app.db.reset_demo.execute_backup", fake_execute_backup)

    with pytest.raises(StopIteration) as exc_info:
        reset_and_seed_demo()

    assert "Validation passed" in str(exc_info.value)
    assert backup_invoked is True
