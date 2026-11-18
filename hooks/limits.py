#!/usr/bin/env python3
"""PreToolUse hook: the limits of the divan agents, keyed on the hook input's agent_type.

Bash rules read the command text, so a command that writes through its own syntax or a script gets past them.
The manager is on a denylist so it can run a repo's checks; the reviewer and the critic are on an allowlist.
`python3 limits.py --test` runs the self-check.
"""
import functools, json, os, re, shlex, subprocess, sys, tempfile

READ = {"git", "gh", "ls", "cat", "head", "tail", "wc", "rg", "grep", "jq", "pwd", "echo", "printf", "date", "diff",
        "stat", "file", "tree", "sort", "uniq", "cut", "which", "true", "cd", "find", "test", "["}
EXTRA = {"reviewer": {"codex"}, "critic": {"superset", "paradev"}}
WRITE = {"rm", "rmdir", "mv", "cp", "touch", "tee", "mkdir", "ln", "chmod", "chown", "dd", "truncate", "install", "rsync"}
# Option tables: {option: number of values}. An option missing from its table blocks the command.
WRAP = {
    "env": {"-i": 0, "--ignore-environment": 0, "-u": 1, "--unset": 1, "-C": 1, "--chdir": 1, "-S": 1,
            "--split-string": 1},
    "sudo": {"-u": 1, "--user": 1, "-g": 1, "--group": 1, "-E": 0, "--preserve-env": 0, "-H": 0, "--set-home": 0,
             "-n": 0, "--non-interactive": 0},
    "xargs": {"-I": 1, "-n": 1, "--max-args": 1, "-P": 1, "--max-procs": 1, "-L": 1, "--max-lines": 1, "-d": 1,
              "--delimiter": 1, "-0": 0, "--null": 0, "-r": 0, "--no-run-if-empty": 0, "-t": 0, "--verbose": 0},
    "timeout": {"-s": 1, "--signal": 1, "-k": 1, "--kill-after": 1, "--preserve-status": 0, "--foreground": 0,
                "-v": 0, "--verbose": 0},
    "nice": {"-n": 1, "--adjustment": 1}, "nohup": {}, "command": {"-p": 0}, "time": {"-p": 0},
    "exec": {"-a": 1, "-c": 0, "-l": 0}}
SHELL = {"--norc": 0, "--noprofile": 0, "--login": 0, "--posix": 0, "--noediting": 0, "--restricted": 0,
         "--verbose": 0, "--rcfile": 1, "--init-file": 1, "-o": 1, "+o": 1, "-O": 1, "+O": 1,
         **{f"{s}{c}": 0 for s in "-+" for c in "abcefhiklmnprstuvxBCEHPT"}}
GIT_GLOBAL = {"-C": 1, "-c": 1, "--no-pager": 0, "-P": 0}
CURL = {"-s": 0, "--silent": 0, "-S": 0, "--show-error": 0, "-L": 0, "--location": 0, "-f": 0, "--fail": 0,
        "-i": 0, "--include": 0, "-I": 0, "--head": 0, "-v": 0, "--verbose": 0, "-G": 0, "--get": 0,
        "--compressed": 0, "-H": 1, "--header": 1, "-A": 1, "--user-agent": 1, "-m": 1, "--max-time": 1,
        "--retry": 1, "-w": 1, "--write-out": 1, "--url": 1, "-e": 1, "--referer": 1}
SHELLS = ("sh", "bash", "zsh", "dash", "ksh", "fish")
RISKY_ENV = r"^(GIT_\w*|PAGER|EDITOR|VISUAL|BASH_ENV|ENV|PATH|LESSOPEN|LESSCLOSE|LD_\w+|DYLD_\w+)="  # change what runs
PREFIX_WORDS = {"if", "then", "else", "elif", "while", "until", "do", "!", "{"}  # shell words before a command
END_WORDS = {"fi", "done", "}"}
SHORT_VALUES = {"commit": "mFcCtS?u?", "checkout": "bB", "switch": "cC", "clean": "e", "restore": "s"}  # `?`: optional
LONG_VALUES = {  # git long options that take the next word as their value
    "commit": ("--message", "--file", "--author", "--date", "--template", "--reuse-message", "--reedit-message",
               "--fixup", "--squash", "--cleanup", "--trailer", "--pathspec-from-file"),
    "checkout": ("--orphan", "--conflict", "--pathspec-from-file"), "switch": ("--create", "--force-create", "--orphan"),
    "clean": ("--exclude",), "add": ("--chmod", "--pathspec-from-file"), "restore": ("--source", "--pathspec-from-file")}
SWEEP_PATHS = {".", ":/", ":", "*", ":/*"}  # pathspecs that take the whole tree
READER_OPTS = {  # read tools: (short letters that take a value, `?` if optional; long options that take the next word)
    "sed": ("efli?", ("--expression", "--file", "--line-length")),
    "sort": ("ktoST", ("--key", "--field-separator", "--temporary-directory", "--buffer-size", "--parallel",
                       "--files0-from", "--random-source", "--compress-program", "--batch-size", "--output")),
    "tree": ("LPIoHT", ("--charset", "--filelimit", "--timefmt", "--sort")),
    "uniq": ("fsw", ("--skip-fields", "--skip-chars", "--check-chars")),
    "rg": ("efgtTABCmMjE", ("--regexp", "--file", "--glob", "--type", "--type-not", "--max-count", "--context",
                            "--before-context", "--after-context", "--threads", "--encoding")),
    "file": ("mefFP", ("--magic-file", "--exclude", "--separator", "--files-from", "--parameter")),
    "date": ("dfrsI?", ("--date", "--file", "--reference")),
    "git grep": ("efABCmO?", ("--max-depth", "--threads", "--max-count", "--context", "--before-context",
                             "--after-context"))}
RUNS_OR_WRITES = {"rg": ("", ("--pre",)), "sort": ("", ("--compress-program",)), "file": ("C", ("--compile",)),
                  "date": ("s", ("--set",)), "git grep": ("O", ("--open-files-in-pager",))}  # run a program or change state
GIT_READ = {"status", "log", "diff", "show", "rev-parse", "ls-files", "grep", "blame", "describe", "shortlog",
            "cat-file", "ls-tree", "merge-base", "rev-list", "worktree", "branch", "remote", "stash"}
GH_READ = {"view", "list", "diff", "checks", "status", "watch"}
GH_VALUE = {"-R", "--repo", "--hostname", "-X", "--method", "-H", "--header", "-f", "-F", "--field", "--raw-field",
            "--input", "-q", "--jq", "-t", "--template", "--json", "-b", "--body", "--title", "-L", "--limit"}
BRANCH_READ = {"-a", "-r", "-v", "-vv", "--list", "--show-current", "--contains", "--merged", "--no-merged"}
BRANCH_PATTERN = {"--list", "--contains", "--merged", "--no-merged"}  # options that take a pattern or commit
CODEX = {  # codex 0.169 subcommand: its allowed flags, True if the flag takes a value
    "exec": {"-s": True, "--sandbox": True, "-c": True, "--config": True, "-C": True, "--cd": True, "-m": True,
             "--model": True, "--skip-git-repo-check": False, "--ephemeral": False, "--json": False},
    "review": {"-c": True, "--config": True, "--base": True, "--uncommitted": False, "--commit": True, "--title": True}}
