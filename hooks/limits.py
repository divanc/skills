#!/usr/bin/env python3
"""PreToolUse hook: the limits of the divan agents, keyed on the hook input's agent_type.

Bash rules read the command text, so a command that writes through its own syntax or a script gets past them.
The manager is on a denylist so it can run a repo's checks; the reviewer and the critic are on an allowlist.
`python3 limits.py --test` runs the self-check.
"""
import json, os, re, shlex, sys, tempfile

READ = {"git", "gh", "ls", "cat", "head", "tail", "wc", "rg", "grep", "jq", "pwd", "echo", "printf", "date", "diff",
        "stat", "file", "tree", "sort", "uniq", "cut", "which", "true", "cd", "find", "test", "["}
EXTRA = {"reviewer": {"codex"}, "critic": {"superset", "paradev"}}
WRITE = {"rm", "rmdir", "mv", "cp", "touch", "tee", "mkdir", "ln", "chmod", "chown", "dd", "truncate", "install", "rsync"}
WRAP = {  # wrapper: its options that take a value
    "env": {"-u", "--unset", "-C", "--chdir"}, "nice": {"-n", "--adjustment"}, "nohup": set(), "command": set(),
    "sudo": {"-u", "-g", "-C", "-p", "-U", "-r", "-t", "-D", "-h"}, "time": {"-o", "-f"}, "exec": {"-a"},
    "xargs": {"-I", "-n", "-P", "-L", "-d", "-E", "-s", "-a"}}
GIT_READ = {"status", "log", "diff", "show", "rev-parse", "ls-files", "grep", "blame", "describe", "shortlog",
            "cat-file", "ls-tree", "merge-base", "rev-list", "worktree", "branch", "remote", "stash"}
GH_READ = {"view", "list", "diff", "checks", "status", "watch"}
GH_VALUE = {"-R", "--repo", "--hostname", "-X", "--method", "-H", "--header", "-f", "-F", "--field", "--raw-field",
            "--input", "-q", "--jq", "-t", "--template", "--json", "-b", "--body", "--title", "-L", "--limit"}
BRANCH_READ = {"-a", "-r", "-v", "-vv", "--list", "--show-current", "--contains", "--merged", "--no-merged"}
BRANCH_PATTERN = {"--list", "--contains", "--merged", "--no-merged"}  # options that take a pattern or commit
BROWSER_READ = {"list", "open", "navigate", "screenshot", "console"}
SEP = {"&&", "||", ";", "|", "&", "(", ")", ";;", "|&"}
REDIR = set("<>&|")  # `>|` writes too


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
    """Simple commands in cmd with wrappers peeled: `env X=1 git push` is `git push`; `bash -c '<cmd>'` is <cmd>.
    A wrapper and its own options come out as a command too, so `time -o FILE` is checked."""
    for w in segments(cmd):
        while w:
            tool = w[0].rsplit("/", 1)[-1]
            if re.match(r"^\w+=", w[0]):
                w = w[1:]
            elif tool in ("sh", "bash", "zsh") and any(re.match(r"^-[a-zA-Z]*c[a-zA-Z]*$", a) for a in w[1:-1]):
                yield from commands(w[next(i for i, a in enumerate(w) if re.match(r"^-[a-zA-Z]*c[a-zA-Z]*$", a)) + 1])
                w = []
            elif tool in WRAP:
                own, w = w[:1], w[1:]
                while w and (w[0].startswith("-") or re.match(r"^\w+=", w[0])):
                    if w[0] == "--":
                        w = w[1:]
                        break
                    if tool == "env" and w[0] in ("-S", "--split-string") and len(w) > 1:
                        w = shlex.split(w[1]) + w[2:]  # env -S '<cmd>' runs <cmd>
                        break
                    n = 2 if w[0] in WRAP[tool] else 1
                    own, w = own + w[:n], w[n:]
                yield own
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


def short_flags(args):
    """Single-letter flags in args, clusters split: `-Av` is A and v."""
    return {c for a in args if re.match(r"^-[a-zA-Z]+$", a) for c in a[1:]}


def option_values(w, short, long):
    """Values of an option given as `short v`, `long v` or `long=v`."""
    return ([w[i + 1] for i, a in enumerate(w[:-1]) if a in (short, long)]
            + [a.split("=", 1)[1] for a in w if a.startswith(long + "=")])


