from review_tracker.data import config_store


def test_load_config_missing_file_returns_empty_dict(tmp_path, monkeypatch):
    monkeypatch.setattr(config_store, "CONFIG_PATH", tmp_path / "does_not_exist.json")
    assert config_store.load_config() == {}


def test_save_and_load_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(config_store, "CONFIG_PATH", tmp_path / "config.json")
    config_store.save_config({"token": "abc", "project_url": "https://example.com/g/p"})

    assert config_store.load_config() == {"token": "abc", "project_url": "https://example.com/g/p"}


def test_load_config_corrupted_file_returns_empty_dict(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text("not json")
    monkeypatch.setattr(config_store, "CONFIG_PATH", path)

    assert config_store.load_config() == {}


def test_add_to_history_inserts_most_recent_first():
    history = config_store.add_to_history([], "https://gitlab.example.com/a/b")
    history = config_store.add_to_history(history, "https://gitlab.example.com/c/d")

    assert history == [
        "https://gitlab.example.com/c/d",
        "https://gitlab.example.com/a/b",
    ]


def test_add_to_history_moves_existing_value_to_front():
    history = ["a", "b", "c"]
    assert config_store.add_to_history(history, "b") == ["b", "a", "c"]


def test_add_to_history_ignores_blank_value():
    assert config_store.add_to_history(["a"], "   ") == ["a"]


def test_add_to_history_caps_at_max_size():
    history = [f"url-{i}" for i in range(config_store.MAX_PROJECT_HISTORY)]
    history = config_store.add_to_history(history, "new-url")

    assert len(history) == config_store.MAX_PROJECT_HISTORY
    assert history[0] == "new-url"