PUSH_FLAGS = {"-u", "--set-upstream", "-f", "--force", "--force-with-lease", "--no-verify", "-n", "--dry-run", "-q", "-v"}
BROWSER_READ = {"list", "open", "navigate", "screenshot", "console"}
SEP = {"&&", "||", ";", "|", "&", "(", ")", ";;", "|&"}
REDIR = set("<>&|")  # `>|` writes too
OPS, BRACES, STAND_IN = "<>|&;()", "{}", 0xE000  # shell operators, braces; private-use offset for quoted copies
GLOB = r"[*?\[\]{}]"  # expanded by the shell when unquoted, or a pattern to git
FIND_END = {";", "+", chr(STAND_IN + ord(";"))}  # ends a find -exec command (`\;` and `';'` stay stand-ins)
AGENTS = ("manager", "worker", "reviewer", "critic")


class Blocked(Exception):
    """Raised where the parser meets something it does not know; the command blocks with this reason."""
SESSIONS = os.path.join(os.environ.get("TMPDIR", "/tmp"), "divan-limits")  # session_id -> its main thread's agent


def heredoc(cmd, i):
    """(delimiter, quoted, `<<-`, end index) of the heredoc marker `<<[-]WORD` at i."""
    j = i + 2 + (cmd[i + 2:i + 3] == "-")
    while j < len(cmd) and cmd[j] in " \t":
        j += 1
    k = j
    while k < len(cmd) and not cmd[k].isspace() and cmd[k] not in OPS:
        k += 1
    word = cmd[j:k]
    return re.sub(r"['\"\\]", "", word), bool(re.search(r"['\"\\]", word)), cmd[i + 2:i + 3] == "-", k


def skip_bodies(cmd, i, pending):
    """Index after the heredoc bodies that start at i. A body is data; one whose delimiter is unquoted expands
    $(...) and backticks, so such a body that has them blocks, as does a body with no closing delimiter."""
    for delim, quoted, dash in pending:
        line = ""
        while True:
            if i >= len(cmd):
                raise Blocked(f"heredoc `{delim}` has no closing line")
            end = cmd.find("\n", i) % (len(cmd) + 1)
            line, i = line + cmd[i:end], end + 1
            if not quoted and re.search(r"(^|[^\\])(\\\\)*\\$", line):  # unquoted: backslash-newline joins lines
                line = line[:-1]
                continue
            if (line.lstrip("\t") if dash else line) == delim:
                break
            if not quoted and re.search(r"\$\(|`", line):
                raise Blocked("a heredoc with an unquoted delimiter runs its $(...)")
            line = ""
    return i


def preprocess(cmd):
    """cmd as bash reads it before splitting words, in one pass and bash's order: a backslash-newline outside single
    quotes is removed first, so `foo\\<newline>#bar` is one word; then an unquoted `#` that starts a word (not after an
    escaped space) drops the rest of the line, keeping the newline, and a backslash there continues nothing; heredoc
    bodies are dropped (see skip_bodies)."""
    out, q, i, pending, word_start = "", None, 0, [], True
    while i < len(cmd):
        ch = cmd[i]
        if q != "'" and ch == "\\":
            if cmd[i + 1:i + 2] != "\n":  # an escaped character is part of the word
                out, word_start = out + cmd[i:i + 2], False
            i += 2
            continue
        if q is None and ch == "#" and word_start:
            i = cmd.find("\n", i) % (len(cmd) + 1)
            continue
        if q is None and cmd.startswith("<<", i) and not cmd.startswith("<<<", i):
            *marker, j = heredoc(cmd, i)
            out, i, word_start = out + cmd[i:j], j, False
            pending.append(marker)
            continue
        if q is None and ch == "\n" and pending:
            out, word_start = out + ch, True
            i, pending = skip_bodies(cmd, i + 1, pending), []
            continue
        if q is None and ch in "'\"":
            q = ch
        elif ch == q:
            q = None
        out, word_start = out + ch, q is None and (ch.isspace() or ch in OPS)
        i += 1
    return out


def protect(cmd):
    """cmd with quoted or escaped operator characters swapped for private-use stand-ins, so `grep ">" f` keeps `>`
    a word (shlex alone drops the quotes and returns a bare `>`), and unquoted newlines made `;`."""
    out, q, i = [], None, 0
    while i < len(cmd):
        ch = cmd[i]
        if q != "'" and ch == "\\" and i + 1 < len(cmd):
            nxt = cmd[i + 1]
            out.append(ch + (chr(STAND_IN + ord(nxt)) if nxt in OPS + BRACES else nxt))
            i += 2
            continue
        if q is None and ch in "'\"":
            q = ch
        elif ch == q:
            q = None
        elif q and ch in OPS + BRACES:
            ch = chr(STAND_IN + ord(ch))
        elif not q and ch == "\n":  # an unquoted newline ends a command
            ch = " ; "
        out.append(ch)
        i += 1
    return "".join(out)


def unprotect(t):
    """Stand-ins back to their characters, except in a token made only of them (a quoted operator stays a word) and
    for braces, which stay stand-ins so a quoted `{` is told from one the shell expands."""
    if t and all(ord(ch) >= STAND_IN for ch in t):
        return t
    return "".join(chr(ord(ch) - STAND_IN) if ord(ch) >= STAND_IN and chr(ord(ch) - STAND_IN) not in BRACES else ch
                   for ch in t)


def unbrace(t):
    """t with brace stand-ins back to braces, for a string the shell parses again (`bash -c`, `eval`, `env -S`)."""
    return "".join(chr(ord(ch) - STAND_IN) if ord(ch) >= STAND_IN else ch for ch in t)


def backtick_end(cmd, i):
    """Index of the backtick closing one whose body starts at i; quotes inside it block."""
    while i < len(cmd) and cmd[i] != "`":
        if cmd[i] in "'\"":
            raise Blocked("quotes inside backticks; use $(...)")
        i += 2 if cmd[i] == "\\" else 1
    if i >= len(cmd):
        raise Blocked("cannot tell where a backtick substitution ends")
    return i


def sub_end(cmd, i):
    """Index of the `)` closing a $( whose body starts at i, honouring quotes, escapes and nested substitutions."""
    q, depth, pending = None, 1, []
    while i < len(cmd):
        ch = cmd[i]
        if q != "'" and ch == "\\":
            i += 2
            continue
        if q is None and cmd.startswith("<<", i) and not cmd.startswith("<<<", i):
            *marker, i = heredoc(cmd, i)
            pending.append(marker)
            continue
        if q is None and ch == "\n" and pending:
            i, pending = skip_bodies(cmd, i + 1, pending), []
            continue
        if q is None and ch == "#" and cmd[i - 1].isspace():
            i = cmd.find("\n", i) % (len(cmd) + 1)
            continue
        if q is None and ch in "'\"":
            q = ch
        elif ch == q:
            q = None
        elif q != "'" and cmd.startswith("$(", i):
            i = sub_end(cmd, i + 2)
        elif q is None and ch == "`":
            i = backtick_end(cmd, i + 1)
        elif q is None and ch in "()":
            depth += 1 if ch == "(" else -1
            if not depth:
                return i
        i += 1
    raise Blocked("cannot tell where a $(...) ends")


