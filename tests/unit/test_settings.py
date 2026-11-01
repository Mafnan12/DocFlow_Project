from docflow.settings import Settings, get_settings


def test_settings_load():
    settings = get_settings()
    assert settings is not None
    assert settings.APP_ENV in ("development", "test", "production")


def test_yaml_configs_loaded():
    settings = get_settings()
    # Check pipeline yaml
    assert "image/jpeg" in settings.pipeline.files.allowed_types
    assert settings.pipeline.ocr.engine in ("paddle", "tesseract", "doctr")

    # Check validation yaml
    assert settings.validation.tolerance.absolute == "0.05"
    assert "IDR" in settings.validation.tolerance.zero_decimal_currencies
    assert "vendor_name" in settings.validation.critical_fields

    # Check confidence yaml
    assert settings.confidence.field_threshold == 0.70
    assert settings.confidence.signals.agreement_weight == 0.45

    # Check llm yaml
    assert "fast" in settings.llm.roles
    assert "vision" in settings.llm.roles

    # Check demo yaml
    assert len(settings.demo.clients) >= 3
    client_ids = [c.client_id for c in settings.demo.clients]
    assert "kopi-corner" in client_ids


def test_settings_isolated_instance():
    s = Settings()
    s.load_yaml_configs()
    assert s.pipeline.files.max_file_mb == 10
