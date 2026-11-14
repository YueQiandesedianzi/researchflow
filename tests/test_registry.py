"""Registry SQLite 读写与只增语义。"""

from researchflow.registry.store import Store


def test_store_roundtrip(tmp_path):
    store = Store.open(tmp_path / ".researchflow")
    run_id = store.create_run("node-a", "io.load_csv", "0.1.0", cache_key="k1")
    assert run_id == "RUN-000001"
    f = tmp_path / "x.csv"
    f.write_text("a,b\n1,2\n", encoding="utf-8")
    from researchflow.registry.artifacts import register_artifact
    register_artifact(store, run_id, "table", f, "table", tmp_path)
    store.add_metrics(run_id, {"rmse": 0.5, "note": "非数值被忽略"})
    store.add_validation(run_id, "file_exists", True, "")
    store.finish_run(run_id, "validated", {"run_id": run_id, "status": "validated"})

    run = store.latest_run("node-a")
    assert run["run_id"] == run_id and run["status"] == "validated"
    assert store.metrics_of(run_id) == {"rmse": 0.5}
    assert len(store.artifacts_of(run_id)) == 1
    assert store.find_cache("k1")["run_id"] == run_id

    store.add_decision("gate-1", "auto", "candidate.rmse < 1", True, True, actor="auto")
    dec = store.latest_decision("gate-1")
    assert dec["final_result"] == 1 and dec["auto_result"] == 1

    # 中断恢复：running → interrupted
    store.create_run("node-b", "io.load_csv", "0.1.0")
    assert store.mark_interrupted() == 1
    assert store.latest_any("node-b")["status"] == "interrupted"
    store.close()


def test_run_id_sequence(tmp_path):
    store = Store.open(tmp_path / ".researchflow")
    ids = [store.create_run("n", "b", "0.1.0") for _ in range(3)]
    assert ids == ["RUN-000001", "RUN-000002", "RUN-000003"]
    store.close()