def substitutions(cmd):
    """Bodies of $(...) and `...` in cmd, skipping single-quoted text (literal there) and $((arithmetic)). Where the
    end of a body is unsure (unclosed, a `case` whose `)` ends it early, quotes in backticks) the command blocks."""
    out, q, i = [], None, 0
    while i < len(cmd):
        ch = cmd[i]
        if q != "'" and ch == "\\":
            i += 2
            continue
        if q != "'" and cmd.startswith("$(", i) and not cmd.startswith("$((", i):
            j = sub_end(cmd, i + 2)
            if re.search(r"\bcase\b", cmd[i + 2:j]):
                raise Blocked("`case` inside $(...)")
            out.append(cmd[i + 2:j])
            i = j + 1
            continue
        if q != "'" and ch == "`":
            j = backtick_end(cmd, i + 1)
            out.append(cmd[i + 1:j])
            i = j + 1
            continue
        if q is None and ch in "'\"":
            q = ch
        elif ch == q:
            q = None
        i += 1
    return out


def segments(cmd):
    """Simple commands in cmd as word lists; $(...) and `...` bodies count as commands too."""
    cmd = preprocess(cmd)
    out = [seg for body in substitutions(cmd) for seg in segments(body)]
    lex = shlex.shlex(protect(cmd), posix=True, punctuation_chars=True)
    lex.whitespace_split, lex.commenters = True, ""  # comments are already gone
    try:
        toks = [unprotect(t) for t in lex]
    except ValueError:
        raise Blocked("unbalanced quotes; the hook cannot read the command")
    seg = []
    for t in toks + [";"]:
        if t in SEP:
            out.append(seg)
            seg = []
        else:
            seg.append(t)
    return [s for s in out if s]


def shell_command(w):
    """The command string of `sh|bash|zsh ... -c ... <cmd>`, read as bash reads argv: options (clusters, -o/-O and
    --rcfile/--init-file values) and a `--` come first, then the first operand is <cmd>. None without -c."""
    own, rest = read_options(w[0], w[1:], SHELL)
    c = any(re.match(r"^-[a-zA-Z]*c", a) for a in own)
    return rest[0] if c and rest else None


def read_options(tool, w, table):
    """Split w into (options, rest) by table {option: number of values}: rest starts at the first operand or after
    `--`. Reads clusters of value-less flags (`-0r`) and attached values (`-n1`, `--max-args=1`); an option missing
    from the table raises Blocked. A cluster ending in a value option (bash `-eo pipefail`) takes the next word."""
    own, i = [], 0
    while i < len(w):
        a = w[i]
        if a == "--":
            return own + [a], w[i + 1:]
        if not re.match(r"^[-+].", a) or a[0] == "+" and a not in table:
            break
        if a.startswith("--"):
            name, eq, _ = a.partition("=")
            n = table.get(name)
            if n is None or eq and not n:
                raise Blocked(f"`{tool} {a}` is an option the hook does not know")
            take = 1 if eq else 1 + n
        elif a in table:
            take = 1 + table[a]
        else:
            letters, value_next = cluster(a, "".join(k[1:] for k, n in table.items() if n == 1 and len(k) == 2 and k[0] == a[0]))
            if any(a[0] + c not in table for c in letters):
                raise Blocked(f"`{tool} {a}` is an option the hook does not know")
            take = 1 + value_next
        own, i = own + w[i:i + take], i + take
    return own, w[i:]


def commands(cmd):
    """Simple commands in cmd with wrappers peeled: `env X=1 git push` is `git push`; `bash -c '<cmd>'` is <cmd>.
    A wrapper and its own options come out as a command too, so `time -o FILE` is checked."""
    for w in segments(cmd):
        yield from peel(w)


def peel(w):
    """The commands one simple command w runs: itself, or what its wrapper, shell, eval or `find -exec` runs."""
    while w:
        tool = w[0].rsplit("/", 1)[-1]
        if w[0] in PREFIX_WORDS | END_WORDS:
            w = w[1:]
            continue
        if w[0] in ("for", "select"):
            if not (re.match(r"^\w+$", (w[1:2] or ["("])[0]) and w[2:3] in ([], ["in"])):
                raise Blocked(f"a `{w[0]}` header the hook cannot read")
            return  # `for NAME in WORDS` runs nothing itself; its body is the next commands
        if w[0] in ("case", "function", "coproc"):
            raise Blocked(f"`{w[0]}` is shell syntax the hook does not read")
        if re.match(RISKY_ENV, w[0]):
            raise Blocked(f"`{w[0].split('=')[0]}=` changes what a command runs")
        if re.match(r"^\w+=", w[0]):
            w = w[1:]
        elif tool == "eval":
            yield from commands(unbrace(" ".join(w[1:])))
            w = []
        elif tool in SHELLS and shell_command(w) is not None:
            yield from commands(unbrace(shell_command(w)))
            w = []
        elif tool == "find":
            yield w
            for i, t in enumerate(w):
                if t in ("-exec", "-execdir", "-ok", "-okdir"):
                    end = next((k for k in range(i + 1, len(w)) if w[k] in FIND_END), len(w))
                    yield from peel(w[i + 1:end])
            w = []
        elif tool in WRAP:
            own, w = read_options(tool, w[1:], WRAP[tool])
            if tool == "timeout":
                own, w = own + w[:1], w[1:]  # the duration
            split = option_values(own, "-S", "--split-string")
            if split:
                w = shlex.split(unbrace(split[0])) + w  # env -S '<cmd>' runs <cmd>
            yield [tool] + own
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
    """(global options, the rest) of a git command; a global option other than -C, -c, --no-pager, -P blocks."""
    return read_options("git", w[1:], GIT_GLOBAL)


@functools.lru_cache(maxsize=None)
def git_commands():
    """git's own and installed commands, aliases excluded."""
    out = subprocess.run(["git", "--list-cmds=main,others"], capture_output=True, text=True).stdout
    return frozenset(out.split())


def cluster(a, values):
    """(letters, value is the next word) of a short-option cluster, read as git and getopt read it: letters until one
    in `values`, which takes the rest of the cluster (`-mfix`), or the next word when it is last (`-am`). A letter
    followed by `?` in `values` takes an optional value: only an attached one, never the next word (`-S`, `-u`)."""
    for j, c in enumerate(a[1:], 1):
        if c.isalnum() and c in values:
            return a[1:j + 1], j == len(a) - 1 and values[values.index(c) + 1:][:1] != "?"
    return a[1:], False


def long_opt(args, *names):
    """True if args hold one of the long options in names, in full, with `=value`, or abbreviated: getopt and git take
    any prefix (`--har` is `--hard`)."""
    return any(len(n := a.split("=", 1)[0]) > 2 and a.startswith("--") and any(o.startswith(n) for o in names)
               for a in args)


