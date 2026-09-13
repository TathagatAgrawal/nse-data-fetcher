"""Tests for the persistent download/lists folder settings."""

from pathlib import Path

import pytest

import settings


@pytest.fixture(autouse=True)
def isolated_settings_path(tmp_path, monkeypatch):
    """Point settings.py at a settings.json under tmp_path instead of the real Documents folder."""
    monkeypatch.setattr(settings, "SETTINGS_PATH", tmp_path / "NSE Data Fetcher" / "settings.json")


def test_download_folder_defaults_to_documents_when_unset():
    """With no settings file, the download folder falls back to the OS Documents folder."""
    assert settings.get_download_folder() == settings.default_documents_dir()


def test_lists_folder_defaults_to_app_subfolder_when_unset():
    """With no settings file, the lists folder falls back to Documents/NSE Data Fetcher."""
    assert settings.get_lists_folder() == settings.default_documents_dir() / "NSE Data Fetcher"


def test_set_and_get_download_folder_round_trips(tmp_path):
    """A saved download folder is returned by a later get_download_folder() call."""
    chosen = tmp_path / "My Downloads"
    settings.set_download_folder(chosen)
    assert settings.get_download_folder() == chosen


def test_set_and_get_lists_folder_round_trips(tmp_path):
    """A saved lists folder is returned by a later get_lists_folder() call."""
    chosen = tmp_path / "My Lists Folder"
    settings.set_lists_folder(chosen)
    assert settings.get_lists_folder() == chosen


def test_setting_one_folder_does_not_clobber_the_other(tmp_path):
    """Saving the download folder leaves a previously-saved lists folder intact, and vice versa."""
    download_path = tmp_path / "Downloads"
    lists_path = tmp_path / "Lists"
    settings.set_download_folder(download_path)
    settings.set_lists_folder(lists_path)
    assert settings.get_download_folder() == download_path
    assert settings.get_lists_folder() == lists_path


def test_corrupt_settings_file_falls_back_to_defaults(monkeypatch, tmp_path):
    """A settings.json that isn't valid JSON is treated as unset rather than raising."""
    path = tmp_path / "settings.json"
    path.write_text("not valid json{{{")
    monkeypatch.setattr(settings, "SETTINGS_PATH", path)
    assert settings.get_download_folder() == settings.default_documents_dir()


def test_set_download_folder_creates_parent_directory(monkeypatch, tmp_path):
    """Saving a setting creates the settings file's parent folder if it doesn't exist yet."""
    nested = tmp_path / "does" / "not" / "exist" / "settings.json"
    monkeypatch.setattr(settings, "SETTINGS_PATH", nested)
    settings.set_download_folder(Path("/some/folder"))
    assert nested.exists()
