"""Tests for runner.py. Uses fake CLI processes; never calls a model or spends quota.

Run from this directory:  python -m unittest test_runner -v
"""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import runner

FAKE_KIMI = r'''
import json, os, sys
from pathlib import Path

args = sys.argv[1:]
if "--version" in args:
    print("0.34.0-fake")
    sys.exit(0)

mode = os.environ.get("FAKE_KIMI_MODE", "ok_review")
out = os.environ.get("FAKE_ARGV_OUT")
if out:
    Path(out).write_text(json.dumps(args), encoding="utf-8")

run_dir = Path(args[args.index("--add-dir") + 1])
prompt_path = run_dir / "prompt.txt"
prompt = prompt_path.read_text(encoding="utf-8")
agent = (run_dir / "agent.md").read_text(encoding="utf-8")
assert "tools: Read, Grep, Glob" in agent or "tools: Read, Write, Edit, Grep, Glob, Bash" in agent

# In split mode prompt.txt is an index of "- <absolute path>" lines, read in order.
indexed = [line[2:].strip() for line in prompt.splitlines() if line.startswith("- ")]
content = "".join(Path(p).read_text(encoding="utf-8") for p in indexed) if indexed else prompt
assert "PLAN SHA256" in content, "reviewer did not receive the runner prompt"

REVIEW = json.dumps({"verdict": "APPROVED", "summary": "ok", "findings": [],
                     "coverage": ["PLAN.md"], "limitations": []})

def emit(*events):
    for event in events:
        print(json.dumps(event))

def call(name, cid="c1", arguments="{}"):
    return {"role": "assistant", "content": None,
            "tool_calls": [{"type": "function", "id": cid,
                            "function": {"name": name, "arguments": arguments}}]}

def read_of(path, cid):
    return call("Read", cid, json.dumps({"path": str(path)}))

def text(body):
    return {"role": "assistant", "content": body}

if mode == "fail":
    print("boom", file=sys.stderr)
    sys.exit(1)

# Every required part is read first, like a careful reviewer would. "split_missing_part" skips the last one,
# and "approved_no_read" reads nothing at all.
required = [prompt_path] + [Path(p) for p in indexed]
if mode == "split_missing_part":
    required = required[:-1]
if mode != "approved_no_read":
    for number, path in enumerate(required):
        emit(read_of(path, f"r{number}"))

# Extra read chosen by the test, for example a path outside the repo.
extra = os.environ.get("FAKE_EXTRA_READ")
if extra:
    emit(read_of(extra, "extra"))

if mode in ("ok_review", "ok_review_split", "split_missing_part"):
    emit(text(REVIEW))
elif mode == "ok_review_fenced":
    emit(text("```json\n" + REVIEW + "\n```"))
elif mode == "ok_review_prose":
    emit(text("I inspected all files. Compiling the review.\n\n```json\n" + REVIEW + "\n```\n\nDone."))
elif mode == "two_blocks":
    emit(text("```json\n" + REVIEW + "\n```\n\n```json\n" + REVIEW + "\n```"))
elif mode == "approved_no_read":
    emit(text(REVIEW))
elif mode == "no_text":
    pass
elif mode == "malformed_json":
    emit(text("this is not json"))
elif mode == "bad_line":
    print("not a json event")
elif mode == "bad_tool":
    emit(call("Bash"), text(REVIEW))
elif mode == "ok_build":
    emit(call("Write"), text("Report: wrote the file. Proof not run by builder."))
else:
    raise SystemExit("unknown fake mode " + mode)

if mode != "fail":
    # Mirrors the real CLI, which prints a resume hint at the end of the stream.
    print(json.dumps({"role": "meta", "type": "session.resume_hint", "session_id": "session_test"}))
'''

PLAN = "# Plan\n\nGoal: say hello.\n"

FAKE_DSH = r'''
import json, os, sys
from pathlib import Path

args = sys.argv[1:]
if "--version" in args:
    print(os.environ.get("FAKE_DSH_VERSION", "0.1.6-alpha.1-fake"))
    sys.exit(0)

out = os.environ.get("FAKE_DSH_ARGV_OUT")
if out:
    Path(out).write_text(json.dumps(args), encoding="utf-8")
envout = os.environ.get("FAKE_DSH_ENV_OUT")
if envout:
    Path(envout).write_text(json.dumps({"DSH_PERMISSION_MODE": os.environ.get("DSH_PERMISSION_MODE")}),
                           encoding="utf-8")

mode = os.environ.get("FAKE_DSH_MODE", "ok_review")
if mode == "fail":
    print("boom", file=sys.stderr)
    sys.exit(1)

prompt = sys.stdin.read()
assert "PLAN SHA256" in prompt, "reviewer did not receive the runner prompt"

REVIEW = json.dumps({"verdict": "APPROVED", "summary": "ok", "findings": [],
                     "coverage": ["PLAN.md"], "limitations": []})

if mode == "ok_review":
    final = REVIEW
elif mode == "ok_review_fenced":
    final = "```json\n" + REVIEW + "\n```"
elif mode == "ok_build":
    final = "Report: wrote the file. Proof not run by builder."
elif mode == "incomplete":
    print(json.dumps({"sessionId": "session-ds", "finalResponse": "partial", "finishReason": "max-tokens"}))
    sys.exit(0)
elif mode == "no_session":
    print(json.dumps({"finalResponse": REVIEW, "finishReason": "completed"}))
    sys.exit(0)
elif mode == "not_json":
    print("this is not json")
    sys.exit(0)
else:
    raise SystemExit("unknown fake mode " + mode)

session = args[args.index("--session-id") + 1] if "--session-id" in args else "session-ds-new"
print(json.dumps({"sessionId": session, "finalResponse": final, "finishReason": "completed"}))
'''

FAKE_QWEN = r'''
import json, os, sys
from pathlib import Path

args = sys.argv[1:]
if "--version" in args:
    print("0.50.0-fake")
    sys.exit(0)

out = os.environ.get("FAKE_QWEN_ARGV_OUT")
if out:
    Path(out).write_text(json.dumps(args), encoding="utf-8")

mode = os.environ.get("FAKE_QWEN_MODE", "ok_review")
if mode == "fail":
    print("boom", file=sys.stderr)
    sys.exit(1)

prompt = sys.stdin.read()
assert "PLAN SHA256" in prompt, "reviewer did not receive the runner prompt"

REVIEW = json.dumps({"verdict": "APPROVED", "summary": "ok", "findings": [],
                     "coverage": ["PLAN.md"], "limitations": []})
SESSION = args[args.index("--resume") + 1] if "--resume" in args else "123e4567-e89b-12d3-a456-426614174000"

def emit(event):
    print(json.dumps(event))

def assistant(text=None, calls=None):
    content = []
    if calls:
        content.append({"functionCalls": calls})
    if text is not None:
        content.append({"text": text})
    return {"type": "assistant", "session_id": SESSION,
            "message": {"role": "model", "content": content}}

def start():
    emit({"type": "system", "subtype": "session_start", "session_id": SESSION})

def finish():
    emit({"type": "result", "subtype": "success", "session_id": SESSION})

if mode == "ok_review":
    start()
    emit(assistant(calls=[{"name": "read", "args": {"path": "PLAN.md"}}]))
    emit(assistant(text=REVIEW))
    finish()
elif mode == "ok_review_fenced":
    start()
    emit(assistant(text="```json\n" + REVIEW + "\n```"))
    finish()
elif mode == "denied_tool":
    start()
    emit(assistant(calls=[{"name": "write", "args": {"path": "evil.txt"}}]))
    emit(assistant(text=REVIEW))
    finish()
elif mode == "error_event":
    start()
    emit({"type": "error", "message": "provider exploded"})
    finish()
elif mode == "no_session":
    emit({"type": "system", "subtype": "session_start"})
    emit(assistant(text=REVIEW))
    finish()
elif mode == "ok_build":
    start()
    emit(assistant(calls=[{"name": "write", "args": {"path": "out.txt"}}]))
    emit(assistant(text="Report: wrote the file. Proof not run by builder."))
    finish()
else:
    raise SystemExit("unknown fake mode " + mode)
'''


