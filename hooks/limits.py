#!/usr/bin/env python3
"""PreToolUse hook: the limits of the divan agents, keyed on the hook input's agent_type.

Bash rules read the command text: they stop the commands an agent writes, not a deliberate escape
(a script file, an alias, `gh api` with a crafted path). `python3 limits.py --test` runs the self-check.
"""
import json, re, shlex, subprocess, sys

READ = {"git", "gh", "ls", "cat", "head", "tail", "wc", "rg", "grep", "jq", "pwd", "echo", "printf", "date", "diff",
        "stat", "file", "tree", "sort", "uniq", "cut", "which", "true", "cd", "find", "test", "["}
EXTRA = {"manager": {"superset", "paradev"}, "reviewer": {"codex"}, "critic": {"superset", "paradev", "curl"}}
GIT_READ = {"status", "log", "diff", "show", "rev-parse", "ls-files", "grep", "blame", "fetch", "describe",
            "shortlog", "cat-file", "ls-tree", "merge-base", "rev-list", "worktree", "branch", "remote"}
GH_READ = {"view", "list", "diff", "checks", "status", "watch"}
SEP = {"&&", "||", ";", "|", "&", "(", ")", ";;", "|&"}


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


def redirects_to_file(w):
    return any(set(t) <= set("<>&") and ">" in t and not (
        w[i + 1:i + 2] == ["/dev/null"] or t.endswith("&") and (w[i + 1:i + 2] or [""])[0].isdigit())
        for i, t in enumerate(w))


def git_args(w):
    """Words after `git`, skipping -C <path> and -c <k=v>; also returns the -C path."""
    i, path = 1, None
    while i < len(w) and w[i].startswith("-"):
        if w[i] in ("-C", "-c"):
            path = w[i + 1] if w[i] == "-C" and i + 1 < len(w) else path
            i += 1
        i += 1
    return w[i:], path


def read_only(agent, w):
    tool, line = w[0].rsplit("/", 1)[-1], " ".join(w)
    if tool not in READ | EXTRA.get(agent, set()):
        return f"`{tool}` is not on the {agent}'s read-only list"
    if redirects_to_file(w):
        return "output redirect to a file"
    w = [t for i, t in enumerate(w) if not (set(t) <= set("<>&") or i and set(w[i - 1]) <= set("<>&")
                                            or t.isdigit() and set((w[i + 1:i + 2] or ["x"])[0]) <= set("<>&"))]
    if any(a.startswith("--output") for a in w) or tool in ("sort", "tree") and "-o" in w:
        return "an output file"
    if tool == "find" and {"-delete", "-exec", "-execdir", "-ok", "-fprint", "-fprint0", "-fprintf", "-fls"} & set(w):
        return "find with -delete, -exec or -fprint"
    if tool == "git":
        a, _ = git_args(w)
        sub, rest = (a or [""])[0], a[1:]
        if (sub not in GIT_READ or "-c" in w[1:len(w) - len(a)] or sub == "worktree" and rest[:1] != ["list"]
                or sub in ("branch", "remote") and any(not r.startswith("-") or r in ("-d", "-D", "-m", "-M", "-f")
                                                       for r in rest)):
            return f"`git {sub}` writes; git is read-only here"
    if tool == "gh":
        noun, verb = (w[1:2] or [""])[0], (w[2:3] or [""])[0]
        api_writes = re.search(r"(-X|--method)(?![ =]*GET\b)|\s(-f|-F|--field|--raw-field|--input)\b", line)
        if not (verb in GH_READ or noun == "search" or (noun, verb) == ("auth", "status") or noun == "api" and not api_writes):
            return f"`gh {noun} {verb}` writes; gh is read-only here"
    if tool == "codex" and ("read-only" not in line or re.search(r"dangerously|full-auto|workspace-write|danger-full", line)):
        return "codex runs only in its read-only sandbox: `-s read-only`, or `-c sandbox_mode=\"read-only\"` for review"
    if tool in ("superset", "paradev") and agent == "critic" and w[1:2] != ["browser"]:
        return "the critic uses superset only for `superset browser`"
    if tool == "curl" and re.search(r"\s(-X|-d|--data\S*|-F|--form|-T|--upload-file|-o|-O|--output)\b", line):
        return "curl only reads: no method, body, upload or output file"
    return None


