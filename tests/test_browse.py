from pathlib import Path

from auto_prompter.browse import list_dir


def test_lists_subdirectories_only_sorted_no_hidden(tmp_path):
    (tmp_path / "beta").mkdir()
    (tmp_path / "alpha").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "file.txt").write_text("x")
    result = list_dir(tmp_path)
    assert result["path"] == str(tmp_path.resolve())
    assert [d["name"] for d in result["dirs"]] == ["alpha", "beta"]


def test_child_paths_are_absolute(tmp_path):
    (tmp_path / "proj").mkdir()
    result = list_dir(tmp_path)
    assert result["dirs"][0]["path"] == str((tmp_path / "proj").resolve())


def test_parent_present_for_subdir(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    assert list_dir(sub)["parent"] == str(tmp_path.resolve())


def test_root_parent_is_none():
    assert list_dir("/")["parent"] is None


def test_nonexistent_falls_back_to_home(tmp_path):
    result = list_dir(tmp_path / "does-not-exist")
    assert result["path"] == str(Path.home().resolve())


def test_none_defaults_to_home():
    assert list_dir()["path"] == str(Path.home().resolve())