def split_args(args, values="", long_values=()):
    """(short flags, long options, operands) of args, read as git and getopt read them: clusters through cluster(),
    `values` are the letters that take a value (`-am'fix: a'` is a and m; `-mchange` is m alone), a long option in
    long_values takes the next word (`--message -a` sets no flag), and `--` makes every later word an operand."""
    short, longs, pos, i = set(), [], [], 0
    while i < len(args):
        a = args[i]
        if a == "--":
            pos += args[i + 1:]
            break
        if a.startswith("--"):
            longs.append(a)
            i += 1 + ("=" not in a and long_opt([a], *long_values))
        elif re.match(r"^-[a-zA-Z]", a):
            letters, value_next = cluster(a, values)
            short |= set(letters)
            i += 1 + value_next
        else:
            pos.append(a)
            i += 1
    return short, longs, pos


def short_flags(args, values="", long_values=()):
    return split_args(args, values, long_values)[0]


def option_values(w, short, long):
    """Values of an option given as `short v`, `shortv`, `long v` or `long=v`."""
    return ([w[i + 1] for i, a in enumerate(w[:-1]) if a in (short, long)]
            + [a[len(short):] for a in w if a.startswith(short) and len(a) > len(short) and not a.startswith("--")]
            + [a.split("=", 1)[1] for a in w if a.startswith(long + "=")])


def gh_options_after_command(w, n):
    """False if an option other than -R/--repo/--hostname comes before gh's first n words (its command)."""
    i, seen = 1, 0
    while i < len(w) and seen < n:
        if w[i] in ("-R", "--repo", "--hostname"):
            i += 2
            continue
        if w[i].startswith("-") and not w[i].startswith(("--repo=", "--hostname=")):
            return False
        seen += w[i][0] != "-"
        i += 1
    return True


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
    """True if w is `codex exec` or `codex review` with only allowlisted flags and every sandbox setting read-only."""
    sub = {"e": "exec"}.get((w[1:2] or [""])[0], (w[1:2] or [""])[0])
    flags, sandbox, pos, i = CODEX.get(sub), [], [], 2
    if flags is None:
        return False
    while i < len(w):
        a = w[i]
        if a == "-" or not a.startswith("-"):
            pos.append(a)
            i += 1
            continue
        name, eq, val = a.partition("=")
        if name not in flags and a[:2] in flags and not a.startswith("--"):  # attached short: -sread-only
            name, eq, val = a[:2], "=", a[2:]
        if name not in flags:
            return False
        if flags[name] and not eq:
            val, i = (w[i + 1] if i + 1 < len(w) else ""), i + 1
        if name in ("-s", "--sandbox"):
            sandbox.append("sandbox_mode=" + val)
        elif name in ("-c", "--config"):
            sandbox.append(val)  # the only -c allowed is sandbox_mode=read-only
        i += 1
    if sub == "exec" and pos[:1] and pos[0] in ("resume", "fork", "review", "help"):
        return False
    return set(sandbox) == {"sandbox_mode=read-only"}


