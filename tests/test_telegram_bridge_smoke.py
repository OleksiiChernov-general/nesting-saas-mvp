from __future__ import annotations

import json
import subprocess
import time

from tools.telegram_codex_bridge.bot import TaskManager
from tools.telegram_codex_bridge.codex_runner import CodexRunResult, CodexRunner
from tools.telegram_codex_bridge.config import BridgeConfig
from tools.telegram_codex_bridge.run_state import CodexEventNormalizer, RunStore


def test_fake_event_stream_smoke(tmp_path):
    store = RunStore(tmp_path, max_runs=10, event_buffer_size=10)
    normalizer = CodexEventNormalizer()
    run = store.create_run(chat_id=1, user_id=2, username="tester", prompt="smoke", workdir=tmp_path)
    run = store.mark_started(run.run_id, pid=1234)

    stream = [
        json.dumps({"type": "turn.started", "title": "Analyzing"}),
        json.dumps({"type": "response.output_text.delta", "delta": "partial output"}),
        json.dumps({"type": "run.completed", "final_text": "all done"}),
    ]

    final_text = ""
    for idx, line in enumerate(stream, start=1):
        current = store.get_run(run.run_id)
        assert current is not None
        event, _, maybe_final = normalizer.normalize_stdout(current, line, sequence=idx)
        store.append_event(run.run_id, event)
        if maybe_final:
            final_text = maybe_final
            store.update_run(run.run_id, final_text=maybe_final)

    store.mark_finished(run.run_id, status="completed", status_reason="completed", exit_code=0, final_text=final_text)
    persisted = RunStore(tmp_path, max_runs=10, event_buffer_size=10).get_run(run.run_id)

    assert persisted is not None
    assert persisted.status == "completed"
    assert persisted.status_reason == "completed"
    assert persisted.final_text == "all done"
    assert [event["name"] for event in persisted.events][-3:] == ["turn.started", "item.updated", "run.completed"]


class FakeTelegram:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []

    def send_message(self, chat_id: int, text: str, reply_markup=None):  # noqa: ANN001
        self.messages.append((chat_id, text))
        return {"result": {"message_id": len(self.messages)}}

    def edit_message_reply_markup(self, chat_id: int, message_id: int) -> None:  # noqa: ARG002
        return None


class FakeRunner:
    def __init__(
        self,
        stdout_lines: list[str],
        stderr_lines: list[str] | None = None,
        exit_code: int = 0,
        execute_hook=None,
    ) -> None:
        self.stdout_lines = stdout_lines
        self.stderr_lines = stderr_lines or []
        self.exit_code = exit_code
        self.execute_hook = execute_hook

    def build_effective_prompt(self, prompt: str) -> str:
        return prompt

    def build_command(self, prompt: str) -> list[str]:
        return ["fake-codex", prompt]

    def execute(self, prompt: str, on_started, on_stdout, on_stderr, on_timeout):  # noqa: ANN001
        on_started(4321)
        if self.execute_hook is not None:
            self.execute_hook()
        for line in self.stdout_lines:
            on_stdout(line)
        for line in self.stderr_lines:
            on_stderr(line)
        return CodexRunResult(exit_code=self.exit_code, timed_out=False, stdout_lines=self.stdout_lines, stderr_lines=self.stderr_lines)

    @staticmethod
    def terminate_pid(pid: int, graceful: bool) -> None:  # noqa: ARG004
        return None


def _build_config(tmp_path) -> BridgeConfig:  # noqa: ANN001
    return BridgeConfig(
        telegram_bot_token="token",
        telegram_chat_id=None,
        allowed_user_ids={1},
        allowed_usernames=set(),
        codex_command=["codex"],
        codex_args_default=[],
        project_dir=tmp_path,
        run_logs_dir=tmp_path / ".bridge-data",
        websocket_enabled=False,
        websocket_host="127.0.0.1",
        websocket_port=8765,
        websocket_token="token",
        run_timeout_sec=30,
        run_idle_timeout_sec=5,
        emit_telegram_progress_updates=False,
        event_buffer_size=50,
        poll_timeout_sec=1,
        max_recent_runs=10,
    )


def _init_git_repo(tmp_path) -> None:  # noqa: ANN001
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    (tmp_path / "tracked.txt").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )


def test_approved_task_runs_via_runner_and_persists_history(tmp_path):
    telegram = FakeTelegram()
    _init_git_repo(tmp_path)
    runner = FakeRunner(
        stdout_lines=[
            json.dumps({"type": "turn.started", "title": "Analyzing"}),
            json.dumps({"type": "run.completed", "final_text": "ready"}),
        ],
        execute_hook=lambda: (tmp_path / "generated.txt").write_text("done\n", encoding="utf-8"),
    )
    manager = TaskManager(_build_config(tmp_path), telegram, runner=runner)
    manager.start()
    try:
        run = manager.create_task(chat_id=1, user_id=1, username="tester", prompt="ship it")
        manager.request_approval(run)
        manager.approve_task(run.task_id)
        final_run = manager.get_task(run.task_id)
        assert final_run is not None
        for _ in range(40):
            final_run = manager.get_task(run.task_id)
            if final_run and final_run.status == "completed" and final_run.final_report_sent:
                break
            time.sleep(0.05)
        assert final_run is not None
        assert final_run.status == "completed"
        assert final_run.status_reason == "completed"
        assert final_run.final_text == "ready"
        assert final_run.final_report_sent is True
        assert "ready" in final_run.result_summary
        assert "?? generated.txt" in final_run.changed_files
        final_reports = [text for _, text in telegram.messages if "Измененные файлы:" in text]
        assert final_reports
        assert "Кратко:" in final_reports[-1]
        assert "Измененные файлы:" in final_reports[-1]
        assert "generated.txt" in final_reports[-1]
        assert "Prompt:" not in final_reports[-1]
        reloaded = RunStore(tmp_path / ".bridge-data", max_runs=10, event_buffer_size=50).get_run(final_run.run_id)
        assert reloaded is not None
        assert reloaded.status == "completed"
        assert reloaded.final_text == "ready"
        assert reloaded.changed_files == ["?? generated.txt"]
    finally:
        manager.stop()


def test_build_effective_prompt_warns_against_broad_recursive_windows_scans():
    prompt = CodexRunner.build_effective_prompt("inspect the project")

    assert "Do NOT call rg" in prompt
    assert "Avoid broad recursive scans from the repository root" in prompt
    assert "switch to a narrower command" in prompt