def gh_words(w):
    """Positional words of a gh command, options skipped: `gh pr --repo o/r merge 1` is [pr, merge, 1]."""
    out, i = [], 1
    while i < len(w):
        if w[i].startswith("-"):
            i += 2 if w[i] in GH_VALUE else 1
        else:
            out.append(w[i])
            i += 1
    return out


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
        if tool == "sed" and ("i" in short_flags(w) or any(a.startswith(("-i", "--in-place")) for a in w)):
            return "sed -i edits files"
    elif tool not in READ | EXTRA[agent] | WRAP.keys():
        return f"`{tool}` is not on the {agent}'s read-only list"
    if (any(a.startswith("--output") for a in w) or tool in ("sort", "tree", "time") and any(re.match(r"^-[a-zA-Z]*o", a) for a in w[1:])
            or tool == "uniq" and len([a for a in w[1:] if not a.startswith("-")]) > 1):
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
                or sub == "branch" and (any(f"-{c}" not in BRANCH_READ for c in short_flags(rest) - {"v"})
                                        or any(r.split("=")[0] not in BRANCH_READ for r in rest if r.startswith("--"))
                                        or any(not r.startswith("-") for r in rest) and not BRANCH_PATTERN & set(rest))
                or sub == "remote" and rest not in ([], ["-v"]) and rest[:1] not in (["show"], ["get-url"])):
            return f"`git {sub}` writes; git is read-only here"
    if tool == "gh":
        noun, verb = (gh_words(w) + ["", ""])[:2]
        if noun == "api":
            methods = option_values(w, "-X", "--method") + [a[2:] for a in w if re.match(r"^-X.", a)]
            if any(re.match(r"^(-[fF]|--(field|raw-field|input))", a) for a in w) or any(m.upper() != "GET" for m in methods):
                return "`gh api` with a body or a non-GET method writes"
        elif not (verb in GH_READ or noun == "search" or (noun, verb) == ("auth", "status")):
            return f"`gh {noun} {verb}` writes; gh is read-only here"
    if tool == "codex" and not codex_read_only(w):
        return "codex runs only in its read-only sandbox: `exec -s read-only` or `review -c sandbox_mode=\"read-only\"`"
    if tool in ("superset", "paradev") and agent == "critic" and (w[1:2] != ["browser"] or (w[2:3] or [""])[0] not in BROWSER_READ):
        return "the critic uses only `superset browser list|open|navigate|screenshot|console`"
    if tool == "curl" and (set("XdFTOo") & ({a[1] for a in w[1:] if re.match(r"^-[a-zA-Z]", a)} | short_flags(w[1:]))
                           or any(re.match(r"^--(data|form|upload-file|output|request|json)", a) for a in w[1:])):
        return "curl only reads: no method, body, upload or output file"
    return None


