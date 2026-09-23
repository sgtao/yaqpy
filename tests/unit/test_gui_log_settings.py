"""実行ログの設定（v0.7.0）：既定値と永続化。"""

from __future__ import annotations

import pytest

from yaqpy.gui.state import SettingsState, settings_from_dict, settings_to_dict


class DefaultsTests:
    def test_defaults_match_the_plan(self) -> None:
        s = SettingsState()
        assert (s.log_enabled, s.log_dir, s.log_max_files, s.log_max_entry_mib) == (
            True, "", 500, 1)


class PersistenceTests:
    def test_the_log_settings_are_saved_and_restored(self) -> None:
        s = SettingsState(log_enabled=False, log_dir="D:\\my logs", log_max_files=20,
                          log_max_entry_mib=3)
        data = settings_to_dict(s)
        assert data["log_enabled"] is False and data["log_dir"] == "D:\\my logs"
        restored = settings_from_dict(data)
        assert (restored.log_enabled, restored.log_dir, restored.log_max_files,
                restored.log_max_entry_mib) == (False, "D:\\my logs", 20, 3)

    def test_dangerous_permissions_are_still_never_saved(self) -> None:
        data = settings_to_dict(SettingsState(allow_env=True, allow_file=True))
        assert "allow_env" not in data and "allow_file" not in data

    def test_old_saved_settings_without_log_fields_get_the_defaults(self) -> None:
        restored = settings_from_dict({"timeout_seconds": 5, "language": "en"})
        assert restored.log_enabled is True and restored.log_max_files == 500

    @pytest.mark.parametrize("bad", [None, "many", 0, -3, [], {}])
    def test_broken_numbers_fall_back_to_the_defaults(self, bad: object) -> None:
        restored = settings_from_dict({"log_max_files": bad, "log_max_entry_mib": bad})
        assert restored.log_max_files == 500 and restored.log_max_entry_mib == 1

    @pytest.mark.parametrize("bad", [None, 5, ["x"], {"a": 1}])
    def test_a_broken_folder_falls_back_to_the_default_folder(self, bad: object) -> None:
        assert settings_from_dict({"log_dir": bad}).log_dir == ""