FAKE_OPENCODE = r'''
import json, os, sys
from pathlib import Path

args = sys.argv[1:]
if "--version" in args:
    print(os.environ.get("FAKE_OPENCODE_VERSION", "1.18.29-fake"))
    sys.exit(0)

out = os.environ.get("FAKE_OPENCODE_ARGV_OUT")
if out:
    Path(out).write_text(json.dumps(args), encoding="utf-8")

mode = os.environ.get("FAKE_OPENCODE_MODE", "ok_review")
if mode == "fail":
    print("boom", file=sys.stderr)
    sys.exit(1)

prompt = sys.stdin.read()
assert "PLAN SHA256" in prompt, "reviewer did not receive the runner prompt"

REVIEW = json.dumps({"verdict": "APPROVED", "summary": "ok", "findings": [],
                     "coverage": ["PLAN.md"], "limitations": []})
SESSION = args[args.index("--session") + 1] if "--session" in args else "ses_fake0123456789abcd"
if mode == "wrong_session":
    SESSION = "ses_other0123456789abcd"

def emit(event):
    print(json.dumps(event))

def step_start():
    return {"type": "step_start", "timestamp": 1, "sessionID": SESSION,
            "part": {"id": "prt_0", "sessionID": SESSION, "messageID": "msg_1", "type": "step-start"}}

def step_finish():
    return {"type": "step_finish", "timestamp": 3, "sessionID": SESSION,
            "part": {"id": "prt_9", "sessionID": SESSION, "messageID": "msg_1", "type": "step-finish",
                     "reason": "stop", "cost": 0.01, "tokens": {"input": 10, "output": 5}}}

def tool_event(name):
    return {"type": "tool_use", "timestamp": 2, "sessionID": SESSION,
            "part": {"partID": "prt_2", "sessionID": SESSION, "messageID": "msg_1", "type": "tool",
                     "id": "tool_1", "tool": name,
                     "state": {"status": "completed", "input": {}, "output": "",
                               "time": {"start": 2, "end": 2}}}}

def text_event(delta):
    return {"type": "text", "timestamp": 2, "sessionID": SESSION,
            "part": {"id": "prt_3", "sessionID": SESSION, "messageID": "msg_1", "type": "text",
                     "text": delta, "time": {"start": 2, "end": 3}}}

if mode in ("ok_review", "ok_review_fenced", "denied_tool", "no_text", "wrong_session"):
    emit(step_start())
    if mode == "denied_tool":
        emit(tool_event("edit"))
    else:
        emit(tool_event("read"))
    if mode != "no_text":
        body = ("```json\n" + REVIEW + "\n```") if mode == "ok_review_fenced" else REVIEW
        # Text arrives as growing deltas, like the real CLI; reconstruction must join them.
        half = len(body) // 2
        emit(text_event(body[:half]))
        emit(text_event(body[half:]))
    emit(step_finish())
elif mode == "ok_build":
    emit(step_start())
    emit(tool_event("edit"))
    emit(text_event("Report: wrote the file. Proof not run by builder."))
    emit(step_finish())
elif mode == "error_event":
    emit(step_start())
    emit({"type": "error", "timestamp": 2, "sessionID": SESSION,
          "error": {"name": "UnknownError", "data": {"message": "provider exploded"}}})
elif mode == "no_session":
    emit({"type": "text", "timestamp": 2,
          "part": {"id": "prt_3", "messageID": "msg_1", "type": "text", "text": REVIEW,
                   "time": {"start": 2, "end": 3}}})
    emit({"type": "step_finish", "timestamp": 3,
          "part": {"id": "prt_9", "messageID": "msg_1", "type": "step-finish"}})
elif mode == "no_step":
    emit(text_event(REVIEW))
elif mode == "not_json":
    print("this is not json")
    sys.exit(0)
else:
    raise SystemExit("unknown fake mode " + mode)
'''


class KimiHarness(unittest.TestCase):
    """Creates a temp repo, a Kimi config, and the fake CLI. Tests choose the fake mode per run."""

    config_text = (
        'default_permission_mode = "auto"\n'
        'default_model = "kimi-code/k3-256k"\n\n'
        '[thinking]\nenabled = true\neffort = "high"\n\n'
        '[models."kimi-code/k3-256k"]\nprovider = "managed:kimi-code"\nmodel = "k3-256k"\n\n'
        '[models."kimi-code/kimi-for-coding"]\nprovider = "managed:kimi-code"\nmodel = "kimi-for-coding"\n'
    )

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="trident-tests-"))
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        (self.repo / "PLAN.md").write_text(PLAN, encoding="utf-8")
        self.kimi_home = self.tmp / "kimi-home"
        self.kimi_home.mkdir()
        (self.kimi_home / "config.toml").write_text(self.config_text, encoding="utf-8")
        self.fake = self.tmp / "fake_kimi.py"
        self.fake.write_text(FAKE_KIMI, encoding="utf-8")
        self.argv_out = self.tmp / "argv.json"
        self.artifacts = self.tmp / "artifacts"
        env = mock.patch.dict(os.environ, {
            "KIMI_CODE_HOME": str(self.kimi_home),
            "FAKE_ARGV_OUT": str(self.argv_out),
            "FAKE_KIMI_MODE": "ok_review",
        })
        env.start()
        self.addCleanup(env.stop)
        patcher = mock.patch.object(runner, "cli_prefix",
                                    lambda provider, override=None: [sys.executable, str(self.fake)])
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_cli(self, *extra: str, mode: str = "ok_review", plan: str = "PLAN.md"):
        os.environ["FAKE_KIMI_MODE"] = mode
        argv = [*extra, "--repo", str(self.repo), "--plan", plan,
                "--artifacts", str(self.artifacts)]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = runner.main(argv)
        # stdout is a one-line launch notice, then the indented record; preflight errors go to stderr only.
        parts = out.getvalue().split("\n{\n")
        record = json.loads("{\n" + parts[-1]) if len(parts) > 1 else None
        return code, record, err.getvalue()

    def fake_argv(self) -> list[str]:
        return json.loads(self.argv_out.read_text(encoding="utf-8"))


