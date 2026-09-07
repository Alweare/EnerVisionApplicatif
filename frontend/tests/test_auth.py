from unittest.mock import MagicMock, patch

from authentification import auth


def test_require_authentication_blocks_when_not_logged_in():
    st = MagicMock()
    st.user.is_logged_in = False
    st.button.return_value = False

    with patch.object(auth, "st", st):
        auth.require_authentication()

    st.stop.assert_called_once()
    st.login.assert_not_called()


def test_require_authentication_triggers_login_on_button_click():
    st = MagicMock()
    st.user.is_logged_in = False
    st.button.return_value = True

    with patch.object(auth, "st", st):
        auth.require_authentication()

    st.login.assert_called_once()
    st.stop.assert_called_once()


def test_require_authentication_allows_access_when_logged_in():
    st = MagicMock()
    st.user.is_logged_in = True

    with patch.object(auth, "st", st):
        auth.require_authentication()

    st.stop.assert_not_called()
    st.login.assert_not_called()


def test_render_user_menu_uses_name_when_available():
    st = MagicMock()
    st.user.name = "Jane Doe"
    st.user.preferred_username = None
    st.user.email = None
    st.button.return_value = False

    with patch.object(auth, "st", st):
        auth.render_user_menu()

    written = st.write.call_args[0][0]
    assert "Jane Doe" in written


def test_render_user_menu_falls_back_to_default_when_no_identity_claim():
    st = MagicMock()
    st.user.name = None
    st.user.preferred_username = None
    st.user.email = None
    st.button.return_value = False

    with patch.object(auth, "st", st):
        auth.render_user_menu()

    written = st.write.call_args[0][0]
    assert "Utilisateur" in written


def test_render_user_menu_logs_out_on_button_click():
    st = MagicMock()
    st.user.name = "Jane Doe"
    st.button.return_value = True

    with patch.object(auth, "st", st):
        auth.render_user_menu()

    st.logout.assert_called_once()


def test_get_access_token_returns_token_when_exposed():
    st = MagicMock()
    st.user.tokens = {"access": "secret-token-value"}

    with patch.object(auth, "st", st):
        assert auth.get_access_token() == "secret-token-value"


def test_get_access_token_returns_none_when_not_exposed():
    st = MagicMock()
    st.user.tokens = {}

    with patch.object(auth, "st", st):
        assert auth.get_access_token() is None


def test_get_access_token_returns_none_when_user_unavailable():
    st = MagicMock(spec=[])

    with patch.object(auth, "st", st):
        assert auth.get_access_token() is None
