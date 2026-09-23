"""UI 文言の言語切り替え（改修計画 5-4 節 U4）。

``texts`` はモジュール属性を直接差し替える方式なので、他のテストに影響しないよう
必ず日本語に戻してから終える（autouse フィクスチャ）。
"""

from __future__ import annotations

import pytest

from yaqpy.gui import texts

# {キー: そのテンプレートが受け取る差し込み値}。両方の言語で同じキーで通ることを確かめる。
_TEMPLATES = {
    "MSG_TRUNCATED": {"n": "10"},
    "MSG_SAVED": {"path": "a.yaml"},
    "MSG_SAVED_WITH_BACKUP": {"path": "a.yaml", "backup": "a.yaml.bak"},
    "DLG_OVERWRITE_BODY": {"path": "a.yaml"},
    "ERR_TOO_LARGE": {"size": "1 MiB", "limit": "50 MiB"},
    "HINT_SECURITY": {"capability": "env"},
}


@pytest.fixture(autouse=True)
def _restore_default_language():
    yield
    texts.select_language(texts.DEFAULT_LANGUAGE)


class LanguageTests:
    def test_default_is_japanese(self) -> None:
        assert texts.BTN_ADD_FILE == "＋ファイルを追加"
        assert texts.DEFAULT_LANGUAGE == "ja"

    def test_switching_to_english_changes_the_module_attributes(self) -> None:
        texts.select_language("en")
        assert texts.BTN_ADD_FILE == "+ Add File"
        assert texts.SET_TITLE == "Settings"

    def test_app_title_is_the_same_in_both_languages(self) -> None:
        texts.select_language("en")
        assert texts.APP_TITLE == "yaqpy"

    def test_switching_back_to_japanese_restores_the_original(self) -> None:
        texts.select_language("en")
        texts.select_language("ja")
        assert texts.BTN_ADD_FILE == "＋ファイルを追加"

    def test_an_unrecognised_language_falls_back_to_japanese(self) -> None:
        texts.select_language("fr")
        assert texts.BTN_ADD_FILE == "＋ファイルを追加"

    def test_every_japanese_key_has_an_english_counterpart(self) -> None:
        # texts.py 自身も import 時に同じ検査を assert している。ここでは回帰検知として残す。
        assert texts._EN.keys() == texts._JA.keys()

    @pytest.mark.parametrize("key,kwargs", list(_TEMPLATES.items()))
    def test_templates_accept_the_same_placeholders_in_both_languages(
        self, key: str, kwargs: dict[str, str]) -> None:
        texts.select_language("ja")
        getattr(texts, key).format(**kwargs)
        texts.select_language("en")
        getattr(texts, key).format(**kwargs)

    def test_capability_labels_exist_in_both_languages(self) -> None:
        texts.select_language("ja")
        assert texts.CAP_ENV and texts.CAP_FILE
        texts.select_language("en")
        assert texts.CAP_ENV and texts.CAP_FILE


class SecurityExplanationTests:
    """v0.7.0：env と load を別々に許可する理由と、load が未実装であることを設定画面で伝える。"""

    @pytest.mark.parametrize("language", ["ja", "en"])
    def test_the_file_switch_says_the_operator_is_not_implemented(self, language: str) -> None:
        texts.select_language(language)
        assert ("未実装" if language == "ja" else "not implemented") in texts.SET_ALLOW_FILE

    @pytest.mark.parametrize("language", ["ja", "en"])
    def test_the_reason_for_two_switches_is_shown(self, language: str) -> None:
        texts.select_language(language)
        assert texts.SET_SECURITY_WHY
        assert texts._EN["SET_SECURITY_WHY"] != texts._JA["SET_SECURITY_WHY"]

    def test_the_claim_matches_reality_load_is_not_implemented(self) -> None:
        """設定画面の注記が事実であること（load を実装したら、この注記と検査を見直す）。"""
        from yaqpy.app.selfdoc import operator_table

        info = {i.name: i.implemented for i in operator_table()}
        assert info["load"] is False and info["load_str"] is False