class KimiReviewTests(KimiHarness):
    def test_success_records_tool_audit_and_argv(self):
        code, record, err = self.run_cli("review", "--host", "codex", "--provider", "kimi",
                                         "--model", "kimi-code/k3-256k")
        self.assertEqual(code, 0, err)
        self.assertEqual(record["status"], "completed")
        self.assertEqual(record["response"]["verdict"], "APPROVED")
        self.assertEqual(record["tool_calls"], {"Read": 1})
        self.assertEqual(record["session_id"], "session_test")
        self.assertNotIn("read_warning", record)
        argv = self.fake_argv()
        self.assertIn("--agent-file", argv)
        self.assertIn("--add-dir", argv)
        self.assertEqual(argv[argv.index("-m") + 1], "kimi-code/k3-256k")
        self.assertNotIn("--resume", argv)
        self.assertNotIn("--session", argv)
        self.assertEqual(record["kimi"]["model_alias"], "kimi-code/k3-256k")
        self.assertEqual(record["kimi"]["tool_allowlist"], ["Read", "Grep", "Glob"])
        self.assertEqual(record["parts_read"], ["prompt.txt"])

    def test_agent_file_enforces_read_only_allowlist(self):
        self.run_cli("review", "--host", "codex", "--provider", "kimi")
        text = next(self.artifacts.rglob("agent.md")).read_text(encoding="utf-8")
        self.assertIn("tools: Read, Grep, Glob", text)
        self.assertIn("disallowedTools: Agent, Skill", text)
        self.assertNotIn("Bash", runner.KIMI_REVIEW_TOOLS)

    def test_fenced_json_is_accepted(self):
        code, record, err = self.run_cli("review", "--host", "codex", "--provider", "kimi",
                                         mode="ok_review_fenced")
        self.assertEqual(code, 0, err)
        self.assertEqual(record["response"]["verdict"], "APPROVED")

    def test_prose_around_single_json_block_is_accepted(self):
        code, record, err = self.run_cli("review", "--host", "codex", "--provider", "kimi",
                                         mode="ok_review_prose")
        self.assertEqual(code, 0, err)
        self.assertEqual(record["response"]["verdict"], "APPROVED")

    def test_several_json_blocks_fail_but_keep_the_audit(self):
        code, record, err = self.run_cli("review", "--host", "codex", "--provider", "kimi",
                                         mode="two_blocks")
        self.assertEqual(code, 1)
        self.assertIn("exactly one JSON block", record["error"])
        self.assertEqual(record["tool_calls"], {"Read": 1})
        self.assertEqual(record["session_id"], "session_test")

    def test_failed_verdict_keeps_session_hint_and_tool_audit(self):
        code, record, err = self.run_cli("review", "--host", "codex", "--provider", "kimi",
                                         mode="malformed_json")
        self.assertEqual(code, 1)
        self.assertEqual(record["tool_calls"], {"Read": 1})
        self.assertEqual(record["session_id"], "session_test")
        self.assertEqual(record["kimi"]["effort_applied"], "high")

    def test_approval_without_any_read_fails_coverage(self):
        # An APPROVED verdict is worthless if the reviewer never read the prompt it was given.
        code, record, err = self.run_cli("review", "--host", "codex", "--provider", "kimi",
                                         mode="approved_no_read")
        self.assertEqual(code, 1)
        self.assertIn("did not read prompt part", record["error"])

    def test_process_failure_is_not_approval(self):
        code, record, err = self.run_cli("review", "--host", "codex", "--provider", "kimi",
                                         mode="fail")
        self.assertEqual(code, 1)
        self.assertIn("exited 1", err + json.dumps(record or {}))

    def test_response_without_text_fails(self):
        code, record, err = self.run_cli("review", "--host", "codex", "--provider", "kimi",
                                         mode="no_text")
        self.assertEqual(code, 1)
        self.assertIn("no assistant text", json.dumps(record))

    def test_malformed_json_fails(self):
        code, record, err = self.run_cli("review", "--host", "codex", "--provider", "kimi",
                                         mode="malformed_json")
        self.assertEqual(code, 1)
        self.assertIn("exactly one JSON block", json.dumps(record))

    def test_invalid_json_inside_block_fails(self):
        # Bare JSON that does not parse is reported as invalid JSON, not as a block-count problem.
        self.assertRaises(runner.RunError, runner.parse_kimi_json, "{not json")
        with self.assertRaisesRegex(runner.RunError, "not valid JSON"):
            runner.parse_kimi_json("```json\n{not json}\n```")

    def test_non_json_stream_line_fails(self):
        code, record, err = self.run_cli("review", "--host", "codex", "--provider", "kimi",
                                         mode="bad_line")
        self.assertEqual(code, 1)
        self.assertIn("non-JSON line", json.dumps(record))

    def test_tool_outside_allowlist_fails(self):
        code, record, err = self.run_cli("review", "--host", "codex", "--provider", "kimi",
                                         mode="bad_tool")
        self.assertEqual(code, 1)
        self.assertIn("outside the allowlist", json.dumps(record))
        self.assertIn("Bash", json.dumps(record))

    def test_unconfigured_model_refuses_before_launch(self):
        self.argv_out.unlink(missing_ok=True)
        code, record, err = self.run_cli("review", "--host", "codex", "--provider", "kimi",
                                         "--model", "kimi-code/not-configured")
        self.assertEqual(code, 1)
        self.assertIn("not configured", err)
        self.assertFalse(self.argv_out.exists(), "CLI must not launch for an unconfigured model")

    def test_effort_mismatch_refuses_and_does_not_edit_config(self):
        before = (self.kimi_home / "config.toml").read_text(encoding="utf-8")
        code, record, err = self.run_cli("review", "--host", "codex", "--provider", "kimi",
                                         "--effort", "low")
        self.assertEqual(code, 1)
        self.assertIn("no per-call effort flag", err)
        self.assertEqual((self.kimi_home / "config.toml").read_text(encoding="utf-8"), before)

    def test_matching_effort_is_accepted(self):
        code, record, err = self.run_cli("review", "--host", "codex", "--provider", "kimi",
                                         "--effort", "high")
        self.assertEqual(code, 0, err)
        self.assertEqual(record["kimi"]["effort_applied"], "high")

    def test_resume_is_fresh_session_with_prior_response(self):
        code, first, err = self.run_cli("review", "--host", "codex", "--provider", "kimi")
        self.assertEqual(code, 0, err)
        prior = self.tmp / "prior.json"
        prior.write_text(json.dumps(first), encoding="utf-8")
        code, second, err = self.run_cli("review", "--host", "codex", "--provider", "kimi",
                                         "--resume", str(prior))
        self.assertEqual(code, 0, err)
        self.assertEqual(second["continuity"], "fresh-session-with-prior-review")
        self.assertNotIn("--resume", self.fake_argv())
        prompt = Path(second["artifacts"], "prompt.txt").read_text(encoding="utf-8")
        self.assertIn("PRIOR RESPONSE FROM THE PREVIOUS INDEPENDENT SESSION", prompt)


