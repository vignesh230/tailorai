import pytest
from pydantic import ValidationError

from app.config import DEFAULT_JWT_SECRET, Settings


def test_default_secret_in_production_raises():
    with pytest.raises(ValidationError):
        Settings(environment="production", jwt_secret=DEFAULT_JWT_SECRET)


def test_short_secret_in_production_raises():
    with pytest.raises(ValidationError):
        Settings(environment="production", jwt_secret="too-short")


def test_real_secret_in_production_passes():
    settings = Settings(environment="production", jwt_secret="a" * 32)
    assert settings.jwt_secret == "a" * 32


def test_default_secret_in_development_is_allowed():
    settings = Settings(environment="development", jwt_secret=DEFAULT_JWT_SECRET)
    assert settings.jwt_secret == DEFAULT_JWT_SECRET
