#!/usr/bin/env python3
"""PreToolUse hook: the divan agents' limits. It stops a cooperative agent's mistakes, not an adversary: a crafted
command gets past it. The hard boundaries are each agent's tools and GitHub branch protection. `--test` self-checks."""
import json, os, re, shlex, sys, tempfile

AGENTS = ("manager", "worker", "reviewer", "critic")
SESSIONS = os.path.join(os.environ.get("TMPDIR", "/tmp"), "divan-limits")  # session_id -> its main thread's agent
KEYWORDS = {"if", "then", "else", "elif", "while", "until", "do", "!", "{"}
GIT_READ = {"status", "log", "diff", "show", "blame", "grep", "ls-files", "ls-tree", "cat-file", "rev-parse",
            "describe", "shortlog", "merge-base", "rev-list"}
GH_READ = {"view", "list", "diff", "checks", "status", "watch"}
NON_GET = r"(-X|--method)[ =]?(?!GET\b)[A-Z]|\s(-f|-F|--field|--raw-field|--input)\b"  # gh api that writes


def commands(cmd):
    """Simple commands of cmd as word lists, split at ; && || | & ( ) and newlines, shell keywords dropped."""
    lex = shlex.shlex(cmd.replace("\n", ";"), posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    try:
        toks = list(lex)
    except ValueError:  # unbalanced quotes: read it word by word
        toks = cmd.split()
    out = [[]]
    for t in toks:
        if set(t) <= set(";&|()"):
            out.append([])
        elif out[-1] or t not in KEYWORDS:
            out[-1].append(t)
    return [w for w in out if w]


def why(agent, w):
    tool, line, ops = w[0].rsplit("/", 1)[-1], " ".join(w), [a for a in w if not a.startswith("-")]
    if tool == "gh" and (re.search(r"\bpr merge\b", " ".join(ops))
                         or re.search(r"pulls/\d+/merge", line) and re.search(NON_GET, line)):
        return "merging is divan's; no agent merges"
    args = w[1:]
    while tool == "git" and args and args[0].startswith("-"):  # skip git's -C/-c <value> and other global options
        args = args[2:] if args[0] in ("-C", "-c") else args[1:]
    sub, pos = (args[:1] or [""])[0] if tool == "git" else "", [a for a in args[1:] if not a.startswith("-")]
    if agent == "worker":
        if sub == "push" and ({"--all", "--mirror"} & set(args)
                              or any(re.search(r"(^|[:/+])(main|deploy)$", a) for a in pos[1:])):
            return "workers never push to main or deploy; push your branch"
        return "name the destination: `git push origin <branch>`" if sub == "push" and len(pos) < 2 else None
    if tool == "git" and sub not in GIT_READ:
        return f"`git {sub}` writes; git is read-only here"
    if tool == "gh" and not (ops[2:3] and ops[2] in GH_READ or ops[1:2] == ["search"] or ops[1:3] == ["auth", "status"]
                             or ops[1:2] == ["api"] and not re.search(NON_GET, line)):
        return "gh is read-only here"
    if tool in ("rm", "mv", "cp", "touch", "tee", "mkdir") or tool == "sed" and re.search(r" (-\w*i|--in-pl)", line):
        return f"`{tool}` writes files"
    for t, nxt in zip(w, w[1:] + [""]):
        if t in (">", ">>", ">|", "&>", "&>>", ">&") and nxt != "/dev/null" and not (t == ">&" and nxt.isdigit()):
            return "output redirect to a file"
    if agent == "reviewer" and tool == "codex" and (
            not re.search(r"(-s|--sandbox)[ =]read-only|sandbox_mode=read-only", line)
            or re.search(r"--yolo|--dangerously|--full-auto|(^| )-o( |$)|--output-last", line)):
        return "codex runs only with `-s read-only`, never `--yolo`, `--dangerously-*` or `-o`"
    if agent == "critic" and tool in ("superset", "paradev") and not (
            w[1:2] == ["browser"] and w[2:3] and w[2] in ("list", "open", "navigate", "screenshot", "console")):
        return "the critic uses only `superset browser list|open|navigate|screenshot|console`"
    return None


def session_agent(event):
    """The event's `divan:` agent, else the one its session's main thread recorded (a worker's subagent is a worker)."""
    scope, _, own = (event.get("agent_type") or "").rpartition(":")
    sid = re.sub(r"[^\w-]", "", event.get("session_id") or "")
    if scope == "divan" and own in AGENTS:
        if sid and not event.get("agent_id"):  # only main threads record
            os.makedirs(SESSIONS, exist_ok=True)
            with open(os.path.join(SESSIONS, sid), "w") as f:
                f.write(own)
        return own
    try:
        with open(os.path.join(SESSIONS, sid) if sid else "") as f:
            return f.read().strip()
    except OSError:
        return None


def check(event):
    agent, tool, inp = session_agent(event), event.get("tool_name"), event.get("tool_input") or {}
    folder = os.path.dirname(os.path.realpath(inp.get("file_path", "")))  # a brief's folder: briefs/ next to charter.md
    if agent == "manager" and tool == "Write" and not (
            os.path.basename(folder) == "briefs" and os.path.isfile(os.path.join(folder, "..", "charter.md"))):
        return "manager: write only briefs, in <evidence folder>/briefs/ next to charter.md"
    bash = tool == "Bash" and agent in AGENTS
    reasons = [why(agent, w) for w in commands(inp.get("command", ""))] if bash else []
    return next((f"{agent}: {r}" for r in reasons if r), None)


def test():
    global SESSIONS
    tmp = tempfile.TemporaryDirectory()
    SESSIONS, ev = f"{tmp.name}/sessions", tmp.name
    os.makedirs(f"{ev}/briefs")
    open(f"{ev}/charter.md", "w").close()
    W = lambda p: check({"agent_type": "divan:manager", "tool_name": "Write", "tool_input": {"file_path": p}})
    B = lambda a, c, sid="", aid=None: check({"agent_type": a, "session_id": sid, "agent_id": aid,
                                              "tool_name": "Bash", "tool_input": {"command": c}})
    assert W(f"{ev}/src/a.py") and W(f"{ev}/briefs/../a.py") and not W(f"{ev}/briefs/T1.md")
    blocked = {"manager": ["git commit -m x", "git push origin f", "gh pr create", "rm -rf x", "sed -i s/a/b/ f",
                           "echo x > f", "if true; then rm x; fi"],
               "worker": ["gh pr merge 1", "gh api -X PUT repos/o/r/pulls/1/merge", "git push origin main",
                          "git push origin HEAD:deploy", "git push --all origin", "git push"],
               "reviewer": ["touch x", "git commit -m x", "codex exec x", "codex exec --yolo -s read-only x",
                            "codex exec -s read-only -o f x"],
               "critic": ["superset browser eval 1", "touch x", "gh pr merge 1"]}
    allowed = {"manager": ["npm test", "python3 -m pytest -q", "claude plugin validate .", "superset agents wait",
                           "git log -3 && git diff --stat", "git status 2>&1 | head", "gh pr view 3 --json state"],
               "worker": ["git push -u origin feat-x", "rm -rf build",
                          "git commit -m \"$(cat <<'EOF'\nfix: it's done\nEOF\n)\""],
               "reviewer": ["codex exec -s read-only - <<'EOF'\nReview a.md\nEOF", "gh pr list"],
               "critic": ["superset browser screenshot --out /tmp/s.png", "git diff main"]}
    assert all(B("divan:" + a, c) for a, cs in blocked.items() for c in cs)
    assert not any(B("divan:" + a, c) for a, cs in allowed.items() for c in cs)
    assert not B("divan:worker", "git status", "s1") and B("general-purpose", "git push origin main", "s1", "a1")
    assert not B("worker", "gh pr merge 1") and not B("general-purpose", "git push origin main", "s2", "a2")
    tmp.cleanup()
    print("ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--test"]:
        sys.exit(test())
    reason = check(json.load(sys.stdin))
    if reason:
        print(f"Blocked by divan limits: {reason}.", file=sys.stderr)
        sys.exit(2)