def worker(w):
    """Why the worker may not run w: pushes to main/deploy and git commands that sweep files."""
    if w[0].rsplit("/", 1)[-1] != "git":
        return None
    a, _ = git_args(w)
    sub, rest = (a or [""])[0], a[1:]
    pos = [x for x in rest if not x.startswith("-")]
    if sub == "push":
        if {"--all", "--mirror"} & set(rest) or any(
                x in (":", "+:") or "*" in x or re.search(r"(^|[:/+])(main|deploy)$", x) for x in pos[1:]):
            return "workers never push to main or deploy; push your branch"
        if len(pos) < 2 or any(re.match(r"^\+?(HEAD|@)$", x) for x in pos[1:]):  # the destination comes from config
            return "name the destination: `git push origin <branch>`"
    short = short_flags(rest)
    sweeps = (sub == "add" and ("A" in short or "--all" in rest or "." in pos)
              or sub == "commit" and ("a" in short or "--all" in rest)
              or sub == "stash" and rest[:1] not in (["list"], ["show"])
              or sub in ("checkout", "restore") and "." in pos
              or sub == "restore" and not pos
              or sub == "reset" and "--hard" in rest
              or sub == "clean" and ("f" in short or "--force" in rest))
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
    merges = re.search(r"pulls/\d+/merge", cmd) or any(  # parsed, and as tokens: gh, then pr, then merge
        w[0].rsplit("/", 1)[-1] == "gh" and gh_words(strip_redirects(w))[:2] == ["pr", "merge"] for w in commands(cmd)) or any(
        re.search(r"(^|\x00)(\S*/)?gh\x00(.*\x00)?pr\x00(.*\x00)?merge(\x00|$)", "\x00".join(w)) for w in segments(cmd))
    if merges:
        return "merging is divan's; no agent merges"
    if agent != "worker" and any(redirects_to_file(w) for w in segments(cmd)):  # before wrappers are peeled
        return f"{agent}: output redirect to a file"
    for w in commands(cmd):
        if agent == "worker":
            why = worker(strip_redirects(w))
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

    tmp = tempfile.TemporaryDirectory()
    ev = tmp.name
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
    # Wrapper and option regressions
    for a in ("manager", "worker", "reviewer", "critic"):
        assert B(a, "gh pr --repo o/r merge 1") and B(a, "gh -R o/r pr merge 1") and B(a, "bash -lc 'gh pr merge 1'"), a
    for c in ("bash -lc 'git push origin HEAD:main'", "sh -ec 'git push origin main'", "git push", "git push origin",
              "git push -u origin HEAD"):
        assert B("worker", c), c
    assert not B("worker", "git push -u origin feat")
    for a in ("manager", "reviewer", "critic"):
        for c in ("bash -lc 'rm x'", "zsh -xc 'touch x'", "sort -o/tmp/a /tmp/b", "sort -ro /tmp/a b", "sort --output=/tmp/a b",
                  "tree -o/tmp/t", "uniq a b", "git branch --edit-description", "git branch -m a b", "git branch new",
                  "git remote add x u", "gh api repos/o/r/issues -ftitle=a", "gh api repos/o/r/issues -Fx=1",
                  "gh api repos/o/r/issues --field=title=a", "gh api repos/o/r/issues --input f.json",
                  "gh api -X POST repos/o/r/issues", "gh api -XPOST repos/o/r/issues", "gh api --method=PATCH repos/o/r"):
            assert B(a, c), (a, c)
        for c in ("git branch -a", "git branch --show-current", "git branch --contains abc", "git branch --list 'f*'",
                  "git remote -v", "git remote get-url origin", "gh api repos/o/r/pulls", "gh api -X GET repos/o/r",
                  "gh --repo o/r pr view 1", "sort -r a"):
            assert not B(a, c), (a, c)
    wrapped = ("env --unset FOO {}", "env -u FOO {}", "env -C /tmp {}", "env -S '{}'", "env FOO=1 BAR=2 {}",
               "nice -n 5 {}", "sudo -u root {}", "xargs -I x -n 1 -P 2 {}", "time -p {}", "command -p {}",
               "exec -a name {}", "nohup {}", "env -- {}")
    for a in ("manager", "worker", "reviewer", "critic"):
        for f in wrapped:
            assert B(a, f.format("gh pr merge 1")), (a, f)
        assert B(a, "gh pr --unknown x merge 1"), a  # raw-text merge check
    for f in wrapped:
        assert B("manager", f.format("rm target")) and B("worker", f.format("git push origin HEAD:main")), f
    for a in ("manager", "reviewer", "critic"):
        assert B(a, "bash -c 'printf ok' > target") and B(a, "env bash -lc 'ls' >> target"), a
        assert not B(a, "gh pr view 1 --json mergeable") and not B(a, "git branch -av"), a
    for c in ("git add -Av", "git add -vA", "git commit -am x", "git commit -va", "git clean -fd", "git clean -df"):
        assert B("worker", c), c
    assert B("manager", "sed -ni s/a/b/ f") and B("manager", "curl -sXPOST u") and not B("manager", "curl -sL https://x") and B("reviewer", "git branch -ad x")
    for a in ("manager", "reviewer", "critic"):
        for c in ("git status >| r.txt", "cat README.md >|r.txt", "bash -c 'ls >| r.txt'", "time -o /tmp/r ls",
                  "time --output=/tmp/r ls", "time -o/tmp/r ls"):
            assert B(a, c), (a, c)
        assert not B(a, "time -p ls") and not B(a, "gh pr view 1 --json body --jq '.body | contains(\"merge\")'"), a
    for c in ("git push origin :", "git push origin +:", "git push origin 'refs/heads/*:refs/heads/*'",
              "git push origin refs/heads/main", "git push origin HEAD:refs/heads/deploy", "git push origin 'feat*'"):
        assert B("worker", c), c
    assert not B("worker", "git push origin feat:refs/heads/feat") and not B("worker", "time -o t.log git status")
    tmp.cleanup()
    print("ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--test"]:
        sys.exit(test())
    reason = check(json.load(sys.stdin))
    if reason:
        print(f"Blocked by divan limits: {reason}.", file=sys.stderr)
        sys.exit(2)