class KimiSplitTests(KimiHarness):
    """Prompts above the Read limit are split; the reviewer must read every part."""

    def setUp(self):
        super().setUp()
        # Big enough that the full prompt exceeds the Read limit.
        (self.repo / "PLAN.md").write_text(PLAN + ("x" * 60000), encoding="utf-8")

    def test_large_prompt_is_split_and_every_part_is_read(self):
        code, record, err = self.run_cli("review", "--host", "codex", "--provider", "kimi")
        self.assertEqual(code, 0, err)
        self.assertTrue(record["kimi"]["split"])
        self.assertGreater(record["kimi"]["prompt_chars"], runner.KIMI_READ_LIMIT_CHARS)
        parts = record["kimi"]["parts"]
        self.assertEqual(parts[0], "prompt.txt")
        self.assertGreater(len(parts), 2)
        self.assertEqual(record["parts_read"], parts)
        index = Path(record["artifacts"], "prompt.txt").read_text(encoding="utf-8")
        self.assertIn("prompt-part-01.txt", index)

    def test_missing_part_fails_the_review(self):
        code, record, err = self.run_cli("review", "--host", "codex", "--provider", "kimi",
                                         mode="split_missing_part")
        self.assertEqual(code, 1)
        self.assertIn("did not read prompt part", record["error"])
        self.assertTrue(record["kimi"]["split"])

    def test_every_part_is_under_the_read_limit(self):
        for sample in ["a" * 1000 + "\n", "line\n" * 5000]:
            for chunk in runner.chunk_text(sample):
                self.assertLessEqual(len(chunk), runner.KIMI_CHUNK_CHARS)
                self.assertLessEqual(chunk.count("\n"), runner.KIMI_CHUNK_LINES)
        long_line = "y" * (runner.KIMI_CHUNK_CHARS * 2 + 5)
        chunks = runner.chunk_text(long_line)
        self.assertTrue(all(len(chunk) <= runner.KIMI_CHUNK_CHARS for chunk in chunks))
        self.assertEqual("".join(chunks), long_line)

    def test_small_prompt_is_not_split(self):
        (self.repo / "PLAN.md").write_text(PLAN, encoding="utf-8")
        code, record, err = self.run_cli("review", "--host", "codex", "--provider", "kimi")
        self.assertEqual(code, 0, err)
        self.assertFalse(record["kimi"]["split"])
        self.assertEqual(record["kimi"]["parts"], ["prompt.txt"])


