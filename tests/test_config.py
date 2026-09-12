"""Regression tests for configuration persistence."""

import json

import pytest

from photosleuth import config


def test_defaults_are_written_on_first_load(isolated_config):
    loaded = config.load_config()
    assert loaded["privacy"]["output_suffix"] == "_clean"
    assert config.config_path().is_file()


def test_partial_config_does_not_raise_keyerror(isolated_config):
    """A hand-edited config missing 'api_keys' used to crash set_api_key."""
    config.save_config({"privacy": {"overwrite": True}})
    config.set_api_key("google_vision", "abc123")
    assert config.get_api_key("google_vision") == "abc123"
    assert config.load_config()["privacy"]["overwrite"] is True


def test_corrupt_config_falls_back_to_defaults(isolated_config):
    config.config_path().parent.mkdir(parents=True, exist_ok=True)
    config.config_path().write_text("{ this is not json")
    loaded = config.load_config()
    assert loaded["default_search_engine"] == "google_vision"
    assert config.config_path().with_suffix(".json.bak").is_file()


def test_updating_one_section_keeps_the_others(isolated_config):
    """The old config_menu wrote a stale dict and silently dropped saved keys."""
    config.set_api_key("google_vision", "key-one")
    config.set_api_key("tineye", "key-two")
    config.set_privacy_options(output_suffix="_scrubbed", overwrite=True)
    config.set_default_engine("tineye")

    final = config.load_config()
    assert final["api_keys"]["google_vision"] == "key-one"
    assert final["api_keys"]["tineye"] == "key-two"
    assert final["privacy"]["output_suffix"] == "_scrubbed"
    assert final["default_search_engine"] == "tineye"


def test_unknown_engine_is_rejected(isolated_config):
    with pytest.raises(ValueError):
        config.set_api_key("bing", "x")
    with pytest.raises(ValueError):
        config.set_default_engine("bing")


def test_config_home_follows_env_override(isolated_config):
    assert config.config_home() == isolated_config


def test_saved_config_is_valid_json(isolated_config):
    config.set_api_key("google_vision", "abc")
    json.loads(config.config_path().read_text(encoding="utf-8"))
