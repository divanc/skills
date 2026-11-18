#!/usr/bin/env python3
"""PreToolUse hook: the divan agents' limits. It stops a cooperative agent's mistakes, not an adversary: a crafted
command gets past it. The hard boundaries are each agent's tools and GitHub branch protection. `--test` self-checks."""
import json, os, re, shlex, sys, tempfile

AGENTS = ("manager", "worker", "reviewer", "critic")
SESSIONS = os.path.join(os.environ.get("TMPDIR", "/tmp"), "divan-limits")  # session_id -> its main thread's agent
KEYWORDS = {"if", "then", "else", "elif", "while", "until", "do", "!", "{"}
GIT_READ = {"status", "log", "diff", "show", "blame", "grep", "ls-files", "ls-tree", "cat-file", "rev-parse",
            "describe", "shortlog", "merge-base", "rev-list", "ls-remote", "for-each-ref", "cherry", "name-rev",
            "check-ignore"}
GH_READ = {"view", "list", "diff", "checks", "status", "watch"}
LIST_FILTERS = {"-l", "--list", "--contains", "--no-contains", "--merged", "--no-merged", "--points-at"}
TAKES_VALUE = {"--contains", "--no-contains", "--merged", "--no-merged", "--points-at", "--sort", "--format"}
BRANCH_READ = LIST_FILTERS | TAKES_VALUE | {"-a", "-r", "-v", "-vv", "--show-current"}


def api_writes(line):
    """True if a `gh api` call writes: a GraphQL mutation or unseen --input; else an explicit non-GET method, else a
    field (which implies POST)."""
    if re.search(r"\bgraphql\b", line):
        return bool(re.search(r"\bmutation\b|--input", line))
    method = re.findall(r"(?:-X|--method)[ =]?([A-Za-z]+)", line)
    return method[-1].upper() != "GET" if method else bool(re.search(r"\s(-f|-F|--field|--raw-field|--input)\b", line))


def commands(cmd):
    """Simple commands of cmd as word lists, split at ; && || | & ( ) and newlines, after dropping heredoc bodies
    (data) and `#` comments (an unquoted `#` that starts a word, to the end of its line); shell keywords dropped."""
    out, delim = [], None
    cmd = re.sub(r"'[^']*'|\\\n", lambda m: m[0] if m[0][0] == "'" else "", cmd)  # join continuations
    for line in cmd.split("\n"):
        if delim:
            delim = None if line.strip() == delim else delim
            continue
        q, chars = None, []
        for i, ch in enumerate(line):
            q = (ch if ch in "'\"" else None) if q is None else (None if ch == q else q)
            if q is None and ch == "#" and (i == 0 or line[i - 1].isspace()):
                line = line[:i]
                break
            chars.append(chr(0xE000 + ord(ch)) if q and ch in "<>|&;()" else ch)  # a quoted operator is a word
        out.append("".join(chars))
        delim = (re.findall(r"(?<!<)<<(?!<)-?\s*['\"]?(\w+)", line) or [None])[-1]
    lex = shlex.shlex(";".join(out), posix=True, punctuation_chars=True)
    lex.whitespace_split, lex.commenters = True, ""  # comments are gone; shlex's own would eat joined lines
    try:
        toks = list(lex)
    except ValueError:  # unbalanced quotes: read it word by word
        toks = " ; ".join(out).split()
    out = [[]]
    for t in toks:
        if set(t) <= set(";&|()"):
            out.append([])
        elif out[-1] or t not in KEYWORDS:
            out[-1].append(t)
    return [w for w in out if w]


