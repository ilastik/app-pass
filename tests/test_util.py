import pathlib
from unittest.mock import Mock, PropertyMock, patch

import pytest

from app_pass._util import BinaryType, is_binary


@pytest.mark.parametrize("suffix", [".py", ".txt", ".md", ".h", ".cpp", ".hpp", ".class"])
@patch("subprocess.run")
def test_is_binary_none_text_files(subprocess_mock: Mock, suffix: str):
    with patch("pathlib.Path.suffix", new_callable=PropertyMock) as mocked_suffix:
        mocked_suffix.return_value = suffix
        path = pathlib.Path(f"/path/to/file{suffix}")
        result = is_binary(path)

        assert result == BinaryType.NONE
        mocked_suffix.assert_called()
        subprocess_mock.assert_not_called()


@pytest.mark.parametrize("suffix", [".a", ".o"])
@patch("subprocess.run")
def test_is_binary_ignore_static_archives(subprocess_mock, suffix: str):
    with patch("pathlib.Path.suffix", new_callable=PropertyMock) as mocked_suffix:
        mocked_suffix.return_value = suffix
        path = pathlib.Path(f"/path/to/file{suffix}")
        result = is_binary(path)

        assert result == BinaryType.NONE
        mocked_suffix.assert_called_once()
        subprocess_mock.assert_not_called()
