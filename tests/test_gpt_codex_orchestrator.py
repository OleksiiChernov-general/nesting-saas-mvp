from __future__ import annotations

import argparse
import json
from pathlib import Path

import certifi

from tools.gpt_codex_orchestrator.config import OrchestratorConfig, discover_bridge_chat_id, resolve_executable, resolve_state_paths
from tools.gpt_codex_orchestrator.executor import Executor
from tools.gpt_codex_orchestrator.models import ExecutionResult, PlannedTask
from tools.gpt_codex_orchestrator.network_env import sanitized_network_env, should_bypass_configured_proxy
from tools.gpt_codex_orchestrator.orchestrator import (
    TaskSourceError,
    build_queue_planning_context,
    list_queue_task_files,
    move_queue_task_file,
    pick_next_task_file,
    resolve_task_input,
    should_soft_exit_for_queue_empty,
    should_stop_queue_loop,
)
from tools.gpt_codex_orchestrator.post_run_actions import PostRunActions
from tools.gpt_codex_orchestrator.planner import Planner
from tools.gpt_codex_orchestrator.reviewer import Reviewer
from tools.gpt_codex_orchestrator.state_store import StateStore
from tools.gpt_codex_orchestrator.telegram_reporter import TelegramReporter


def _write_prompt_files(base_dir: Path) -> None:
    prompts_dir = base_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / "planner_system.txt").write_text("Return JSON only.", encoding="utf-8")
    (prompts_dir / "planner_user_template.txt").write_text(
        "Task: {high_level_task}\nContext: {planning_context}\nRepo: {repo_root}\nMax tasks: {max_tasks}",
        encoding="utf-8",
    )
    (prompts_dir / "codex_task_template.txt").write_text("{task_id} {task_title} {task_objective}", encoding="utf-8")
    (prompts_dir / "reviewer_template.txt").write_text("review", encoding="utf-8")


