from app.core.errors import AuthError, ErrorClass, FatalPersistenceError, SchemaError, classify_error


def test_timeout_is_recoverable():
    assert classify_error(TimeoutError()) == ErrorClass.RECOVERABLE


def test_connection_is_recoverable():
    assert classify_error(ConnectionError()) == ErrorClass.RECOVERABLE


def test_auth_is_not_recoverable():
    assert classify_error(AuthError()) == ErrorClass.AUTH


def test_schema_error():
    assert classify_error(SchemaError()) == ErrorClass.SCHEMA


def test_fatal_persistence():
    assert classify_error(FatalPersistenceError()) == ErrorClass.FATAL
