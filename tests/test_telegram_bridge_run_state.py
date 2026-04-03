from __future__ import annotations

import json

from tools.telegram_codex_bridge.run_state import CodexEventNormalizer, RunStore


def test_run_store_persists_runs_and_events(tmp_path):
    store = RunStore(tmp_path, max_runs=10, event_buffer_size=5)
    run = store.create_run(chat_id=1, user_id=2, username="tester", prompt="ship it", workdir=tmp_path)
    run = store.update_run(run.run_id, status="waiting_approval")

    normalizer = CodexEventNormalizer()
    event, _, final_text = normalizer.normalize_stdout(
        run,
        json.dumps({"type": "run.completed", "final_text": "done", "timestamp": "2026-03-30T10:00:00+00:00"}),
        sequence=1,
    )
    assert final_text == "done"

    store.append_event(run.run_id, event)
    store.mark_finished(run.run_id, status="completed", status_reason="completed", exit_code=0, final_text="done")

    reloaded = RunStore(tmp_path, max_runs=10, event_buffer_size=5)
    persisted = reloaded.get_run(run.run_id)
    assert persisted is not None
    assert persisted.status == "completed"
    assert persisted.status_reason == "completed"
    assert persisted.final_text == "done"
    assert persisted.events[-1]["name"] == "run.completed"
    assert (tmp_path / "latest-runs.json").exists()
    assert (tmp_path / "runs" / f"{run.run_id}.json").exists()
    assert (tmp_path / "runs" / f"{run.run_id}.jsonl").exists()


def test_normalizer_maps_stdout_stderr_and_invalid_json(tmp_path):
    store = RunStore(tmp_path, max_runs=1, event_buffer_size=5)
    run = store.create_run(chat_id=1, user_id=2, username="tester", prompt="prompt", workdir=tmp_path)
    normalizer = CodexEventNormalizer()

    event, payload, final_text = normalizer.normalize_stdout(run, json.dumps({"type": "response.output_text.delta", "delta": "partial"}), sequence=1)
    bad_event, bad_payload, bad_final = normalizer.normalize_stdout(run, "{not-json", sequence=2)
    stderr_event = normalizer.normalize_stderr(run, "boom", sequence=3)

    assert payload["type"] == "response.output_text.delta"
    assert event.name == "item.updated"
    assert event.body == "partial"
    assert final_text is None
    assert bad_payload["parse_error"]
    assert bad_event.name == "log.stdout.unparsed"
    assert bad_final is None
    assert stderr_event.name == "log.stderr"
    assert stderr_event.severity == "error"


def test_run_store_recovers_incomplete_runs(tmp_path):
    store = RunStore(tmp_path, max_runs=10, event_buffer_size=5)
    run = store.create_run(chat_id=1, user_id=2, username="tester", prompt="resume me", workdir=tmp_path)
    store.update_run(run.run_id, status="running", pid=999)

    reloaded = RunStore(tmp_path, max_runs=10, event_buffer_size=5)
    recovered = reloaded.recover_incomplete_runs()

    assert len(recovered) == 1
    interrupted = reloaded.get_run(run.run_id)
    assert interrupted is not None
    assert interrupted.status == "interrupted"
    assert interrupted.status_reason == "bridge_restarted"
    assert interrupted.pid is None
    assert interrupted.events[-1]["name"] == "run.interrupted"
