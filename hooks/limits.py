#!/usr/bin/env python3
"""PreToolUse hook: the limits of the divan agents, keyed on the hook input's agent_type.

Bash rules read the command text, so a command that writes through its own syntax or a script gets past them.
The manager is on a denylist so it can run a repo's checks; the reviewer and the critic are on an allowlist.
`python3 limits.py --test` runs the self-check.
"""
import json, os, re, shlex, subprocess, sys, tempfile

READ = {"git", "gh", "ls", "cat", "head", "tail", "wc", "rg", "grep", "jq", "pwd", "echo", "printf", "date", "diff",
        "stat", "file", "tree", "sort", "uniq", "cut", "which", "true", "cd", "find", "test", "["}
EXTRA = {"reviewer": {"codex"}, "critic": {"superset", "paradev"}}
WRITE = {"rm", "rmdir", "mv", "cp", "touch", "tee", "mkdir", "ln", "chmod", "chown", "dd", "truncate", "install", "rsync"}
WRAP = {"env", "command", "nice", "time", "nohup", "xargs", "sudo", "exec"}
WRAP_VALUE = {"-n", "-I", "-P", "-L", "-d", "-E", "-s", "-u", "-g", "-C"}  # wrapper options that take a value
GIT_READ = {"status", "log", "diff", "show", "rev-parse", "ls-files", "grep", "blame", "describe", "shortlog",
            "cat-file", "ls-tree", "merge-base", "rev-list", "worktree", "branch", "remote", "stash"}
GH_READ = {"view", "list", "diff", "checks", "status", "watch"}
BROWSER_READ = {"list", "open", "navigate", "screenshot", "console"}
SEP = {"&&", "||", ";", "|", "&", "(", ")", ";;", "|&"}
REDIR = set("<>&")


