import os

from mr_auto_reviewer.main import _sanitize_invalid_tls_env


def test_sanitize_invalid_tls_bundle_paths(monkeypatch, tmp_path):
    missing = tmp_path / "missing-ca.pem"
    missing_path = str(missing)
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", missing_path)
    monkeypatch.setenv("SSL_CERT_FILE", missing_path)
    monkeypatch.setenv("CURL_CA_BUNDLE", missing_path)

    _sanitize_invalid_tls_env()

    assert os.getenv("REQUESTS_CA_BUNDLE") is None
    assert os.getenv("SSL_CERT_FILE") is None
    assert os.getenv("CURL_CA_BUNDLE") is None


def test_keep_valid_tls_bundle_paths(monkeypatch, tmp_path):
    valid = tmp_path / "ca.pem"
    valid.write_text("dummy-ca", encoding="utf-8")
    valid_path = str(valid)
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", valid_path)

    _sanitize_invalid_tls_env()

    assert os.getenv("REQUESTS_CA_BUNDLE") == valid_path