class KimiInspectDiffTests(KimiHarness):
    """The tracked diff goes to its own parts when large, and stays inline when small."""

    def _commit_with_change(self, plan_body: str):
        import subprocess
        (self.repo / "PLAN.md").write_text(plan_body, encoding="utf-8")
        (self.repo / "src.txt").write_text("a\n", encoding="utf-8")
        for cmd in (["git", "init", "-q"], ["git", "add", "."],
                    ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init"]):
            subprocess.run(cmd, cwd=self.repo, check=True, capture_output=True)

    def test_large_diff_becomes_diff_parts_read_by_the_reviewer(self):
        self._commit_with_change(PLAN)
        (self.repo / "src.txt").write_text("".join(f"line {i}\n" for i in range(8000)), encoding="utf-8")
        code, record, err = self.run_cli("inspect", "--host", "codex", "--provider", "kimi", "--base", "HEAD")
        self.assertEqual(code, 0, err)
        parts = record["kimi"]["parts"]
        diff_parts = [p for p in parts if p.startswith("diff-part-")]
        self.assertGreater(len(diff_parts), 0)
        self.assertEqual(record["parts_read"], parts)
        head = Path(record["artifacts"], "prompt-part-01.txt").read_text(encoding="utf-8")
        self.assertNotIn("line 7999", head, "the diff must not be inlined in the prompt parts")
        diff_text = "".join(Path(record["artifacts"], p).read_text(encoding="utf-8") for p in diff_parts)
        self.assertIn("line 7999", diff_text)

    def test_small_diff_stays_inline_in_prompt(self):
        self._commit_with_change(PLAN)
        (self.repo / "src.txt").write_text("changed\n", encoding="utf-8")
        code, record, err = self.run_cli("inspect", "--host", "codex", "--provider", "kimi", "--base", "HEAD")
        self.assertEqual(code, 0, err)
        self.assertFalse(record["kimi"]["split"])
        prompt = Path(record["artifacts"], "prompt.txt").read_text(encoding="utf-8")
        self.assertIn("TRACKED DIFF:", prompt)
        self.assertIn("changed", prompt)


class KimiPathScopeTests(KimiHarness):
    """Kimi must not read or search outside the repo: its review would describe the wrong checkout."""

    def extra_read(self, path: str):
        os.environ["FAKE_EXTRA_READ"] = path
        self.addCleanup(os.environ.pop, "FAKE_EXTRA_READ", None)

    def test_relative_read_inside_repo_is_allowed(self):
        self.extra_read("PLAN.md")
        code, record, err = self.run_cli("review", "--host", "codex", "--provider", "kimi")
        self.assertEqual(code, 0, err)
        self.assertEqual(record["outside_paths"], [])

    def test_absolute_read_outside_repo_fails_and_names_the_path(self):
        outside = str(self.tmp / "elsewhere" / "withdrawal-payouts.ts")
        self.extra_read(outside)
        code, record, err = self.run_cli("review", "--host", "codex", "--provider", "kimi")
        self.assertEqual(code, 1)
        self.assertIn("outside the repo root", record["error"])
        self.assertIn(outside, record["outside_paths"])
        self.assertNotIn("response", record, "a run that read outside the repo must not produce a verdict")

    def test_repo_root_is_written_into_the_kimi_prompt(self):
        code, record, err = self.run_cli("review", "--host", "codex", "--provider", "kimi")
        self.assertEqual(code, 0, err)
        prompt = Path(record["artifacts"], "prompt.txt").read_text(encoding="utf-8")
        # The runner resolves the repo before writing the root note (tmp dirs may
        # be symlinked or use 8.3 short names on CI runners).
        self.assertIn(f"REPO ROOT (absolute): {self.repo.resolve()}", prompt)

    def test_plan_file_is_allowed_but_its_folder_is_not(self):
        scratch = self.tmp / "scratch"
        (scratch / "runs" / "old").mkdir(parents=True)
        plan = scratch / "plan.md"
        plan.write_text(PLAN, encoding="utf-8")
        (scratch / "runs" / "old" / "stdout.txt").write_text("previous review", encoding="utf-8")
        # The plan itself is read by the runner's prompt, so it must be allowed.
        code, record, err = self.run_cli("review", "--host", "codex", "--provider", "kimi", plan=str(plan))
        self.assertEqual(code, 0, err)
        self.assertEqual(record["outside_paths"], [])
        # A sibling file in the same folder, such as an earlier run's output, must be refused.
        self.extra_read(str(scratch / "runs" / "old" / "stdout.txt"))
        code, record, err = self.run_cli("review", "--host", "codex", "--provider", "kimi", plan=str(plan))
        self.assertEqual(code, 1)
        self.assertTrue(any("stdout.txt" in p for p in record["outside_paths"]))

    def test_own_session_spill_is_allowed_and_other_sessions_are_not(self):
        store = self.kimi_home / "sessions" / "wd_x" / "session_test" / "agents" / "main" / "tool-results"
        store.mkdir(parents=True)
        own = store / "own.txt"
        own.write_text("big tool output", encoding="utf-8")
        self.extra_read(str(own))
        code, record, err = self.run_cli("review", "--host", "codex", "--provider", "kimi")
        self.assertEqual(code, 0, err)
        other = self.kimi_home / "sessions" / "wd_x" / "session_other" / "agents" / "main" / "tool-results"
        other.mkdir(parents=True)
        self.extra_read(str(other / "theirs.txt"))
        code, record, err = self.run_cli("review", "--host", "codex", "--provider", "kimi")
        self.assertEqual(code, 1)
        self.assertTrue(any("theirs.txt" in p for p in record["outside_paths"]))

    def test_path_rule(self):
        repo = "C:/work/wt"
        roots = ["c:/work/wt", "c:/work/scratch"]
        self.assertFalse(runner.path_outside("src/a.ts", repo, roots))
        self.assertFalse(runner.path_outside("C:/work/wt/src/a.ts", repo, roots))
        self.assertFalse(runner.path_outside("C:\\work\\scratch\\plan.md", repo, roots))
        self.assertTrue(runner.path_outside("C:/work/other/a.ts", repo, roots))
        self.assertTrue(runner.path_outside("../other/a.ts", repo, roots))
        self.assertTrue(runner.path_outside("C:/work/wtx/a.ts", repo, roots), "prefix must end at a separator")


class KimiBuildTests(KimiHarness):
    def _commit_repo(self):
        import subprocess
        for cmd in (["git", "init", "-q"], ["git", "add", "."],
                    ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init"]):
            subprocess.run(cmd, cwd=self.repo, check=True, capture_output=True)

    def test_build_requires_explicit_permission_acceptance(self):
        self._commit_repo()
        code, record, err = self.run_cli("build", "--host", "codex", "--provider", "kimi",
                                         "--unreviewed-spec", "--proof", "echo ok", mode="ok_build")
        self.assertEqual(code, 1)
        self.assertIn("--accept-kimi-config-permission", err)

    def test_build_with_acceptance_records_it(self):
        self._commit_repo()
        code, record, err = self.run_cli("build", "--host", "codex", "--provider", "kimi",
                                         "--unreviewed-spec", "--proof", "echo ok",
                                         "--accept-kimi-config-permission", mode="ok_build")
        self.assertEqual(code, 0, err)
        self.assertTrue(record["kimi"]["build_permission_accepted"])
        self.assertIn("Write", record["tool_calls"])
        self.assertIn("Report:", record["response"])


class DeepSeekHarness(unittest.TestCase):
    """Creates a temp repo and a fake dsh CLI. Tests choose the fake mode per run."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="trident-tests-"))
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        (self.repo / "PLAN.md").write_text(PLAN, encoding="utf-8")
        self.fake = self.tmp / "fake_dsh.py"
        self.fake.write_text(FAKE_DSH, encoding="utf-8")
        self.argv_out = self.tmp / "dsh-argv.json"
        self.env_out = self.tmp / "dsh-env.json"
        self.artifacts = self.tmp / "artifacts"
        env = mock.patch.dict(os.environ, {
            "FAKE_DSH_ARGV_OUT": str(self.argv_out),
            "FAKE_DSH_ENV_OUT": str(self.env_out),
            "FAKE_DSH_MODE": "ok_review",
        })
        env.start()
        self.addCleanup(env.stop)
        patcher = mock.patch.object(runner, "cli_prefix",
                                    lambda provider, override=None: [sys.executable, str(self.fake)])
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_cli(self, *extra: str, mode: str = "ok_review"):
        os.environ["FAKE_DSH_MODE"] = mode
        argv = [*extra, "--repo", str(self.repo), "--plan", "PLAN.md",
                "--artifacts", str(self.artifacts)]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = runner.main(argv)
        text = out.getvalue()
        if "\n{\n" in text:
            record = json.loads("{\n" + text.split("\n{\n")[-1])  # launch notice + record
        elif text.strip().startswith("{"):
            record = json.loads(text)  # failure before launch: record only, no notice line
        else:
            record = None
        return code, record, err.getvalue()

    def fake_argv(self) -> list:
        return json.loads(self.argv_out.read_text(encoding="utf-8"))

    def fake_env(self) -> dict:
        return json.loads(self.env_out.read_text(encoding="utf-8"))


class DeepSeekReviewTests(DeepSeekHarness):
    def test_review_records_verdict_permission_and_argv(self):
        code, record, err = self.run_cli("review", "--host", "claude", "--provider", "deepseek")
        self.assertEqual(code, 0, err)
        self.assertEqual(record["status"], "completed")
        self.assertEqual(record["response"]["verdict"], "APPROVED")
        self.assertEqual(record["session_id"], "session-ds-new")
        self.assertEqual(record["deepseek"]["permission_mode"], "read-only")
        self.assertEqual(self.fake_env()["DSH_PERMISSION_MODE"], "read-only")
        argv = self.fake_argv()
        self.assertEqual(argv[:2], ["--profile", "headless"])
        self.assertIn("--json", argv)
        self.assertNotIn("--session-id", argv)

    def test_fenced_json_is_accepted(self):
        code, record, err = self.run_cli("review", "--host", "claude", "--provider", "deepseek",
                                         mode="ok_review_fenced")
        self.assertEqual(code, 0, err)
        self.assertEqual(record["response"]["verdict"], "APPROVED")

    def test_model_flag_is_passed_through(self):
        code, record, err = self.run_cli("review", "--host", "claude", "--provider", "deepseek",
                                         "--model", "deepseek-chat")
        self.assertEqual(code, 0, err)
        argv = self.fake_argv()
        self.assertEqual(argv[argv.index("--model") + 1], "deepseek-chat")

    def test_incomplete_turn_is_not_approval(self):
        code, record, err = self.run_cli("review", "--host", "claude", "--provider", "deepseek",
                                         mode="incomplete")
        self.assertEqual(code, 1)
        self.assertIn("did not complete", record["error"])

    def test_missing_session_fails(self):
        code, record, err = self.run_cli("review", "--host", "claude", "--provider", "deepseek",
                                         mode="no_session")
        self.assertEqual(code, 1)
        self.assertIn("no session id", record["error"])

    def test_non_json_stdout_fails(self):
        code, record, err = self.run_cli("review", "--host", "claude", "--provider", "deepseek",
                                         mode="not_json")
        self.assertEqual(code, 1)
        self.assertIn("--json projection", record["error"])

    def test_old_cli_version_is_refused_before_launch(self):
        self.argv_out.unlink(missing_ok=True)
        os.environ["FAKE_DSH_VERSION"] = "0.1.5-rc.2-fake"
        self.addCleanup(os.environ.pop, "FAKE_DSH_VERSION", None)
        code, record, err = self.run_cli("review", "--host", "claude", "--provider", "deepseek")
        self.assertEqual(code, 1)
        self.assertIn("older than the documented", record["error"])
        self.assertFalse(self.argv_out.exists(), "CLI must not launch for an undocumented version")

    def test_effort_is_refused(self):
        code, record, err = self.run_cli("review", "--host", "claude", "--provider", "deepseek",
                                         "--effort", "high")
        self.assertEqual(code, 1)
        self.assertIn("no per-call effort", record["error"])

    def test_resume_continues_the_same_session(self):
        code, first, err = self.run_cli("review", "--host", "claude", "--provider", "deepseek")
        self.assertEqual(code, 0, err)
        prior = self.tmp / "prior.json"
        prior.write_text(json.dumps(first), encoding="utf-8")
        code, second, err = self.run_cli("review", "--host", "claude", "--provider", "deepseek",
                                         "--resume", str(prior))
        self.assertEqual(code, 0, err)
        argv = self.fake_argv()
        self.assertEqual(argv[argv.index("--session-id") + 1], first["session_id"])
        self.assertEqual(second["session_id"], first["session_id"])


class DeepSeekBuildTests(DeepSeekHarness):
    def _commit_repo(self):
        import subprocess
        for cmd in (["git", "init", "-q"], ["git", "add", "."],
                    ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init"]):
            subprocess.run(cmd, cwd=self.repo, check=True, capture_output=True)

    def test_build_uses_workspace_write(self):
        self._commit_repo()
        code, record, err = self.run_cli("build", "--host", "claude", "--builder", "deepseek",
                                         "--unreviewed-spec", "--proof", "echo ok", mode="ok_build")
        self.assertEqual(code, 0, err)
        self.assertEqual(record["deepseek"]["permission_mode"], "workspace-write")
        self.assertEqual(self.fake_env()["DSH_PERMISSION_MODE"], "workspace-write")
        self.assertIn("Report:", record["response"])


class QwenHarness(unittest.TestCase):
    """Creates a temp repo and a fake qwen CLI. Tests choose the fake mode per run."""
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="trident-tests-"))
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        (self.repo / "PLAN.md").write_text(PLAN, encoding="utf-8")
        self.fake = self.tmp / "fake_qwen.py"
        self.fake.write_text(FAKE_QWEN, encoding="utf-8")
        self.argv_out = self.tmp / "qwen-argv.json"
        self.artifacts = self.tmp / "artifacts"
        env = mock.patch.dict(os.environ, {
            "FAKE_QWEN_ARGV_OUT": str(self.argv_out),
            "FAKE_QWEN_MODE": "ok_review",
        })
        env.start()
        self.addCleanup(env.stop)
        patcher = mock.patch.object(runner, "cli_prefix",
                                    lambda provider, override=None: [sys.executable, str(self.fake)])
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_cli(self, *extra: str, mode: str = "ok_review"):
        os.environ["FAKE_QWEN_MODE"] = mode
        argv = [*extra, "--repo", str(self.repo), "--plan", "PLAN.md",
                "--artifacts", str(self.artifacts)]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = runner.main(argv)
        text = out.getvalue()
        if "\n{\n" in text:
            record = json.loads("{\n" + text.split("\n{\n")[-1])  # launch notice + record
        elif text.strip().startswith("{"):
            record = json.loads(text)  # failure before launch: record only, no notice line
        else:
            record = None
        return code, record, err.getvalue()

    def fake_argv(self) -> list:
        return json.loads(self.argv_out.read_text(encoding="utf-8"))


class QwenReviewTests(QwenHarness):
    def test_review_records_verdict_boundary_and_argv(self):
        code, record, err = self.run_cli("review", "--host", "claude", "--provider", "qwen")
        self.assertEqual(code, 0, err)
        self.assertEqual(record["status"], "completed")
        self.assertEqual(record["response"]["verdict"], "APPROVED")
        self.assertEqual(record["session_id"], "123e4567-e89b-12d3-a456-426614174000")
        self.assertEqual(record["qwen"]["approval_mode"], "plan")
        self.assertEqual(record["qwen"]["excluded_tools"], ["shell", "write", "edit"])
        argv = self.fake_argv()
        self.assertEqual(argv[:2], ["-p", "--output-format"])
        self.assertIn("stream-json", argv)
        self.assertIn("--safe-mode", argv)
        self.assertEqual(argv[argv.index("--exclude-tools") + 1], "shell,write,edit")

    def test_fenced_json_is_accepted(self):
        code, record, err = self.run_cli("review", "--host", "claude", "--provider", "qwen",
                                         mode="ok_review_fenced")
        self.assertEqual(code, 0, err)
        self.assertEqual(record["response"]["verdict"], "APPROVED")

    def test_model_flag_is_passed_through(self):
        code, record, err = self.run_cli("review", "--host", "claude", "--provider", "qwen",
                                         "--model", "qwen3-coder")
        self.assertEqual(code, 0, err)
        argv = self.fake_argv()
        self.assertEqual(argv[argv.index("-m") + 1], "qwen3-coder")

    def test_denied_tool_fails_but_keeps_the_audit(self):
        code, record, err = self.run_cli("review", "--host", "claude", "--provider", "qwen",
                                         mode="denied_tool")
        self.assertEqual(code, 1)
        self.assertIn("excludes", record["error"])
        self.assertEqual(record["tool_denials"], ["write"])
        self.assertNotIn("response", record, "a run that escaped the boundary must not produce a verdict")

    def test_error_event_fails(self):
        code, record, err = self.run_cli("review", "--host", "claude", "--provider", "qwen",
                                         mode="error_event")
        self.assertEqual(code, 1)
        self.assertIn("error event", record["error"])

    def test_missing_session_fails(self):
        code, record, err = self.run_cli("review", "--host", "claude", "--provider", "qwen",
                                         mode="no_session")
        self.assertEqual(code, 1)
        self.assertIn("no session id", record["error"])

    def test_effort_is_refused(self):
        code, record, err = self.run_cli("review", "--host", "claude", "--provider", "qwen",
                                         "--effort", "high")
        self.assertEqual(code, 1)
        self.assertIn("no per-call effort", record["error"])

    def test_resume_continues_the_same_session(self):
        code, first, err = self.run_cli("review", "--host", "claude", "--provider", "qwen")
        self.assertEqual(code, 0, err)
        prior = self.tmp / "prior.json"
        prior.write_text(json.dumps(first), encoding="utf-8")
        code, second, err = self.run_cli("review", "--host", "claude", "--provider", "qwen",
                                         "--resume", str(prior))
        self.assertEqual(code, 0, err)
        argv = self.fake_argv()
        self.assertEqual(argv[argv.index("--resume") + 1], first["session_id"])
        self.assertEqual(second["session_id"], first["session_id"])


class QwenBuildTests(QwenHarness):
    def _commit_repo(self):
        import subprocess
        for cmd in (["git", "init", "-q"], ["git", "add", "."],
                    ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init"]):
            subprocess.run(cmd, cwd=self.repo, check=True, capture_output=True)

    def test_build_uses_yolo_without_exclusions(self):
        self._commit_repo()
        code, record, err = self.run_cli("build", "--host", "claude", "--builder", "qwen",
                                         "--unreviewed-spec", "--proof", "echo ok", mode="ok_build")
        self.assertEqual(code, 0, err)
        self.assertEqual(record["qwen"]["approval_mode"], "yolo")
        argv = self.fake_argv()
        self.assertNotIn("--exclude-tools", argv)
        self.assertIn("Report:", record["response"])


class OpenCodeHarness(unittest.TestCase):
    """Creates a temp repo and a fake opencode CLI. Tests choose the fake mode per run."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="trident-tests-"))
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        (self.repo / "PLAN.md").write_text(PLAN, encoding="utf-8")
        self.fake = self.tmp / "fake_opencode.py"
        self.fake.write_text(FAKE_OPENCODE, encoding="utf-8")
        self.argv_out = self.tmp / "opencode-argv.json"
        self.artifacts = self.tmp / "artifacts"
        env = mock.patch.dict(os.environ, {
            "FAKE_OPENCODE_ARGV_OUT": str(self.argv_out),
            "FAKE_OPENCODE_MODE": "ok_review",
        })
        env.start()
        self.addCleanup(env.stop)
        patcher = mock.patch.object(runner, "cli_prefix",
                                    lambda provider, override=None: [sys.executable, str(self.fake)])
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_cli(self, *extra: str, mode: str = "ok_review"):
        os.environ["FAKE_OPENCODE_MODE"] = mode
        argv = [*extra, "--repo", str(self.repo), "--plan", "PLAN.md",
                "--artifacts", str(self.artifacts)]
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = runner.main(argv)
        text = out.getvalue()
        if "\n{\n" in text:
            record = json.loads("{\n" + text.split("\n{\n")[-1])  # launch notice + record
        elif text.strip().startswith("{"):
            record = json.loads(text)  # failure before launch: record only, no notice line
        else:
            record = None
        return code, record, err.getvalue()

    def fake_argv(self) -> list:
        return json.loads(self.argv_out.read_text(encoding="utf-8"))


class OpenCodeReviewTests(OpenCodeHarness):
    def test_review_records_verdict_boundary_and_argv(self):
        code, record, err = self.run_cli("review", "--host", "claude", "--provider", "opencode")
        self.assertEqual(code, 0, err)
        self.assertEqual(record["status"], "completed")
        self.assertEqual(record["response"]["verdict"], "APPROVED")
        self.assertEqual(record["session_id"], "ses_fake0123456789abcd")
        self.assertEqual(record["opencode"], {"agent": "plan", "auto": False, "pure": True,
                                              "denied_tools": list(runner.OPENCODE_DENIED_TOOLS)})
        self.assertEqual(record["usage"], {"tokens": {"input": 10, "output": 5}, "cost": 0.01})
        self.assertEqual(record["tool_calls"], {"read": 1})
        argv = self.fake_argv()
        self.assertEqual(argv[:2], ["run", "--format"])
        self.assertIn("json", argv)
        self.assertIn("--pure", argv)
        self.assertEqual(argv[argv.index("--agent") + 1], "plan")
        self.assertNotIn("--auto", argv)
        self.assertNotIn("--session", argv)

    def test_text_deltas_are_reconstructed_in_order(self):
        code, record, err = self.run_cli("review", "--host", "claude", "--provider", "opencode")
        self.assertEqual(code, 0, err)
        self.assertEqual(record["response"]["summary"], "ok")

    def test_fenced_json_is_accepted(self):
        code, record, err = self.run_cli("review", "--host", "claude", "--provider", "opencode",
                                         mode="ok_review_fenced")
        self.assertEqual(code, 0, err)
        self.assertEqual(record["response"]["verdict"], "APPROVED")

    def test_model_and_effort_flags_are_passed_through(self):
        code, record, err = self.run_cli("review", "--host", "claude", "--provider", "opencode",
                                         "--model", "anthropic/claude-fable-5-1", "--effort", "high")
        self.assertEqual(code, 0, err)
        argv = self.fake_argv()
        self.assertEqual(argv[argv.index("--model") + 1], "anthropic/claude-fable-5-1")
        self.assertEqual(argv[argv.index("--variant") + 1], "high")

    def test_denied_tool_fails_but_keeps_the_audit(self):
        code, record, err = self.run_cli("review", "--host", "claude", "--provider", "opencode",
                                         mode="denied_tool")
        self.assertEqual(code, 1)
        self.assertIn("excludes", record["error"])
        self.assertEqual(record["tool_denials"], ["edit"])
        self.assertNotIn("response", record, "a run that escaped the boundary must not produce a verdict")

    def test_error_event_fails(self):
        code, record, err = self.run_cli("review", "--host", "claude", "--provider", "opencode",
                                         mode="error_event")
        self.assertEqual(code, 1)
        self.assertIn("error event", record["error"])

    def test_missing_session_fails(self):
        code, record, err = self.run_cli("review", "--host", "claude", "--provider", "opencode",
                                         mode="no_session")
        self.assertEqual(code, 1)
        self.assertIn("session id", record["error"])

    def test_missing_step_fails(self):
        code, record, err = self.run_cli("review", "--host", "claude", "--provider", "opencode",
                                         mode="no_step")
        self.assertEqual(code, 1)
        self.assertIn("no completed step", record["error"])

    def test_non_json_stdout_fails(self):
        code, record, err = self.run_cli("review", "--host", "claude", "--provider", "opencode",
                                         mode="not_json")
        self.assertEqual(code, 1)
        self.assertIn("non-JSON line", record["error"])

    def test_old_cli_version_is_refused_before_launch(self):
        self.argv_out.unlink(missing_ok=True)
        os.environ["FAKE_OPENCODE_VERSION"] = "1.17.9-fake"
        self.addCleanup(os.environ.pop, "FAKE_OPENCODE_VERSION", None)
        code, record, err = self.run_cli("review", "--host", "claude", "--provider", "opencode")
        self.assertEqual(code, 1)
        self.assertIn("older than the documented", record["error"])
        self.assertFalse(self.argv_out.exists(), "CLI must not launch for an undocumented version")

    def test_resume_continues_the_same_session(self):
        code, first, err = self.run_cli("review", "--host", "claude", "--provider", "opencode")
        self.assertEqual(code, 0, err)
        prior = self.tmp / "prior.json"
        prior.write_text(json.dumps(first), encoding="utf-8")
        code, second, err = self.run_cli("review", "--host", "claude", "--provider", "opencode",
                                         "--resume", str(prior))
        self.assertEqual(code, 0, err)
        argv = self.fake_argv()
        self.assertEqual(argv[argv.index("--session") + 1], first["session_id"])
        self.assertEqual(second["session_id"], first["session_id"])

    def test_different_session_is_refused(self):
        code, first, err = self.run_cli("review", "--host", "claude", "--provider", "opencode")
        self.assertEqual(code, 0, err)
        prior = self.tmp / "prior.json"
        prior.write_text(json.dumps(first), encoding="utf-8")
        code, record, err = self.run_cli("review", "--host", "claude", "--provider", "opencode",
                                         "--resume", str(prior), mode="wrong_session")
        self.assertEqual(code, 1)
        self.assertIn("different session", record["error"])


class OpenCodeBuildTests(OpenCodeHarness):
    def _commit_repo(self):
        import subprocess
        for cmd in (["git", "init", "-q"], ["git", "add", "."],
                    ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init"]):
            subprocess.run(cmd, cwd=self.repo, check=True, capture_output=True)

    def test_build_uses_build_agent_with_auto(self):
        self._commit_repo()
        code, record, err = self.run_cli("build", "--host", "claude", "--builder", "opencode",
                                         "--unreviewed-spec", "--proof", "echo ok", mode="ok_build")
        self.assertEqual(code, 0, err)
        self.assertEqual(record["opencode"], {"agent": "build", "auto": True, "pure": True})
        argv = self.fake_argv()
        self.assertEqual(argv[argv.index("--agent") + 1], "build")
        self.assertIn("--auto", argv)
        self.assertIn("edit", record["tool_calls"], "builds are supposed to write")
        self.assertIn("Report:", record["response"])


class CliPrefixTests(unittest.TestCase):
    @unittest.skipIf(os.name != "nt", "npm .cmd shim resolution is Windows-specific")
    def test_npm_entry_native_exe_is_launched_directly(self):
        """opencode's npm package ships a bun-compiled opencode.exe next to the .cmd shim."""
        tmp = Path(tempfile.mkdtemp(prefix="trident-argv-"))
        exe = tmp / "node_modules" / "opencode-ai" / "bin" / "opencode.exe"
        exe.parent.mkdir(parents=True)
        exe.write_text("", encoding="utf-8")
        (tmp / "opencode.cmd").write_text("@echo off\r\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"PATH": str(tmp)}):
            self.assertEqual(runner.cli_prefix("opencode"), [str(exe)])


class ClaudeCodexCompatibilityTests(unittest.TestCase):
    """Pins the argv the original runner produced for Claude and Codex."""

    def setUp(self):
        self.run_dir = Path(tempfile.mkdtemp(prefix="trident-argv-"))

    def test_claude_review_argv_is_unchanged(self):
        argv = runner.command("claude", "review", self.run_dir)
        self.assertEqual(argv[:4], ["-p", "--output-format", "json", "--permission-prompts"])
        self.assertIn("--safe-mode", argv)
        self.assertEqual(argv[argv.index("--tools") + 1], "Read,Glob,Grep")
        self.assertEqual(argv[argv.index("--permission-mode") + 1], "dontAsk")

    def test_claude_build_uses_accept_edits(self):
        argv = runner.command("claude", "build", self.run_dir, model="m", effort="high")
        self.assertEqual(argv[argv.index("--permission-mode") + 1], "acceptEdits")
        self.assertEqual(argv[argv.index("--model") + 1], "m")
        self.assertEqual(argv[argv.index("--effort") + 1], "high")

    def test_codex_review_argv_is_unchanged(self):
        argv = runner.command("codex", "review", self.run_dir)
        self.assertEqual(argv[:3], ["exec", "-s", "read-only"])
        self.assertIn("--output-schema", argv)
        self.assertEqual(argv[-1], "-")

    def test_codex_resume_stays_read_only(self):
        session = "12345678-1234-1234-1234-123456789abc"
        argv = runner.command("codex", "review", self.run_dir, session=session)
        self.assertEqual(argv[:2], ["exec", "resume"])
        self.assertIn('sandbox_mode="read-only"', argv)


class RoleTests(unittest.TestCase):
    def test_default_reviewers_keep_previous_behaviour(self):
        self.assertEqual(runner.resolve_roles("claude")["reviewer"], "codex")
        self.assertEqual(runner.resolve_roles("codex")["reviewer"], "claude")
        self.assertEqual(runner.resolve_roles("claude", builder="codex")["inspector"], "claude")
        self.assertEqual(runner.resolve_roles("codex", builder="claude")["inspector"], "codex")

    def test_kimi_roles(self):
        roles = runner.resolve_roles("kimi")
        self.assertEqual(roles["reviewer"], "claude")
        self.assertEqual(roles["inspector"], "claude")
        self.assertEqual(runner.resolve_roles("codex", builder="kimi")["inspector"], "claude")

    def test_reviewer_must_differ_from_host(self):
        with self.assertRaises(runner.RunError):
            runner.resolve_roles("kimi", reviewer="kimi")

    def test_custom_pipeline_order_resolves_defaults(self):
        roles = runner.resolve_roles("claude", order=["claude", "kimi", "codex"])
        self.assertEqual(roles["reviewer"], "kimi")
        self.assertEqual(roles["builder"], "claude")
        self.assertEqual(roles["inspector"], "kimi")
        self.assertEqual(roles["pipeline_order"], ["claude", "kimi", "codex"])

    def test_explicit_reviewer_overrides_order(self):
        roles = runner.resolve_roles("claude", reviewer="kimi")
        self.assertEqual(roles["reviewer"], "kimi")

    def test_unimplemented_provider_is_refused_with_guidance(self):
        with self.assertRaisesRegex(runner.RunError, "glm"):
            runner.resolve_roles("glm")

    def test_qwen_roles(self):
        roles = runner.resolve_roles("qwen")
        self.assertEqual(roles["reviewer"], "claude")
        self.assertEqual(roles["pipeline_order"][-2], "qwen")

    def test_deepseek_roles(self):
        roles = runner.resolve_roles("deepseek")
        self.assertEqual(roles["reviewer"], "claude")
        self.assertEqual(roles["pipeline_order"][-3], "deepseek")

    def test_opencode_roles(self):
        roles = runner.resolve_roles("opencode")
        self.assertEqual(roles["reviewer"], "claude")
        self.assertEqual(roles["pipeline_order"][-1], "opencode")

    def test_pipeline_order_needs_another_provider(self):
        with self.assertRaises(runner.RunError):
            runner.resolve_roles("claude", order=["claude"])

    def test_command_fails_fast_on_unknown_provider(self):
        with self.assertRaisesRegex(runner.RunError, "Unknown provider"):
            runner.command("glm", "review", Path(tempfile.mkdtemp()))

    def test_roles_cli_accepts_pipeline_override(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = runner.main(["roles", "--host", "claude", "--providers", "claude,kimi"])
        self.assertEqual(code, 0, err.getvalue())
        self.assertEqual(json.loads(out.getvalue())["reviewer"], "kimi")

    def test_roles_cli_refuses_unknown_provider_before_launch(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = runner.main(["roles", "--host", "notaprovider"])
        self.assertEqual(code, 1)
        self.assertIn("Unknown provider", err.getvalue())
        self.assertIn("Implemented", err.getvalue())


if __name__ == "__main__":
    unittest.main()
