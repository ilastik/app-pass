import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import app_pass._notarize
import pytest


@patch.object(subprocess, "check_call")
def test_compress(check_call_patch: MagicMock):
    app_path = Path("Path_to_my_app.app")
    to_sign_path = app_path.name.replace(".app", "-tosign.zip")
    app_pass._notarize.compress(app_path)

    check_call_patch.assert_called_once()
    args = check_call_patch.call_args.args[0]
    assert args == ["/usr/bin/ditto", "-v", "-c", "-k", "--keepParent", str(app_path), str(to_sign_path)]


@patch.object(subprocess, "check_call")
def test_remove_apple_double(check_call_patch: MagicMock):
    app_path = Path("Path_to_my_app")
    app_pass._notarize.remove_apple_double(app_path)

    check_call_patch.assert_called_once()
    args = check_call_patch.call_args.args[0]
    assert args == ["find", str(app_path), "-type", "f", "-name", "._*", "-delete"]


@patch.object(subprocess, "check_output")
def test_submit(check_output_patch: MagicMock):
    check_output_patch.return_value = '{"id": "some_id"}'
    app_path_to_sign = Path("Path_to_my_app_to_sign")
    keychain_profile = "keychain_profile"
    keychain = Path("Path_to_my_keychain")
    apple_id_email = "hello@ilastik.org"
    team_id = "ilastik team"
    app_pass._notarize.submit(app_path_to_sign, keychain_profile, keychain, apple_id_email, team_id)

    check_output_patch.assert_called_once()
    args = check_output_patch.call_args.args[0]
    assert args == [
        "xcrun",
        "notarytool",
        "submit",
        "--output-format",
        "json",
        "--keychain-profile",
        keychain_profile,
        "--keychain",
        str(keychain),
        "--apple-id",
        apple_id_email,
        "--team-id",
        team_id,
        str(app_path_to_sign),
    ]


@patch.object(subprocess, "check_output")
def test_staple(check_output_patch: MagicMock):
    app_path = Path("Path_to_my_app.app")

    app_pass._notarize.staple(app_path)
    check_output_patch.assert_called_once()
    args = check_output_patch.call_args.args[0]
    assert args == ["xcrun", "stapler", "staple", str(app_path)]


@patch.object(subprocess, "check_output")
def test_check(check_output_patch: MagicMock):
    keychain_profile = "keychain_profile"
    keychain = Path("Path_to_my_keychain")
    apple_id_email = "hello@ilastik.org"
    team_id = "ilastik team"
    submission_id = "123"

    check_output_patch.return_value = f'{{"id": {submission_id}, "status": "blah", "name": "somename"}}'

    app_pass._notarize.check(submission_id, keychain_profile, keychain, apple_id_email, team_id)
    check_output_patch.assert_called_once()
    args = check_output_patch.call_args.args[0]
    assert args == [
        "xcrun",
        "notarytool",
        "info",
        "--output-format",
        "json",
        "--keychain-profile",
        keychain_profile,
        "--keychain",
        str(keychain),
        "--apple-id",
        apple_id_email,
        "--team-id",
        team_id,
        submission_id,
    ]


def mocked_perf_counter():
    value = -1

    def func():
        nonlocal value
        value += 60
        return value

    return func


@patch.object(time, "sleep")
@patch.object(time, "perf_counter", new_callable=mocked_perf_counter)
@patch.object(app_pass._notarize, "staple")
@patch.object(app_pass._notarize, "check")
@patch.object(app_pass._notarize, "submit")
@patch.object(app_pass._notarize, "compress")
@patch.object(app_pass._notarize, "remove_apple_double")
def test_notarize_timeout(
    apple_double_mock: MagicMock,
    compress_mock: MagicMock,
    submit_mock: MagicMock,
    check_mock: MagicMock,
    staple_mock: MagicMock,
    perf_counter_mock: MagicMock,
    sleep_mock: MagicMock,
):
    app_path = Path("Path_to_my_app")
    keychain_profile = "keychain_profile"
    keychain = Path("Path_to_my_keychain")
    apple_id_email = "hello@ilastik.org"
    team_id = "ilastik team"

    check_mock.return_value = "in progress"
    ret_val = app_pass._notarize.notarize_impl(
        app_path, keychain_profile, keychain, apple_id_email, team_id, timeout_minutes=142
    )

    apple_double_mock.assert_called_once()
    compress_mock.assert_called_once()
    submit_mock.assert_called_once()
    assert ret_val == -1
    assert sleep_mock.call_count == 142
    assert check_mock.call_count == 142

    staple_mock.assert_not_called()


@patch.object(time, "sleep")
@patch.object(time, "perf_counter", new_callable=mocked_perf_counter)
@patch.object(app_pass._notarize, "staple")
@patch.object(app_pass._notarize, "check")
@patch.object(app_pass._notarize, "submit")
@patch.object(app_pass._notarize, "compress")
@patch.object(app_pass._notarize, "remove_apple_double")
def test_notarize_success(
    apple_double_mock: MagicMock,
    compress_mock: MagicMock,
    submit_mock: MagicMock,
    check_mock: MagicMock,
    staple_mock: MagicMock,
    perf_counter_mock: MagicMock,
    sleep_mock: MagicMock,
):
    app_path = Path("Path_to_my_app")
    keychain_profile = "keychain_profile"
    keychain = Path("Path_to_my_keychain")
    apple_id_email = "hello@ilastik.org"
    team_id = "ilastik team"

    check_mock.return_value = "accepted"
    ret_val = app_pass._notarize.notarize_impl(
        app_path, keychain_profile, keychain, apple_id_email, team_id, timeout_minutes=42
    )

    apple_double_mock.assert_called_once()
    compress_mock.assert_called_once()
    submit_mock.assert_called_once()
    assert sleep_mock.call_count == 0
    assert check_mock.call_count == 1

    assert ret_val == 0
    staple_mock.assert_called_once()
