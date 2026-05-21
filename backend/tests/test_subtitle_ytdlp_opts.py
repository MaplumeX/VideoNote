import pytest

from app.services import subtitle


def test_ydl_opts_includes_proxy_and_cookies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subtitle, "YT_DLP_PROXY", "http://127.0.0.1:7890")
    monkeypatch.setattr(subtitle, "YT_DLP_COOKIES_FROM_BROWSER", "chrome:Default")
    monkeypatch.setattr(subtitle, "YT_DLP_COOKIES_FILE", "/tmp/cookies.txt")

    opts = subtitle._ydl_opts(format="bestaudio/best")

    assert opts["proxy"] == "http://127.0.0.1:7890"
    assert opts["cookiesfrombrowser"] == ("chrome", "Default", None, None)
    assert opts["cookiefile"] == "/tmp/cookies.txt"
    assert opts["format"] == "bestaudio/best"


def test_parse_cookies_from_browser_supports_keyring_and_container() -> None:
    assert subtitle._parse_cookies_from_browser("firefox+basictext:Profile 1::none") == (
        "firefox",
        "Profile 1",
        "BASICTEXT",
        "none",
    )


def test_parse_cookies_from_browser_rejects_invalid_value() -> None:
    with pytest.raises(ValueError, match="Invalid YT_DLP_COOKIES_FROM_BROWSER"):
        subtitle._parse_cookies_from_browser("chrome+")