def test_planner_fallback_and_executor_dry_run(monkeypatch, tmp_path: Path) -> None:
    module_root = tmp_path / "tools" / "gpt_codex_orchestrator"
    module_root.mkdir(parents=True)
    _write_prompt_files(module_root)
    repo_root = module_root.parent.parent

    monkeypatch.setenv("REPO_ROOT", str(repo_root))
    monkeypatch.setenv("ORCHESTRATOR_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ORCHESTRATOR_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("CODEX_COMMAND", "codex")
    monkeypatch.setenv("DRY_RUN", "true")

    config = OrchestratorConfig.load(module_root=module_root)
    planner = Planner(config)
    plan = planner.plan("Create an orchestrator MVP")
    assert plan.tasks
    assert plan.tasks[0].id == "T1"

    store = StateStore(config.paths.runs_dir)
    run, run_dir = store.init_run(
        "run-1",
        "task-1",
        "Create an orchestrator MVP",
        repo_root,
        task_source_type="inline",
        task_source_path="",
    )
    store.save_planner_output(run_dir, run, plan)

    executor = Executor(config)
    result = executor.execute(run_dir, "Create an orchestrator MVP", plan.assumptions, plan.tasks[0])
    assert result.status == "completed"
    assert Path(result.stdout_path).exists()
    assert "Dry-run" in Path(result.artifacts[1]).read_text(encoding="utf-8")

    store.save_step_result(run_dir, run, 0, result)
    state = json.loads((run_dir / "run_state.json").read_text(encoding="utf-8"))
    assert state["steps"][0]["status"] == "completed"
    assert config.allow_git_push is False


def test_reviewer_fix_then_stop(monkeypatch, tmp_path: Path) -> None:
    module_root = tmp_path / "tools" / "gpt_codex_orchestrator"
    module_root.mkdir(parents=True)
    _write_prompt_files(module_root)
    repo_root = module_root.parent.parent

    monkeypatch.setenv("REPO_ROOT", str(repo_root))
    monkeypatch.setenv("ORCHESTRATOR_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ORCHESTRATOR_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("CODEX_COMMAND", "codex")
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("MAX_FIX_ATTEMPTS_PER_STEP", "3")

    config = OrchestratorConfig.load(module_root=module_root)
    reviewer = Reviewer(config)
    run_dir = config.paths.runs_dir / "run-review"
    (run_dir / "artifacts" / "T1").mkdir(parents=True, exist_ok=True)
    stdout_path = run_dir / "artifacts" / "T1" / "stdout.log"
    stderr_path = run_dir / "artifacts" / "T1" / "stderr.log"
    stdout_path.write_text("", encoding="utf-8")
    stderr_path.write_text("Traceback: failing test", encoding="utf-8")

    task = PlannedTask(
        id="T1",
        title="Sample task",
        objective="Fix something",
        scope=["tools/"],
        constraints=["Keep it safe."],
        verification=["Run a smoke test."],
        acceptance=["Smoke test passes."],
    )
    failed = ExecutionResult(
        task_id="T1",
        status="failed",
        return_code=1,
        summary="Step failed",
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
        artifacts=[],
        command=["codex"],
        started_at="2026-01-01T00:00:00+00:00",
        finished_at="2026-01-01T00:00:01+00:00",
        duration_sec=1.0,
        attempt=1,
        error="Traceback: failing test",
    )

    review1 = reviewer.review(run_dir, task, task, failed, attempt=1)
    assert review1.decision == "fix"
    assert "Traceback: failing test" in review1.next_task
    assert review1.review_path

    review_stop = reviewer.review(run_dir, task, task, failed, attempt=3)
    assert review_stop.decision == "stop"


def test_blocking_loopback_proxy_env_is_removed() -> None:
    env = {
        "HTTP_PROXY": "http://127.0.0.1:9",
        "HTTPS_PROXY": "http://127.0.0.1:9",
        "ALL_PROXY": "http://127.0.0.1:9",
        "NO_PROXY": "localhost,127.0.0.1,::1",
        "OPENAI_API_KEY": "test",
    }
    assert should_bypass_configured_proxy(env) is True
    cleaned = sanitized_network_env(env)
    assert "HTTP_PROXY" not in cleaned
    assert "HTTPS_PROXY" not in cleaned
    assert "ALL_PROXY" not in cleaned
    assert cleaned["OPENAI_API_KEY"] == "test"


def test_certifi_bundle_exists() -> None:
    assert Path(certifi.where()).exists()


def test_planner_caps_simple_readme_tasks(monkeypatch, tmp_path: Path) -> None:
    module_root = tmp_path / "tools" / "gpt_codex_orchestrator"
    module_root.mkdir(parents=True)
    _write_prompt_files(module_root)
    repo_root = module_root.parent.parent

    monkeypatch.setenv("REPO_ROOT", str(repo_root))
    monkeypatch.setenv("ORCHESTRATOR_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ORCHESTRATOR_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("CODEX_COMMAND", "codex")
    monkeypatch.delenv("DRY_RUN", raising=False)

    config = OrchestratorConfig.load(module_root=module_root)
    planner = Planner(config)

    assert planner._infer_task_budget("обновить README") == 1
    assert planner._infer_task_budget("refresh project documentation") == 1
    assert planner._infer_task_budget("implement worker retry queue") == config.max_tasks_per_run


def test_planner_prompt_includes_previous_queue_context(monkeypatch, tmp_path: Path) -> None:
    module_root = tmp_path / "tools" / "gpt_codex_orchestrator"
    module_root.mkdir(parents=True)
    _write_prompt_files(module_root)
    repo_root = module_root.parent.parent
    monkeypatch.setenv("REPO_ROOT", str(repo_root))
    monkeypatch.setenv("ORCHESTRATOR_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ORCHESTRATOR_LOG_DIR", str(tmp_path / "logs"))
    config = OrchestratorConfig.load(module_root=module_root)
    planner = Planner(config)
    prompt = planner.build_prompt("Implement task B", planning_context="Completed task A changed README.md")
    assert "Completed task A changed README.md" in prompt


def test_resolve_state_paths_accepts_runs_dir(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    state_dir, runs_dir = resolve_state_paths(repo_root, tmp_path / ".orchestrator-data" / "runs")
    assert state_dir == tmp_path / ".orchestrator-data"
    assert runs_dir == tmp_path / ".orchestrator-data" / "runs"


def test_discover_bridge_chat_id_from_recent_runs(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    runs_dir = repo_root / ".bridge-data" / "runs"
    runs_dir.mkdir(parents=True)
    (runs_dir / "older.json").write_text('{"chat_id": 111}', encoding="utf-8")
    latest = runs_dir / "latest.json"
    latest.write_text('{"chat_id": 468403961}', encoding="utf-8")
    assert discover_bridge_chat_id(repo_root) == 468403961


def test_resolve_executable_falls_back_to_latest_vscode_codex(monkeypatch, tmp_path: Path) -> None:
    fake_home = tmp_path / "home"
    latest_codex = (
        fake_home
        / ".vscode"
        / "extensions"
        / "openai.chatgpt-26.999.1-win32-x64"
        / "bin"
        / "windows-x86_64"
        / "codex.exe"
    )
    latest_codex.parent.mkdir(parents=True, exist_ok=True)
    latest_codex.write_text("", encoding="utf-8")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    resolved = resolve_executable(
        [str(fake_home / ".vscode" / "extensions" / "openai.chatgpt-26.1.1-win32-x64" / "bin" / "windows-x86_64" / "codex.exe")]
    )
    assert resolved[0] == str(latest_codex)


def test_resolve_task_input_from_task_file(tmp_path: Path) -> None:
    task_file = tmp_path / "next_task.txt"
    task_file.write_text("Update orchestrator README", encoding="utf-8")
    args = argparse.Namespace(task=None, task_file=str(task_file), task_queue_dir=None)
    resolved = resolve_task_input(args)
    assert resolved.source_type == "task_file"
    assert resolved.source_path == str(task_file)
    assert resolved.task_text == "Update orchestrator README"


def test_resolve_task_input_empty_task_file(tmp_path: Path) -> None:
    task_file = tmp_path / "empty.txt"
    task_file.write_text(" \n", encoding="utf-8")
    args = argparse.Namespace(task=None, task_file=str(task_file), task_queue_dir=None)
    try:
        resolve_task_input(args)
    except TaskSourceError as exc:
        assert "Task file is empty" in str(exc)
    else:
        raise AssertionError("Expected TaskSourceError for empty task file")


def test_resolve_task_input_missing_task_file(tmp_path: Path) -> None:
    args = argparse.Namespace(task=None, task_file=str(tmp_path / "missing.txt"), task_queue_dir=None)
    try:
        resolve_task_input(args)
    except TaskSourceError as exc:
        assert "Task file not found" in str(exc)
    else:
        raise AssertionError("Expected TaskSourceError for missing task file")


def test_pick_next_task_file_uses_name_order_and_supported_extensions(tmp_path: Path) -> None:
    queue_dir = tmp_path / "task_queue"
    queue_dir.mkdir()
    later = queue_dir / "010_later.txt"
    first = queue_dir / "001_first.md"
    later.write_text("later", encoding="utf-8")
    first.write_text("first", encoding="utf-8")
    first.touch()
    (queue_dir / "zzz_ignore.json").write_text("ignore", encoding="utf-8")
    selected = pick_next_task_file(queue_dir)
    assert selected.name == "010_later.txt"


def test_list_queue_task_files_sorts_by_file_placement_time(tmp_path: Path) -> None:
    queue_dir = tmp_path / "task_queue"
    queue_dir.mkdir()
    second = queue_dir / "020_second.txt"
    first = queue_dir / "003_first.txt"
    third = queue_dir / "100_third.md"
    first.write_text("first", encoding="utf-8")
    second.write_text("second", encoding="utf-8")
    third.write_text("third", encoding="utf-8")
    second.touch()
    third.touch()
    ordered = list_queue_task_files(queue_dir)
    assert [path.name for path in ordered] == ["003_first.txt", "020_second.txt", "100_third.md"]


def test_move_queue_task_file_to_completed_and_failed(tmp_path: Path) -> None:
    queue_dir = tmp_path / "task_queue"
    queue_dir.mkdir()

    completed_source = queue_dir / "001_task.txt"
    completed_source.write_text("done", encoding="utf-8")
    completed_path = move_queue_task_file(completed_source, queue_dir, "completed", "run123")
    assert completed_path.parent.name == "completed_tasks"
    assert completed_path.exists()
    assert not completed_source.exists()

    failed_source = queue_dir / "002_task.md"
    failed_source.write_text("fail", encoding="utf-8")
    failed_path = move_queue_task_file(failed_source, queue_dir, "failed", "run124")
    assert failed_path.parent.name == "failed_tasks"
    assert failed_path.exists()
    assert not failed_source.exists()


def test_resolve_task_input_from_queue_dir(tmp_path: Path) -> None:
    queue_dir = tmp_path / "task_queue"
    queue_dir.mkdir()
    first = queue_dir / "001_update_readme.txt"
    first.write_text("Update README from queue", encoding="utf-8")
    (queue_dir / "002_ignore.json").write_text("{}", encoding="utf-8")
    args = argparse.Namespace(task=None, task_file=None, task_queue_dir=str(queue_dir))
    resolved = resolve_task_input(args)
    assert resolved.source_type == "task_queue"
    assert resolved.source_path == str(first)
    assert resolved.queue_dir == queue_dir
    assert resolved.task_text == "Update README from queue"


def test_resolve_task_input_empty_queue_dir(tmp_path: Path) -> None:
    queue_dir = tmp_path / "task_queue"
    queue_dir.mkdir()
    args = argparse.Namespace(task=None, task_file=None, task_queue_dir=str(queue_dir))
    try:
        resolve_task_input(args)
    except TaskSourceError as exc:
        assert "No task files found in queue" in str(exc)
    else:
        raise AssertionError("Expected TaskSourceError for empty task queue")


def test_conflicting_task_source_arguments_raise() -> None:
    conflict_cases = [
        argparse.Namespace(task="inline", task_file="task.txt", task_queue_dir=None),
        argparse.Namespace(task="inline", task_file=None, task_queue_dir="queue"),
        argparse.Namespace(task=None, task_file="task.txt", task_queue_dir="queue"),
    ]
    for args in conflict_cases:
        try:
            resolve_task_input(args)
        except TaskSourceError as exc:
            assert "Conflicting task source arguments" in str(exc)
        else:
            raise AssertionError("Expected TaskSourceError for conflicting task source args")


def test_soft_exit_if_queue_empty_flag_matches_only_empty_queue_case() -> None:
    args = argparse.Namespace(
        task=None,
        task_file=None,
        task_queue_dir="queue",
        soft_exit_if_queue_empty=True,
    )
    empty_queue_exc = TaskSourceError(
        "No task files found in queue: queue. Supported extensions: .txt, .md",
        source_type="task_queue",
        source_path="queue",
    )
    assert should_soft_exit_for_queue_empty(args, empty_queue_exc) is True

    other_exc = TaskSourceError("Task queue directory not found: queue", source_type="task_queue", source_path="queue")
    assert should_soft_exit_for_queue_empty(args, other_exc) is False


def test_loop_flag_requires_queue_dir() -> None:
    args = argparse.Namespace(
        task="inline",
        task_file=None,
        task_queue_dir=None,
        soft_exit_if_queue_empty=False,
        loop=True,
    )
    assert args.loop is True


def test_should_stop_queue_loop_triggers_only_for_failed_or_cancelled_runs() -> None:
    args = argparse.Namespace(
        task=None,
        task_file=None,
        task_queue_dir="queue",
        soft_exit_if_queue_empty=False,
        loop=True,
        stop_on_failure=True,
    )
    assert should_stop_queue_loop(args, {"status": "failed"}) is True
    assert should_stop_queue_loop(args, {"status": "cancelled"}) is True
    assert should_stop_queue_loop(args, {"status": "completed"}) is False

    args.stop_on_failure = False
    assert should_stop_queue_loop(args, {"status": "failed"}) is False


def test_build_queue_planning_context_uses_previous_completed_reports() -> None:
    context = build_queue_planning_context(
        [
            {
                "task_source_path": "task_queue/001_first.txt",
                "status": "completed",
                "planner_goal": "Implement first task",
                "steps": [{"task": {"id": "T1"}, "summary": "Updated README and tests"}],
                "post_run_actions": {"git_push": {"status": "skipped", "reason": "ALLOW_GIT_PUSH=false"}},
            }
        ]
    )
    assert "task_queue/001_first.txt" in context
    assert "Updated README and tests" in context
    assert "Git push status" in context


def test_post_run_actions_skip_when_git_push_disabled(monkeypatch, tmp_path: Path) -> None:
    module_root = tmp_path / "tools" / "gpt_codex_orchestrator"
    module_root.mkdir(parents=True)
    _write_prompt_files(module_root)
    repo_root = module_root.parent.parent
    monkeypatch.setenv("REPO_ROOT", str(repo_root))
    monkeypatch.setenv("ORCHESTRATOR_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ORCHESTRATOR_LOG_DIR", str(tmp_path / "logs"))
    config = OrchestratorConfig.load(module_root=module_root)
    reporter = TelegramReporter("", None)
    actions = PostRunActions(config, reporter).run("Update docs", baseline_status={})
    assert actions["git_push"]["status"] == "skipped"
    assert actions["deploy_verification"]["status"] == "skipped"


def test_post_run_actions_skip_when_repo_dirty_before_run(monkeypatch, tmp_path: Path) -> None:
    module_root = tmp_path / "tools" / "gpt_codex_orchestrator"
    module_root.mkdir(parents=True)
    _write_prompt_files(module_root)
    repo_root = module_root.parent.parent
    monkeypatch.setenv("REPO_ROOT", str(repo_root))
    monkeypatch.setenv("ORCHESTRATOR_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ORCHESTRATOR_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ALLOW_GIT_PUSH", "true")
    config = OrchestratorConfig.load(module_root=module_root)
    reporter = TelegramReporter("", None)
    actions = PostRunActions(config, reporter).run("Update docs", baseline_status={"README.md": " M"})
    assert actions["git_push"]["status"] == "skipped"
    assert "dirty before the run" in actions["git_push"]["reason"]


def test_post_run_actions_skip_when_no_changes(monkeypatch, tmp_path: Path) -> None:
    module_root = tmp_path / "tools" / "gpt_codex_orchestrator"
    module_root.mkdir(parents=True)
    _write_prompt_files(module_root)
    repo_root = module_root.parent.parent
    monkeypatch.setenv("REPO_ROOT", str(repo_root))
    monkeypatch.setenv("ORCHESTRATOR_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ORCHESTRATOR_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ALLOW_GIT_PUSH", "true")
    config = OrchestratorConfig.load(module_root=module_root)
    reporter = TelegramReporter("", None)
    manager = PostRunActions(config, reporter)
    manager.snapshot_git_status = lambda: {}  # type: ignore[method-assign]
    actions = manager.run("Update docs", baseline_status={})
    assert actions["git_push"]["status"] == "skipped"
    assert "No git changes detected" in actions["git_push"]["reason"]


def test_post_run_actions_push_and_healthcheck_success(monkeypatch, tmp_path: Path) -> None:
    module_root = tmp_path / "tools" / "gpt_codex_orchestrator"
    module_root.mkdir(parents=True)
    _write_prompt_files(module_root)
    repo_root = module_root.parent.parent
    monkeypatch.setenv("REPO_ROOT", str(repo_root))
    monkeypatch.setenv("ORCHESTRATOR_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("ORCHESTRATOR_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("ALLOW_GIT_PUSH", "true")
    monkeypatch.setenv("RAILWAY_HEALTHCHECK_URL", "https://example.test/health")
    config = OrchestratorConfig.load(module_root=module_root)
    reporter = TelegramReporter("", None)
    manager = PostRunActions(config, reporter)
    manager.snapshot_git_status = lambda: {"README.md": " M"}  # type: ignore[method-assign]
    commands: list[list[str]] = []

    def fake_run_process(command: list[str], timeout_sec: int) -> dict[str, object]:
        commands.append(command)
        return {"command": command, "return_code": 0, "stdout": "ok", "stderr": "", "duration_sec": 0.1}

    manager._run_process = fake_run_process  # type: ignore[method-assign]
    manager._verify_deploy = lambda: {  # type: ignore[method-assign]
        "status": "completed",
        "reason": "Healthcheck succeeded.",
        "url": "https://example.test/health",
        "http_status": 200,
    }
    actions = manager.run("Update docs", baseline_status={})
    assert actions["git_push"]["status"] == "completed"
    assert actions["deploy_verification"]["status"] == "completed"
    assert commands[0][:3] == ["git", "add", "--all"]
    assert commands[1][:3] == ["git", "commit", "-m"]
    assert commands[2] == ["git", "push", "origin", "main"]