def pushes_protected(w, cwd):
    if w[0].rsplit("/", 1)[-1] != "git":
        return False
    a, path = git_args(w)
    if a[:1] != ["push"]:
        return False
    pos = [x for x in a[1:] if not x.startswith("-")]
    if {"--all", "--mirror"} & set(a) or any(re.search(r"(^|[:/+])(main|deploy)$", x) for x in pos[1:]):
        return True
    if len(pos) < 2:  # no refspec: pushes the current branch
        head = subprocess.run(["git", "-C", path or cwd, "rev-parse", "--abbrev-ref", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
        return head in ("main", "deploy")
    return False


def check(event):
    agent = (event.get("agent_type") or "").removeprefix("divan:")
    if agent not in ("manager", "worker", "reviewer", "critic"):
        return None
    tool, inp = event.get("tool_name"), event.get("tool_input") or {}
    if tool == "Write" and agent == "manager" and "/briefs/" not in inp.get("file_path", ""):
        return "the manager writes only briefs, in <evidence folder>/briefs/"
    if tool != "Bash":
        return None
    cmd = inp.get("command", "")
    if re.search(r"\bgh\b.*\bpr\s+merge\b|pulls/\d+/merge", cmd):
        return "merging is divan's; no agent merges"
    for w in segments(cmd):
        if agent == "worker":
            if pushes_protected(w, event.get("cwd", ".")):
                return "workers never push to main or deploy; push your branch"
        else:
            why = read_only(agent, w)
            if why:
                return f"{agent} is read-only: {why}"
    return None


def test():
    def B(agent, cmd):
        return check({"agent_type": "divan:" + agent, "tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": "/"})

    def W(path):
        return check({"agent_type": "divan:manager", "tool_name": "Write", "tool_input": {"file_path": path}})

    for a in ("manager", "worker", "reviewer", "critic"):
        assert B(a, "gh pr merge 1 --squash"), a
    assert B("worker", "gh -R o/r pr merge 1") and not B("manager", "gh api -X GET repos/o/r/pulls")
    assert B("worker", "git push origin HEAD:main") and B("worker", "git -C /x push -f origin deploy")
    assert not B("worker", "git push -u origin feat-main-fix") and not B("worker", "rm -rf build")
    assert not B("manager", "git -C /r log --oneline 2>&1 | head -5 && gh pr view 3 --json state >/dev/null")
    assert not B("manager", "grep 'a|b' f; echo 'x > y'; git branch -a")
    assert B("manager", "git commit -m x") and B("manager", "gh pr create") and B("manager", "echo x > f")
    assert B("manager", 'echo "$(rm -rf /)"') and B("manager", "git branch -D x") and B("manager", "ls\nrm f")
    assert B("manager", "git diff --output=x") and B("manager", "sort -o x y") and B("manager", "sed -n 'w x' y")
    assert B("manager", "git -c core.pager='rm x' log")
    assert not B("manager", "superset agents wait --until settled 2>/dev/null")
    assert not B("reviewer", 'codex review --base main -c sandbox_mode="read-only"')
    assert B("reviewer", "codex exec --full-auto x") and B("reviewer", "codex exec x") and B("reviewer", "superset ws delete 1")
    assert not B("critic", "superset browser screenshot --out /tmp/s.png") and B("critic", "superset agents create")
    assert W("/e/src/a.py") and not W("/e/briefs/T1.md")
    assert not check({"tool_name": "Bash", "tool_input": {"command": "gh pr merge 1"}})  # plain sessions untouched
    print("ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--test"]:
        sys.exit(test())
    reason = check(json.load(sys.stdin))
    if reason:
        print(f"Blocked by divan limits: {reason}.", file=sys.stderr)
        sys.exit(2)