def why(agent, w):
    tool, line = w[0].rsplit("/", 1)[-1], " ".join(w)
    ops = [a for i, a in enumerate(w)  # the words, without options and the values of gh's -R/--repo/--hostname
           if not a.startswith("-") and (w[i - 1] if i else "") not in ("-R", "--repo", "--hostname")]
    if tool == "gh" and (re.search(r"\bpr merge\b", " ".join(ops))
                         or re.search(r"pulls/\d+/merge", line) and api_writes(line)
                         or "graphql" in ops and re.search(r"mergePullRequest|enablePullRequestAutoMerge", line)):
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
    words = [a for i, a in enumerate(args[1:]) if not a.startswith("-") and args[i] not in TAKES_VALUE]  # operands
    reads = (sub == "branch" and {a.split("=")[0] for a in args[1:] if a.startswith("-")} <= BRANCH_READ
             and (not words or LIST_FILTERS & {a.split("=")[0] for a in args})
             or sub in ("stash", "worktree") and args[1:2] == ["list"] or sub == "stash" and args[1:2] == ["show"]
             or sub == "tag" and (not args[1:] or {"-l", "--list"} & set(args))
             or sub == "reflog" and args[1:2] in ([], ["show"])
             or sub == "remote" and (args[1:] in ([], ["-v"]) or args[1:2] == ["get-url"])
             or sub == "config" and (args[1:2] in (["get"], ["list"])
                                     or {"--get", "--get-all", "--list", "-l", "--get-regexp"} & set(args)))
    if tool == "git" and (sub not in GIT_READ and not reads
                          or any(len(o := a.split("=")[0]) > 2 and "--output".startswith(o) for a in args)):
        return f"`git {sub}` writes; git is read-only here"
    if tool == "gh" and not (ops[2:3] and ops[2] in GH_READ or ops[1:2] == ["search"] or ops[1:] == ["status"]
                             or ops[1:3] == ["auth", "status"]
                             or ops[1:2] == ["api"] and not api_writes(line)):
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
    if agent == "critic" and tool in ("superset", "paradev") and not (  # ops skips superset's options, like --json
            ops[1:2] == ["browser"] and ops[2:3] and ops[2] in ("list", "open", "navigate", "screenshot", "console")):
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
    path = os.path.join(SESSIONS, sid)
    return open(path).read().strip() if sid and os.path.isfile(path) else None


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
    blocked = {
        "manager": ["git commit -m x", "git push origin f", "gh pr create", "rm -rf x", "sed -i s/a/b/ f", "echo x > f",
                    "if true; then rm x; fi", "curl https://x.com/#docs\nrm artifact", "# clean up\nrm -rf x",
                    "ls # c\ngit commit -m x", "echo 'a #b' && rm x"],
        "worker": ["gh pr merge 1", "gh pr --repo o/r merge 1", "gh -R o/r pr merge 1", "git push origin \\\nmain",
                   "gh api -X PUT repos/o/r/pulls/1/merge", "git push origin main", "git push",
                   "# Publish\ngit push origin main", "gh api graphql -f query='mutation{mergePullRequest(x)}'",
                   "git push origin HEAD:deploy", "git push --all origin"],
        "reviewer": ["touch x", "git commit -m x", "cat <<EOF\nx\nEOF\ntouch y", "codex exec x",
                     "codex exec --yolo -s read-only x", "codex exec -s read-only -o f x"],
        "critic": ["superset browser eval 1", "touch x", "gh pr merge 1", "git branch new", "git branch -d x",
                   "gh api --method GET x -X POST", "git branch --sort x new", "git branch -v new-branch",
                   "git remote add x u", "git stash", "git worktree add ../x", "git tag v1",
                   "gh api graphql -f query='mutation { addComment(x) }'", "gh api graphql --input q.json",
                   "git log --output=f", "git diff --outp f", "git config user.name x",
                   "git config --unset user.name", "git config set user.name x"]}
    allowed = {
        "manager": ["npm test", "python3 -m pytest -q", "claude plugin validate .", "superset agents wait",
                    "git log -3 && git diff --stat", "git status 2>&1 | head", "gh pr view 3 --json state"],
        "worker": ["git push -u origin feat-x", "rm -rf build", "git push origin \\\nfeature",
                   "git commit -m \"$(cat <<'EOF'\nfix: it's done\nEOF\n)\""],
        "reviewer": ["codex exec -s read-only - <<'EOF'\nReview a.md.\ngit commit is forbidden.\nEOF", "gh pr list",
                     "git branch --show-current", "git branch -a -v", "git remote -v", "git remote get-url origin"],
        "critic": ["superset browser screenshot --out /tmp/s.png", "superset --json browser list",
                   "git log --grep '#12'", "echo 'a # b' && ls", "rg '>' README.md", "grep \"a|b\" f",
                   "git branch --contains HEAD", "git branch --list 'feat/*'", "git branch --merged=main -v",
                   "gh api --method GET search/issues -f q=x", "gh pr --repo o/r view 1", "git log --oneline -3",
                   "git config --get user.name", "git config --show-origin --list", "git config get remote.origin.url",
                   "git config -l", "git log --output-indicator-new=+ -1", "git branch --sort committerdate",
                   "git branch --format '%(refname:short)'", "git branch --contains HEAD -a", "git branch --merged",
                   "gh status", "gh auth status", "git stash list", "git worktree list", "git tag", "git tag -l 'v*'",
                   "git ls-remote origin", "git reflog", "git branch -v --list 'feat*'",
                   "gh api graphql -f query='query { viewer { login } }'", "sed -n 's/a/b/p' f", "sort f 2>/dev/null"]}
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
