from auto_prompter.store import JobStore

def test_add_and_list(tmp_path):
    store = JobStore(tmp_path / "jobs.json")
    job = store.add({"id": "a", "prompt": "hi", "enabled": True})
    assert job["id"] == "a"
    assert store.list() == [job]

def test_get(tmp_path):
    store = JobStore(tmp_path / "jobs.json")
    store.add({"id": "a", "prompt": "hi"})
    assert store.get("a")["prompt"] == "hi"
    assert store.get("missing") is None

def test_update(tmp_path):
    store = JobStore(tmp_path / "jobs.json")
    store.add({"id": "a", "prompt": "hi", "status": "pending"})
    updated = store.update("a", status="done")
    assert updated["status"] == "done"
    assert store.get("a")["status"] == "done"
    assert store.update("missing", status="x") is None

def test_delete(tmp_path):
    store = JobStore(tmp_path / "jobs.json")
    store.add({"id": "a"})
    assert store.delete("a") is True
    assert store.delete("a") is False
    assert store.list() == []

def test_persists_across_instances(tmp_path):
    path = tmp_path / "jobs.json"
    JobStore(path).add({"id": "a", "prompt": "hi"})
    assert JobStore(path).get("a")["prompt"] == "hi"