def segments(cmd):
    """Simple commands in cmd as word lists; $(...) and `...` bodies count as commands too."""
    out = []
    for c in [cmd] + [a or b for a, b in re.findall(r"\$\(([^()]*)\)|`([^`]*)`", cmd)]:
        lex = shlex.shlex(c.replace("\n", " ; "), posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        try:
            toks = list(lex)
        except ValueError:
            toks = c.split()
        seg = []
        for t in toks + [";"]:
            if t in SEP:
                out.append(seg)
                seg = []
            else:
                seg.append(t)
    return [s for s in out if s]


def commands(cmd):
    """Simple commands in cmd with wrappers peeled: `env X=1 git push` is `git push`; `bash -c '<cmd>'` is <cmd>."""
    for w in segments(cmd):
        while w:
            tool = w[0].rsplit("/", 1)[-1]
            if re.match(r"^\w+=", w[0]):
                w = w[1:]
            elif tool in ("sh", "bash", "zsh") and "-c" in w[1:-1]:
                yield from commands(w[w.index("-c") + 1])
                w = []
            elif tool in WRAP:
                w = w[1:]
                while w and (w[0].startswith("-") or re.match(r"^\w+=", w[0])):
                    w = w[2:] if w[0] in WRAP_VALUE else w[1:]
            else:
                yield w
                w = []


def redirects_to_file(w):
    return any(set(t) <= REDIR and ">" in t and not (
        w[i + 1:i + 2] == ["/dev/null"] or t.endswith("&") and (w[i + 1:i + 2] or [""])[0].isdigit())
        for i, t in enumerate(w))


def strip_redirects(w):
    return [t for i, t in enumerate(w) if not (set(t) <= REDIR or i and set(w[i - 1]) <= REDIR
                                               or t.isdigit() and set((w[i + 1:i + 2] or ["x"])[0]) <= REDIR)]


def git_args(w):
    """Words after `git`, skipping -C <path> and -c <k=v>; also returns the -C path."""
    i, path = 1, None
    while i < len(w) and w[i].startswith("-"):
        if w[i] in ("-C", "-c"):
            path = w[i + 1] if w[i] == "-C" and i + 1 < len(w) else path
            i += 1
        i += 1
    return w[i:], path


def option_values(w, short, long):
    """Values of an option given as `short v`, `long v` or `long=v`."""
    return ([w[i + 1] for i, a in enumerate(w[:-1]) if a in (short, long)]
            + [a.split("=", 1)[1] for a in w if a.startswith(long + "=")])


def codex_read_only(w):
    sub = (w[1:2] or [""])[0]
    if any(a.startswith("--dangerously") or a in ("--full-auto", "-p", "--profile") for a in w):
        return False
    if any(v.startswith("sandbox") and v != "sandbox_mode=read-only" for v in option_values(w, "-c", "--config")):
        return False
    if sub in ("exec", "e"):
        modes = option_values(w, "-s", "--sandbox")
        return bool(modes) and set(modes) == {"read-only"}
    return sub == "review" and "sandbox_mode=read-only" in option_values(w, "-c", "--config")


def reader(agent, w):
    """Why w writes, for the manager (denylist) and the reviewer and critic (allowlist)."""
    tool, line = w[0].rsplit("/", 1)[-1], " ".join(w)
    if agent == "manager":
        if tool in WRITE:
            return f"`{tool}` writes files"
        if tool == "sed" and any(a.startswith("-i") or a == "--in-place" for a in w):
            return "sed -i edits files"
    elif tool not in READ | EXTRA[agent]:
        return f"`{tool}` is not on the {agent}'s read-only list"
    if any(a.startswith("--output") for a in w) or tool in ("sort", "tree") and "-o" in w:
        return "an output file"
    if tool == "find" and {"-delete", "-exec", "-execdir", "-ok", "-fprint", "-fprint0", "-fprintf", "-fls"} & set(w):
        return "find with -delete, -exec or -fprint"
    if tool == "git":
        a, _ = git_args(w)
        sub, rest = (a or [""])[0], a[1:]
        if "-c" in w[1:len(w) - len(a)]:
            return "`git -c` can make git run any program"
        if (sub not in GIT_READ or sub == "worktree" and rest[:1] != ["list"]
                or sub == "stash" and rest[:1] not in (["list"], ["show"])
                or sub in ("branch", "remote") and any(not r.startswith("-") or r in ("-d", "-D", "-m", "-M", "-f")
                                                       for r in rest)):
            return f"`git {sub}` writes; git is read-only here"
    if tool == "gh":
        noun, verb = (w[1:2] or [""])[0], (w[2:3] or [""])[0]
        api_writes = re.search(r"(-X|--method)(?![ =]*GET\b)|\s(-f|-F|--field|--raw-field|--input)\b", line)
        if not (verb in GH_READ or noun == "search" or (noun, verb) == ("auth", "status") or noun == "api" and not api_writes):
            return f"`gh {noun} {verb}` writes; gh is read-only here"
    if tool == "codex" and not codex_read_only(w):
        return "codex runs only in its read-only sandbox: `exec -s read-only` or `review -c sandbox_mode=\"read-only\"`"
    if tool in ("superset", "paradev") and agent == "critic" and (w[1:2] != ["browser"] or (w[2:3] or [""])[0] not in BROWSER_READ):
        return "the critic uses only `superset browser list|open|navigate|screenshot|console`"
    if tool == "curl" and any(re.match(r"^-[XdFTOo]|^--(data|form|upload-file|output|request|json)", a) for a in w[1:]):
        return "curl only reads: no method, body, upload or output file"
    return None


def worker(w, cwd):
    """Why the worker may not run w: pushes to main/deploy and git commands that sweep files."""
    if w[0].rsplit("/", 1)[-1] != "git":
        return None
    a, path = git_args(w)
    sub, rest = (a or [""])[0], a[1:]
    pos = [x for x in rest if not x.startswith("-")]
    if sub == "push":
        if {"--all", "--mirror"} & set(rest) or any(re.search(r"(^|[:/+])(main|deploy)$", x) for x in pos[1:]):
            return "workers never push to main or deploy; push your branch"
        if len(pos) < 2:  # no refspec: pushes the current branch
            head = subprocess.run(["git", "-C", path or cwd, "rev-parse", "--abbrev-ref", "HEAD"],
                                  capture_output=True, text=True).stdout.strip()
            if head in ("main", "deploy"):
                return "workers never push to main or deploy; push your branch"
    sweeps = (sub == "add" and ({"-A", "--all"} & set(rest) or "." in pos)
              or sub == "commit" and any(r == "--all" or re.match(r"^-[a-zA-Z]*a", r) for r in rest)
              or sub == "stash" and rest[:1] not in (["list"], ["show"])
              or sub in ("checkout", "restore") and "." in pos
              or sub == "restore" and not pos
              or sub == "reset" and "--hard" in rest
              or sub == "clean" and any(r == "--force" or re.match(r"^-[a-zA-Z]*f", r) for r in rest))
    if sweeps:
        return f"`git {' '.join(a)}` touches files beyond your own; stage, restore and clean by explicit path"
    return None


def brief_path(p):
    """True for a file directly in <evidence folder>/briefs/, the evidence folder being the one holding charter.md."""
    d = os.path.dirname(os.path.realpath(p))
    return os.path.basename(d) == "briefs" and os.path.isfile(os.path.join(os.path.dirname(d), "charter.md"))


def check(event):
    agent = (event.get("agent_type") or "").removeprefix("divan:")
    if agent not in ("manager", "worker", "reviewer", "critic"):
        return None
    tool, inp = event.get("tool_name"), event.get("tool_input") or {}
    if tool == "Write" and agent == "manager" and not brief_path(inp.get("file_path", "")):
        return "the manager writes only briefs: files in <evidence folder>/briefs/, next to charter.md"
    if tool != "Bash":
        return None
    cmd = inp.get("command", "")
    if re.search(r"\bgh\b.*\bpr\s+merge\b|pulls/\d+/merge", cmd):
        return "merging is divan's; no agent merges"
    for w in commands(cmd):
        if agent == "worker":
            why = worker(strip_redirects(w), event.get("cwd", "."))
        else:
            why = "output redirect to a file" if redirects_to_file(w) else reader(agent, strip_redirects(w))
        if why:
            return f"{agent}: {why}"
    return None


def test():
    def B(agent, cmd):
        return check({"agent_type": "divan:" + agent, "tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": "/"})

    def W(path):
        return check({"agent_type": "divan:manager", "tool_name": "Write", "tool_input": {"file_path": path}})

    ev = tempfile.mkdtemp()
    os.makedirs(f"{ev}/briefs")
    open(f"{ev}/charter.md", "w").close()
    os.symlink(f"{ev}/charter.md", f"{ev}/briefs/link.md")
    assert not W(f"{ev}/briefs/T1.md") and W(f"{ev}/briefs/link.md")  # the link's target is outside briefs/
    assert W(f"{ev}/briefs/../src/a.py") and W(f"{ev}/src/a.py") and W(f"{ev}/briefs/sub/T1.md") and W("/x/briefs/T1.md")
    for a in ("manager", "worker", "reviewer", "critic"):
        assert B(a, "gh pr merge 1 --squash"), a
    assert B("worker", "gh -R o/r pr merge 1") and not B("manager", "gh api -X GET repos/o/r/pulls")
    # worker: pushes, wrapped pushes, git commands that sweep files
    for c in ("git push origin HEAD:main", "git -C /x push -f origin deploy", "env git push origin HEAD:main",
              "bash -c 'git push origin HEAD:main'", "nice -n 5 git push origin main", "git add -A", "git add .",
              "git commit -am x", "git commit --all -m x", "git stash", "git stash pop", "git checkout -- .",
              "git restore", "git restore .", "git reset --hard", "git clean -fd"):
        assert B("worker", c), c
    for c in ("git push -u origin feat-main-fix", "rm -rf build", "git add a.py b.py", "git commit -m 'add a thing'",
              "git stash list", "git restore --staged a.py", "git reset HEAD~1", "git commit --amend --no-edit"):
        assert not B("worker", c), c
    # manager: denylist
    for c in ("git commit -m x", "gh pr create", "echo x > f", 'echo "$(rm -rf /)"', "git branch -D x", "ls\nrm f",
              "git diff --output=x", "sort -o x y", "git -c core.pager='rm x' log", "git fetch", "rm -rf x", "touch f",
              "sed -i s/a/b/ f", "find . -delete", "ls | xargs rm", "ls | xargs -n 1 rm", "bash -c 'rm x'",
              "env FOO=1 touch f", "npm test > out.txt", "python3 -m pytest | tee log", "curl -XPOST u", "curl -dx u"):
        assert B("manager", c), c
    for c in ("npm test", "python3 -m pytest -q", "claude plugin validate .", "python3 hooks/limits.py --test 2>&1",
              "git -C /r log --oneline 2>&1 | head -5 && gh pr view 3 --json state >/dev/null", "git stash list",
              "grep 'a|b' f; echo 'x > y'; git branch -a", "superset agents wait --until settled 2>/dev/null"):
        assert not B("manager", c), c
    # reviewer and critic: allowlist
    assert B("reviewer", "python3 -m pytest") and B("critic", "npm test") and B("reviewer", "sed -n 'w x' y")
    assert B("reviewer", "env touch x") and B("reviewer", "bash -c 'touch x'") and B("reviewer", "superset ws delete 1")
    assert not B("reviewer", "env ls") and not B("reviewer", "git stash show")
    for c in ("codex exec --full-auto x", "codex exec x", "codex exec read-only", "codex exec -s workspace-write x",
              "codex exec -s read-only -c sandbox_mode=danger-full-access x", "codex review --base main",
              "codex exec -s read-only --dangerously-bypass-approvals-and-sandbox x", "codex exec -p rw -s read-only x"):
        assert B("reviewer", c), c
    for c in ("codex exec -s read-only x", "codex exec --sandbox=read-only x", 'codex review --base main -c sandbox_mode="read-only"'):
        assert not B("reviewer", c), c
    for c in ("superset agents create", "superset browser eval 1", "superset browser cdp", "curl https://x"):
        assert B("critic", c), c
    assert not B("critic", "superset browser screenshot --out /tmp/s.png")
    assert not check({"tool_name": "Bash", "tool_input": {"command": "gh pr merge 1"}})  # plain sessions untouched
    print("ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--test"]:
        sys.exit(test())
    reason = check(json.load(sys.stdin))
    if reason:
        print(f"Blocked by divan limits: {reason}.", file=sys.stderr)
        sys.exit(2)