def reader(agent, w):
    """Why w writes, for the manager (denylist) and the reviewer and critic (allowlist)."""
    tool = w[0].rsplit("/", 1)[-1]
    key = "git grep" if tool == "git" and git_args(w)[1][:1] == ["grep"] else tool
    args = git_args(w)[1][1:] if key == "git grep" else w[1:]
    short, longs, pos = split_args(args, *READER_OPTS.get(key, ("", ())))  # option values are not flags or operands
    if agent == "manager":
        if tool in WRITE:
            return f"`{tool}` writes files"
        if tool == "sed" and ("i" in short or long_opt(longs, "--in-place")):
            return "sed -i edits files"
    elif tool not in READ | EXTRA[agent] | WRAP.keys():
        return f"`{tool}` is not on the {agent}'s read-only list"
    if (tool == "sort" and ("o" in short or long_opt(longs, "--output")) or tool == "git" and long_opt(w, "--output")
            or tool == "tree" and "o" in short or tool == "uniq" and len(pos) > 1):
        return "an output file"
    bad_short, bad_long = RUNS_OR_WRITES.get(key, ("", ()))
    if set(bad_short) & short or bad_long and long_opt(longs, *bad_long):
        return f"`{key}` with an option that runs a program or changes state"
    if tool == "find" and {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprint0", "-fprintf", "-fls"} & set(w):
        return "find with -delete, -exec or -fprint"
    if tool == "git":
        opts, a = git_args(w)
        sub, rest = (a or [""])[0], a[1:]
        if any(o.startswith("-c") for o in opts):
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
            methods = option_values(w, "-X", "--method")
            if any(re.match(r"^(-[fF]|--(field|raw-field|input))", a) for a in w) or any(m.upper() != "GET" for m in methods):
                return "`gh api` with a body or a non-GET method writes"
        elif not (verb in GH_READ or noun == "search" or (noun, verb) == ("auth", "status")):
            return f"`gh {noun} {verb}` writes; gh is read-only here"
    if tool == "codex" and not codex_read_only(w):
        return ("codex runs only as `exec -s read-only` or `review -c sandbox_mode=\"read-only\"`, "
                "with the flags the reviewer uses (no -o, --yolo, --add-dir, ...)")
    if tool in ("superset", "paradev") and agent == "critic" and (w[1:2] != ["browser"] or (w[2:3] or [""])[0] not in BROWSER_READ):
        return "the critic uses only `superset browser list|open|navigate|screenshot|console`"
    if tool in ("superset", "paradev") and agent == "critic" and not all(
            os.path.isabs(p) and evidence_or_tmp(p) for p in map(expand_out, option_values(w, "--out", "--out"))):
        return "screenshots go to an absolute path in the evidence folder (next to charter.md) or $TMPDIR"
    if tool == "curl":
        rest = w[1:]
        while rest:  # options and URLs interleave
            _, rest = read_options("curl", rest, CURL)
            rest = rest[1:]
    return None


def worker(w):
    """Why the worker may not run w: pushes to main/deploy and git commands that sweep files. `w` is already a command
    in executable position (wrappers, shells, eval and `find -exec` peeled), so `rg git README.md` is not git."""
    return worker_git(w) if w[0].rsplit("/", 1)[-1] == "git" else None


def worker_git(w):
    opts, a = git_args(w)
    sub, rest = (a or [""])[0], a[1:]
    if sub and sub not in git_commands():
        return f"`git {sub}` is not a git command (an alias?); run the command it stands for"
    if sub == "push" and any(o.startswith("-c") for o in opts):
        return "`git -c ... push` can change where the push goes"
    pos = [x for x in rest if not x.startswith("-")]
    if sub == "push":  # allowlist: git push [flags] <remote> <refspec>...
        bad = [x for x in rest if x.startswith("-") and x not in PUSH_FLAGS and not x.startswith("--force-with-lease=")
               and not re.match(r"^-[ufnqv]+$", x)]
        if bad:
            return f"`{bad[0]}` is not allowed; push as `git push [-u] [--force-with-lease] origin <branch>`"
        if any(re.search(r"[$`]", x) for x in pos):
            return "name the remote and branch literally, not through a variable"
        if any(re.search(GLOB, x) for x in pos):
            return "a push remote or refspec with `*?[]` or an unquoted `{}`; name the branch literally"
        if any(x in (":", "+:") or re.search(r"(^|[:/+])(main|deploy)$", x) for x in pos[1:]):
            return "workers never push to main or deploy; push your branch"
        if len(pos) < 2 or any(re.match(r"^\+?(HEAD|@)$", x) for x in pos[1:]):  # the destination comes from config
            return "name the destination: `git push origin <branch>`"
    short, longs, pos = split_args(rest, SHORT_VALUES.get(sub, ""), LONG_VALUES.get(sub, ()))
    sweeps = (sub == "add" and ({"A", "u"} & short or long_opt(longs, "--all", "--update"))
              or sub in ("add", "checkout", "restore", "commit") and (SWEEP_PATHS & set(pos) or any(re.search(GLOB, x) for x in pos))
              or sub == "commit" and ("a" in short or long_opt(longs, "--all"))
              or sub == "stash" and rest[:1] not in (["list"], ["show"])
              or sub in ("checkout", "switch") and ("f" in short or long_opt(longs, "--force", "--discard-changes"))
              or sub == "restore" and not pos
              or sub == "reset" and long_opt(longs, "--hard")
              or sub == "clean" and ("f" in short or long_opt(longs, "--force")))
    if sweeps:
        return f"`git {' '.join(a)}` touches files beyond your own; stage, restore and clean by explicit path"
    return None


def expand_out(p):
    """A screenshot path with ~ and $TMPDIR (only that variable) expanded."""
    tmp = os.environ.get("TMPDIR", "")
    return os.path.expanduser(p.replace("${TMPDIR}", tmp).replace("$TMPDIR", tmp))


def evidence_or_tmp(p):
    """True if p, resolved, lies under $TMPDIR or under a directory holding charter.md (the evidence folder)."""
    p = os.path.realpath(p)
    tmp = os.path.realpath(os.environ.get("TMPDIR") or "/nonexistent")
    if os.path.commonpath([p, tmp]) == tmp:
        return True
    d = os.path.dirname(p)
    while d != os.path.dirname(d):
        if os.path.isfile(os.path.join(d, "charter.md")):
            return True
        d = os.path.dirname(d)
    return False


def brief_path(p):
    """True for a file directly in <evidence folder>/briefs/, the evidence folder being the one holding charter.md."""
    d = os.path.dirname(os.path.realpath(p))
    return os.path.basename(d) == "briefs" and os.path.isfile(os.path.join(os.path.dirname(d), "charter.md"))


def session_agent(event):
    """The divan agent whose limits apply: the event's own, else the one running its session's main thread, so a
    worker's general-purpose subagent is still a worker. A plain session's main thread stays unlimited."""
    scope, _, own = (event.get("agent_type") or "").rpartition(":")
    sid = re.sub(r"[^\w-]", "", event.get("session_id") or "")
    path = os.path.join(SESSIONS, sid)
    if scope == "divan" and own in AGENTS:  # only this plugin's agents; a bare `worker` is someone else's
        if sid and not event.get("agent_id"):  # main thread
            os.makedirs(SESSIONS, exist_ok=True)
            with open(path, "w") as f:
                f.write(own)
        return own
    try:
        with open(path if sid else "") as f:
            return f.read().strip()
    except OSError:
        return None


def check(event):
    agent = session_agent(event)
    if agent not in AGENTS:
        return None
    tool, inp = event.get("tool_name"), event.get("tool_input") or {}
    if tool == "Write" and agent == "manager" and not brief_path(inp.get("file_path", "")):
        return "the manager writes only briefs: files in <evidence folder>/briefs/, next to charter.md"
    if tool != "Bash":
        return None
    try:
        return bash(agent, inp.get("command", ""))
    except Blocked as e:
        return f"{agent}: {e}"


def merge_call(w, cmd):
    """True if w merges a PR: `gh pr merge`, a non-GET `gh api` call to pulls/<n>/merge, `gh api graphql` with a merge
    mutation (in its words, or anywhere in cmd when the body comes from --input), or curl/wget at pulls/<n>/merge."""
    tool = (w or [""])[0].rsplit("/", 1)[-1]
    if tool in ("curl", "wget", "http", "xh"):
        return any(re.search(r"pulls/\d+/merge", a) for a in w)
    if tool != "gh":
        return False
    words = gh_words(w)
    if words[:2] == ["pr", "merge"]:
        return True
    if words[:1] != ["api"]:
        return False
    body = any(re.match(r"^(-[fF]|--(field|raw-field|input))", a) for a in w)
    method = (option_values(w, "-X", "--method") or ["POST" if body else "GET"])[-1].upper()
    mutation = r"mergePullRequest|enablePullRequestAutoMerge"
    if words[1:2] == ["graphql"]:
        return any(re.search(mutation, a) for a in w) or long_opt(w, "--input") and bool(re.search(mutation, cmd))
    return method != "GET" and any(re.search(r"pulls/\d+/merge", a) for a in words[1:2])


def bash(agent, cmd):
    for w in map(strip_redirects, commands(cmd)):
        if w and w[0].rsplit("/", 1)[-1] == "gh":  # gh in executable position: its command words must be plain
            if any(re.search(r"[$`]", x) for x in gh_words(w)[:2]):
                return f"{agent}: name gh's command literally, not through a variable"
            if not gh_options_after_command(w, 1 if gh_words(w)[:1] == ["api"] else 2):
                return f"{agent}: `gh` with an option before its command that the hook does not know"
    if any(merge_call(strip_redirects(w), cmd) for w in commands(cmd)):
        return "merging is divan's; no agent merges"
    if agent != "worker" and any(redirects_to_file(w) for w in segments(cmd)):  # before wrappers are peeled
        return f"{agent}: output redirect to a file"
    for w in commands(cmd):
        if not strip_redirects(w):  # only redirections, e.g. what follows `done`
            continue
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

    global SESSIONS
    tmp = tempfile.TemporaryDirectory()
    ev, SESSIONS = tmp.name, f"{tmp.name}/sessions"
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
    assert not B("critic", f"superset browser screenshot --out {ev}/s.png") and not B("critic", "superset browser screenshot")
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
    assert not B("worker", "git push origin feat:refs/heads/feat") and not B("worker", "time -p git status") and B("worker", "time -o t.log git status")
    for c in ("env --split-string='git push origin HEAD:main'", "env -S'git push origin main'"):
        assert B("worker", c), c
    assert B("critic", "env --split-string='superset browser eval --expression x'") and B("manager", "env -S'rm x'")
    for c in ("git -ccore.pager='touch x' log", "git -c core.pager=less log", "git --config-env=core.pager=P log"):
        assert B("manager", c) and B("reviewer", c), c
    for c in ("codex review -c sandbox_mode=read-only -csandbox_mode=danger-full-access", "codex exec -s read-only -sdanger-full-access x",
              "codex exec -s read-only --config=sandbox_mode=workspace-write x"):
        assert B("reviewer", c), c
    assert not B("reviewer", "codex exec -sread-only x") and not B("reviewer", "codex review -csandbox_mode=read-only")
    # limits follow the session: a divan main thread's subagents get its limits; a plain session stays unlimited
    def E(sid, agent_type, agent_id, cmd):
        return check({"session_id": sid, "agent_type": agent_type, "agent_id": agent_id, "tool_name": "Bash",
                      "tool_input": {"command": cmd}, "cwd": "/"})

    assert not E("s1", "divan:worker", None, "git status")  # the worker's main thread records itself
    assert E("s1", "general-purpose", "a1", "git push origin HEAD:main") and E("s1", "Explore", "a2", "gh pr merge 1")
    assert E("s2", "divan:reviewer", "a3", "touch x") and not E("s2", None, None, "touch x")
    assert not E("s3", "general-purpose", "a4", "git push origin HEAD:main")  # no divan session: untouched
    assert E("s4", "divan:manager", None, "ls") is None and E("s4", "divan:reviewer", "a5", "superset ws list")
    for c in ("codex exec --yolo -s read-only x", "codex exec -s read-only -o out.txt x", "codex exec -s read-only -oout.txt x",
              "codex exec -s read-only --output-last-message=out.txt x", "codex exec -s read-only --add-dir /x x",
              "codex exec -s read-only --full-auto x", "codex exec -s read-only resume --last", "codex exec -s read-only review",
              "codex exec -s read-only -c model=o3 x", "codex review --base main -c sandbox_mode=read-only -m o3",
              "codex review --base main -c sandbox_mode=read-only --enable x", "codex exec -s", "codex login", "codex"):
        assert B("reviewer", c), c
    for c in ('codex exec -s read-only "review this"', "codex exec -s read-only --skip-git-repo-check --ephemeral --json -C /r -m o3 -",
              'codex review --base main -c sandbox_mode="read-only"', "codex review --uncommitted --config=sandbox_mode=read-only",
              "codex review --commit abc --title t -c sandbox_mode=read-only focus", "codex e -c sandbox_mode=read-only x"):
        assert not B("reviewer", c), c
    for sh in ("bash", "sh", "zsh"):
        for f in ("{} -c -- '{}'", "{} -c -e -- '{}'", "{} -o pipefail -c '{}'", "{} --norc -lc -- '{}'", "{} -O extglob -ec '{}'"):
            for a in AGENTS:
                assert B(a, f.format(sh, "gh pr merge 1")), (a, f, sh)
            assert B("worker", f.format(sh, "git push origin main")) and B("manager", f.format(sh, "rm f")), (f, sh)
    assert shell_command(["bash", "script.sh"]) is None and not B("manager", "bash -c -- 'ls'")
    for c in ("git push --repo=x origin feat", "git push -o ci.skip origin feat", "git push --push-option=x origin feat",
              "git push --tags origin feat", "git push --prune origin feat", "git push --delete origin feat",
              "git push --mirror origin", "git push --all origin", "git push --force-if-includes origin feat",
              "git push origin feat main", "git push origin feat '*'", "git push -fu origin HEAD"):
        assert B("worker", c), c
    for c in ("git push -u origin feat", "git push --force-with-lease=feat:abc origin feat", "git push -fu origin feat",
              "git push --no-verify --dry-run -q -v origin feat other", "git push --set-upstream origin feat"):
        assert not B("worker", c), c
    for a in ("manager", "reviewer", "critic"):
        for c in ('grep ">" README.md', "grep '>' f | head", "echo \\> x", "grep 'a > b' f", 'bash -c \'grep ">" f\''):
            assert not B(a, c), (a, c)
        for c in ("grep x > f", "grep '>' f > out", 'bash -c \'grep ">" f > out\'', "grep x '>'> f"):
            assert B(a, c), (a, c)
    for c in ("git \\\npush origin main", "git push \\\n origin main", "gh \\\npr merge 1", "bash -c 'git \\\npush origin main'",
              'git push origin "ma\\\nin"'):
        assert B("worker", c), c
    assert not B("worker", "git push origin 'ma\\\nin'")  # literal in single quotes: not main
    assert not B("worker", "echo 'a\\\nb' && git status") and B("manager", "ls \\\n> f")
    tmpdir, os.environ["TMPDIR"] = os.environ.get("TMPDIR"), "/nonexistent"  # test the evidence-folder rule alone
    os.symlink("/usr", f"{ev}/out")
    for c in (f"superset browser screenshot --out {ev}/shots/s.png", f"superset browser screenshot --out={ev}/briefs/s.png"):
        assert not B("critic", c), c
    for c in ("superset browser screenshot --out /usr/s.png", f"superset browser screenshot --out {ev}/out/s.png",
              f"superset browser screenshot --out {ev}/../s.png", "superset browser screenshot --out ~/s.png"):
        assert B("critic", c), c
    os.environ["TMPDIR"] = tmpdir or ""
    # Unknown options block: git globals, wrappers, shells, curl, gh before its command
    for c in ("git --git-dir .git push origin main", "git --work-tree=. push origin main", "git -c remote.origin.push=x push origin feat",
              "git -c alias.p=push p origin main", "git frobnicate", "timeout 60 git push origin main",
              "find . -exec git push origin main ';'", "xargs --arg-file f git push origin main",
              "sudo --user root git push origin main", "sudo --chroot=/ git status", "env --ignore-environment git push origin main"):
        assert B("worker", c), c
    for c in ("git -c user.name=x commit -m y", "git -C /r --no-pager -P log", "timeout -s KILL 5 git status"):
        assert not B("worker", c), c
    for a in ("manager", "reviewer", "critic"):
        for c in ("git --git-dir .git log", "git --exec-path=/x log", "nice -10 ls", "xargs -0r --arg-file f ls",
                  "bash --debugger -c 'ls'", "gh pr --body-file view create 1", "git grep -Ovim x", "rg --pre ./x y",
                  "sort --compress-program=sh f", "file -C -m m", "date -s 1", "command -v git"):
            assert B(a, c), (a, c)
        for c in ("git -C /r --no-pager -P log", "gh --repo o/r pr view 1 --comments", "gh api -X GET repos/o/r",
                  "timeout 5 ls", "xargs -0r ls", "echo '`rm x`'", "printf %s '$(touch x)'"):
            assert not B(a, c), (a, c)
        assert B(a, 'printf %s "$(touch x)"') and B(a, "echo \\'$(touch x)\\'"), a
    for c in ("timeout -s KILL 5 rm x", "xargs -0r rm", "curl -D h.txt https://x", "curl -c jar https://x",
              "curl --trace t https://x", "curl -sSLo f https://x"):
        assert B("manager", c), c
    for c in ("curl -sSL https://x", "curl -H 'A: b' https://x -w '%{http_code}'", "echo $((1+2))"):
        assert not B("manager", c), c
    # Hunted: eval, other shells, risky env assignments, variables in commands, sweeping pathspecs, find -okdir
    for c in ("eval 'git push origin main'", "fish -c 'git push origin main'", "dash -c 'gh pr merge 1'",
              "GIT_CONFIG_PARAMETERS=\"'remote.origin.push=refs/heads/x:refs/heads/main'\" git push origin x",
              "git push origin $BRANCH", "git push origin \"$(git branch --show-current)\"", "gh $CMD 1",
              "git add -u", "git add :/", "git checkout -- '*'", "git checkout -f main", "git switch --discard-changes x"):
        assert B("worker", c), c
    for c in ("LC_ALL=C git status", "gh pr view $N", "git add -p a.py", "git switch -c feat"):
        assert not B("worker", c), c
    for a in ("manager", "reviewer", "critic"):
        for c in ("GIT_PAGER='touch x' git log", "PAGER=x git log", "eval 'rm x'", "find . -okdir rm {} ';'",
                  "BASH_ENV=x.sh bash -c 'ls'", "gh $X 1"):
            assert B(a, c), (a, c)
        assert not B(a, "LC_ALL=C sort f"), a
    # Substitutions read with quotes; an unsure end blocks
    for a in ("manager", "reviewer", "critic"):
        for c in ('echo "$(printf \')\'; rm victim)"', "echo \"$(printf ')'; gh pr merge 1)\"", "echo $(echo \"(\"; rm x)",
                  "echo `printf ')'; rm x`", "echo \"$(case x in a) rm y;; esac)\"", "echo \"$(ls", "echo `ls", "echo `printf '%s' x`"):
            assert B(a, c), (a, c)
        for c in ("echo \"$(git log -1 --format='%s (%h)')\"", "echo \"$(echo \\\")\\\")\"", "echo `git status`"):
            assert not B(a, c), (a, c)
    assert B("worker", "echo \"$(printf ')'; gh pr merge 1)\"")
    for c in ('superset browser screenshot --out "$TMPDIR/s.png"', "superset browser screenshot --out ${TMPDIR}/s.png"):
        assert not B("critic", c), c
    assert B("critic", "superset browser screenshot --out $HOME/s.png")
    # Clusters read as git reads them; GraphQL merge mutations
    for c in ("git commit -am'fix: bug'", "git commit -vam x", "git clean -dfx", "git checkout -fb x", "git add -vA"):
        assert B("worker", c), c
    for c in ("git commit -mchange", "git commit -m -a", "git commit -mafix", "git clean -e foo -n", "git checkout -bf",
              "git switch -cf"):
        assert not B("worker", c), c
    assert B("manager", "sed -ni s/a/b/ f") and not B("manager", "sed -ei s/a/b/ f") and not B("manager", "sed -e -i f") and B("manager", "sed -i.bak s/a/b/ f")
    for a in AGENTS:
        for c in ("gh api graphql -f query='mutation { mergePullRequest(input: {pullRequestId: \"x\"}) { clientMutationId } }'",
                  "gh api graphql -F query='mutation{enablePullRequestAutoMerge(input:{pullRequestId:\"x\"}){clientMutationId}}'",
                  "echo '{\"query\":\"mutation{mergePullRequest(input:{})}\"}' | gh api graphql --input -"):
            assert B(a, c), (a, c)
    assert not B("worker", "gh api graphql -f query='query { viewer { login } }'")
    # git counts only where it runs; --output/-o only where they write
    for c in ("rg git README.md", "grep -r 'git push' docs", "echo git push origin main", "npm test -- --output-format=json"):
        assert not B("worker", c), c
    for c in ("find . -execdir git push origin main '+'", "find . -ok git add -A ';'", "xargs -n1 git push origin main",
              "nohup git push origin main", "find . -exec git push origin main \\;"):
        assert B("worker", c), c
    for c in ("npm test -- --output-format=json", "pytest -o log_cli=true", "jq -o x f"):
        assert not B("manager", c), c
    for c in ("sort -o out f", "sort --output=out f", "sort -ro out f", "tree -o out", "git log --output=x", "git diff --output x"):
        assert B("manager", c), c
    assert not B("manager", "sort -t, -k2 f") and not B("manager", "sort -to f") and not B("manager", "tree -L 2")
    # Comments end at a newline; git and getopt take abbreviated long options
    cases = {"manager": "ls # comment\nrm victim", "worker": "git status # comment\ngit push origin main",
             "reviewer": "ls # comment\ntouch victim", "critic": "pwd # comment\nsuperset browser eval --code bad"}
    for a, c in cases.items():
        assert B(a, c) and B(a, c.replace(" # comment", " # comment \\")) and B(a, c.replace("\n", " #x\n")), (a, c)
    for a in ("manager", "reviewer", "critic"):
        for c in ("ls # rm x", "echo 'a # b' && ls", "echo a#b", "ls # $(rm x)", "echo \"#\" # c"):
            assert not B(a, c), (a, c)
        for c in ("echo 'a\n#' && rm x", "sort --out=f g", "sort --outp f g", "sort --co=sh f", "git log --outp=x",
                  "git grep --open x", "date --se 1", "file --comp m"):
            assert B(a, c), (a, c)
        assert not B(a, "git log --output-indicator-new=+ -1"), a
        assert not B(a, 'echo \\" # "; rm x') and B(a, "echo a#b; rm x"), a  # escaped quote; # inside a word
        assert B(a, "echo 'unclosed; rm x") and B(a, 'echo "a'), a
        for c in ("cat <<'EOF'\nit's data; rm x\nEOF", "cat <<EOF\nit's plain\nEOF\nls", "cat <<-EOF\n\tit's\n\tEOF",
                  "echo \"$(cat <<'EOF'\nfix: it's done (really)\nEOF\n)\""):
            assert not B(a, c), (a, c)
        for c in ("cat <<'EOF'\nx\nEOF\nrm y", "cat <<EOF\n$(rm y)\nEOF", "cat <<EOF\nno end", "cat <<EOF > out\nx\nEOF",
                  "echo \"$(cat <<'EOF'\nit's\nEOF\n)\"; rm y"):
            assert B(a, c), (a, c)
    assert not B("worker", "git commit -m \"$(cat <<'EOF'\nfix: it's done\n\nCo-Authored-By: x\nEOF\n)\"")
    for c in ("git reset --har", "git clean --fo", "git add --al", "git add --upd", "git commit --al -m x",
              "git checkout --forc main", "git switch --disc x", "git push --al origin", "git push --mir origin"):
        assert B("worker", c), c
    assert not B("worker", "git commit --amend --no-edit") and not B("worker", "git commit --author=x -m y")
    # Shell keywords; long options with values; merge checks only on merge calls
    assert B("manager", "if true; then rm victim; fi") and B("manager", "{ rm x; }") and B("manager", "! rm x")
    assert B("worker", "bash -c 'if true; then git push origin main; fi'") and B("worker", "until false; do git push origin main; done")
    assert B("worker", "while read l; do git commit -am x; done < list") and B("worker", "for f in a b; do git add -A; done")
    for c in ("case x in a) rm y;; esac", "case x in a) echo ok;; esac", "function f { rm x; }", "for ((i=0;i<3;i++)); do ls; done", "coproc rm x",
              "select x; do rm y; done"):
        assert B("manager", c), c
    for a in ("manager", "reviewer", "critic"):
        for c in ("if test -f x; then cat x; else ls; fi", "for f in a b; do cat $f; done", "{ ls; }", "! grep -q x f"):
            assert not B(a, c), (a, c)
    assert not B("worker", "while true; do git status; done") and not B("worker", "if git diff --quiet; then git commit -m x; fi")
    assert not B("worker", "git commit --message -a") and not B("worker", "git commit --mess -a") and B("worker", "git commit --amend -a")
    for c in ("gh api repos/o/r/pulls/1/merge -X GET", "gh api repos/o/r/pulls/1/merge", "git log --format=mergePullRequest",
              "grep -r pulls/1/merge docs", "gh api graphql -f query='query { viewer { login } }'"):
        assert not B("worker", c), c
    for c in ("gh api repos/o/r/pulls/1/merge -X PUT", "gh api -XPUT repos/o/r/pulls/1/merge", "gh api repos/o/r/pulls/1/merge -f m=s",
              "curl -X PUT https://api.github.com/repos/o/r/pulls/1/merge"):
        assert B("worker", c), c
    # sed --in-place abbreviated; merges only from gh in executable position
    for c in ("sed --in-plac s/a/b/ f", "sed --in s/a/b/ f", "sed --in-place=.bak s/a/b/ f"):
        assert B("manager", c), c
    assert not B("manager", "sed --expression -i f") and not B("manager", "sed -n --expr s/a/b/p f")
    for a in AGENTS:
        for c in ("echo gh pr merge 1", "rg gh README.md --glob pr --glob merge"):
            assert not B(a, c), (a, c)
        assert a != "worker" or not B(a, "git commit -m 'run gh pr merge later'")
        for c in ("gh --unknown x pr merge 1", "gh pr --body-file x merge 1", "env gh pr merge 1", "if true; then gh pr merge 1; fi"):
            assert B(a, c), (a, c)
    # Sweeps read with split_args; only divan:-scoped agents count
    for c in ("git commit -m --all", "git add -- --all", "git commit -m -a x", "git add --chmod -A f", "git restore -s HEAD~1 a.py",
              "git checkout -b x -- a.py"):
        assert not B("worker", c), c
    for c in ("git add --all", "git commit -am x", "git add -- .", "git restore -s HEAD~1", "git checkout -b x .",
              "git restore --source HEAD~1"):
        assert B("worker", c), c
    for t in ("worker", "other:worker", "manager", "divanx:reviewer"):
        assert not check({"agent_type": t, "session_id": "s9", "tool_name": "Bash", "tool_input": {"command": "gh pr merge 1"}}), t
    assert not E("s9", "general-purpose", "a9", "gh pr merge 1")  # a bare `worker` main thread recorded nothing
    assert not B("reviewer", "codex exec -s read-only - <<'EOF'\nReview a.md, changed since main (git diff main), "
                             "against this bar: the charter's Great.\nReturn, per file: \"<file>  score: N/10\".\nEOF")
    # Glob and brace expansion in push operands and sweep pathspecs; quoted braces are literal
    for c in ("git push origin HEAD:{main,feature}", "git push origin [m]ain", "git push origin 'ma?n'", "git push {origin,x} f",
              "git add {.,a.py}", "git add 'src/*.py'", "git add a?.py", "git checkout -- '[a]'", "git commit .", "git commit -- *",
              "bash -c 'git push origin HEAD:{main,x}'", "eval 'git add {.,a}'"):
        assert B("worker", c), c
    for c in ("git push origin 'HEAD:{x}'", "git add 'a{b}.py'", "git add \\{a\\}.py", "git commit -m '{wip}' a.py",
              "git push origin feat-1"):
        assert not B("worker", c), c
    assert not B("manager", "jq '{a: .b}' f") and not B("manager", "{ ls; }") and B("manager", "{ rm x; }")
    # Reader tools: clusters split, option values are neither flags nor operands
    for a in ("manager", "reviewer", "critic"):
        for c in ("git grep -lOvim pattern", "git grep -O pattern", "git grep --open pattern", "file -bC -m m", "date -us 1",
                  "uniq in out", "uniq -c in out", "sort -ro out f", "sort -k1 --output out f", "tree -ao out"):
            assert B(a, c), (a, c)
        for c in ("uniq -f 1 input.txt", "uniq -s 2 input.txt", "uniq --skip-fields 1 input.txt", "git grep -e -O pattern",
                  "git grep -l --max-depth 2 x", "date -d 1 +%s", "file -m magic f", "sort -t o f", "sort --key -o f",
                  "rg -e --pre x f"):
            assert not B(a, c), (a, c)
    assert not B("manager", "sed -e --in-place f") and not B("manager", "sed --expression -i f") and B("manager", "sed -ni s/a/b/ f")
    # bash's order: continuations join before comments; an escaped space keeps `#` inside the word
    for a, c in (("manager", "rm victim"), ("reviewer", "touch victim"), ("critic", "touch victim"), ("worker", "git push origin main")):
        assert B(a, f"echo foo\\\n#bar; {c}") and B(a, f"echo a\\ #b; {c}") and B(a, f"echo a # b \\\n{c}"), (a, c)
        assert not B(a, f"echo a #b; {c}"), (a, c)
    assert B("manager", "cat <<EOF # c\nbody\nEOF\nrm victim") and not B("manager", "cat <<EOF # c\nrm in body\nEOF")
    assert B("manager", "cat <<EOF\n$\\\n(rm x)\nEOF") and not B("manager", "cat <<'EOF'\n$\\\n(rm x)\nEOF")
    assert not B("manager", "cat <<EOF\na \\\\\nEOF")  # an escaped backslash ends the line: no join
    assert not B("manager", "cat <<'EOF'\nx\\\nEOF\nls")  # quoted: a trailing backslash is data
    # Optional values (-S[keyid], -u[mode], -I[fmt], -O[pager], -i[suffix]) are attached only, never the next word
    for c in ("git commit -u -a -m fix", "git commit -S -a -m fix", "git commit -uno -a"):
        assert B("worker", c), c
    assert not B("worker", "git commit -Sa -m fix") and not B("worker", "git commit -m -a")  # -Sa: key `a`
    for a in ("manager", "reviewer", "critic"):
        assert B(a, "date -I -s 2030-01-01") and not B(a, "date -Iseconds") and B(a, "git grep -O -e x"), a
    assert B("manager", "sed -i -e s/a/b/ f") and B("manager", "sed -in s/a/b/ f")
    here = os.getcwd()
    os.chdir(ev)  # relative paths would resolve inside the evidence folder; they block anyway
    for c in ("superset browser screenshot --out shot.png", "superset browser screenshot --out ./s.png",
              "superset browser screenshot --out=s.png"):
        assert B("critic", c), c
    os.chdir(here)
    tmp.cleanup()
    print("ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--test"]:
        sys.exit(test())
    reason = check(json.load(sys.stdin))
    if reason:
        print(f"Blocked by divan limits: {reason}.", file=sys.stderr)
        sys.exit(2)
