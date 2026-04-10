import json
import pytest
from pathlib import Path

from core.project_registry import ProjectRegistry


@pytest.fixture
def registry(tmp_path):
    data_file = tmp_path / "projects.json"
    return ProjectRegistry(data_file=str(data_file))


@pytest.fixture
def fake_projects_dir(tmp_path):
    """Create a directory with some git repos and some non-git dirs."""
    for name in ["repo-a", "repo-b", "repo-c"]:
        d = tmp_path / name
        d.mkdir()
        (d / ".git").mkdir()
    # Non-git directory
    (tmp_path / "not-a-repo").mkdir()
    return tmp_path


def test_scan_finds_git_repos(registry, fake_projects_dir):
    found = registry.scan(str(fake_projects_dir))
    names = [r["name"] for r in found]
    assert sorted(names) == ["repo-a", "repo-b", "repo-c"]


def test_scan_ignores_non_git(registry, fake_projects_dir):
    found = registry.scan(str(fake_projects_dir))
    names = [r["name"] for r in found]
    assert "not-a-repo" not in names


def test_add_project(registry, fake_projects_dir):
    registry.add("repo-a", str(fake_projects_dir / "repo-a"))
    projects = registry.list()
    assert len(projects) == 1
    assert projects[0]["name"] == "repo-a"
    assert projects[0]["path"] == str(fake_projects_dir / "repo-a")
    assert "added_at" in projects[0]


def test_add_duplicate_raises(registry, fake_projects_dir):
    path = str(fake_projects_dir / "repo-a")
    registry.add("repo-a", path)
    with pytest.raises(ValueError, match="already registered"):
        registry.add("repo-a", path)


def test_remove_project(registry, fake_projects_dir):
    registry.add("repo-a", str(fake_projects_dir / "repo-a"))
    registry.remove("repo-a")
    assert registry.list() == []


def test_remove_nonexistent_raises(registry):
    with pytest.raises(ValueError, match="not found"):
        registry.remove("nope")


def test_persistence(tmp_path, fake_projects_dir):
    data_file = tmp_path / "projects.json"
    reg1 = ProjectRegistry(data_file=str(data_file))
    reg1.add("repo-a", str(fake_projects_dir / "repo-a"))

    reg2 = ProjectRegistry(data_file=str(data_file))
    assert len(reg2.list()) == 1
    assert reg2.list()[0]["name"] == "repo-a"


def test_get_project(registry, fake_projects_dir):
    registry.add("repo-a", str(fake_projects_dir / "repo-a"))
    project = registry.get("repo-a")
    assert project["name"] == "repo-a"


def test_get_nonexistent_returns_none(registry):
    assert registry.get("nope") is None
