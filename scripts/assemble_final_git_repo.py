import subprocess
from pathlib import Path
import re
import bisect

repo_path = Path("r_ecosystem_tracks_output")
input_path = Path("r_ecosystem_tracks")


def get_branches(repo_path):
    return [
        x[2:]
        for x in (
            subprocess.check_output(["git", "branch", "--list"], cwd=repo_path)
            .decode("utf-8")
            .strip()
            .split("\n")
        )
    ]


def checkout(repo_path, tag):
    print("checkout", tag)
    return subprocess.check_call(["git", "checkout", tag, "-q"], cwd=repo_path)


def branch(repo_path, tag):
    print("branch", tag)
    return subprocess.check_call(["git", "checkout", "-b", tag], cwd=repo_path)


def add_all(repo_path):
    print("add_all")
    return subprocess.check_call(["git", "add", "--all"], cwd=repo_path)


def rsync(source, target):
    print("rsync", source.name)
    subprocess.check_call(
        ["rsync", str(source) + "/", str(target), "--exclude=.git", "--delete", "-r"]
    )


def reset(repo_path):
    subprocess.check_call(["git", "reset", "--hard", "-q"], cwd=repo_path)


def changed(repo_path):
    s = subprocess.check_output(["git", "status", "-s"], cwd=repo_path).decode("utf-8")
    print('changed', repr(s))
    if "nothing to commit" in s:
        return False
    return s != ''


def git_commit(repo_path, msg):
    subprocess.check_call(["git", "commit", "-m", msg], cwd=repo_path)


def starts_with_date(x):
    return bool(re.match("^[0-9]{4}-[0-9]{2}-[0-9]{2}", x))


if not repo_path.exists():
    subprocess.check_call(["git", "init", str(repo_path)])
    (repo_path / ".gitignore").write_text("#")
    subprocess.check_call(["git", "add", ".gitignore"], cwd=repo_path)
    subprocess.check_call(["git", "commit", "-m", "fill_master"], cwd=repo_path)
    subprocess.check_call(["git", "branch", "-m", "master", "main"], cwd=repo_path)

print(get_branches(repo_path))
known_tags = [x for x in get_branches(repo_path) if starts_with_date(x)]
print("known tags", known_tags)

for d in sorted(input_path.glob("*")):
    if (
        d.is_dir()
        and starts_with_date(d.name)
        and len(d.name) == 10
        and (d / "final_done").exists()
    ):
        print(d)
        matching_tags = [x for x in known_tags if x.startswith(d.name)]
        if matching_tags:
            latest = max(matching_tags)
            next = str(int(latest[latest.rfind("_") + 1 :]) + 1)
        else:
            if len(known_tags) > 1:
                smaller = [x for x in known_tags if x[:10] < d.name]
                latest = max(smaller)
            else:
                latest = "main"
            next = 1
        next = d.name + "_" + str(next)
        print("checkout")
        checkout(repo_path, latest)
        reset(repo_path)

        rsync(d / "flake", repo_path)
        add_all(repo_path)
        if changed(repo_path):
            print("switching to", next)
            branch(repo_path, next)
            msg = (d / "final_done").read_text()
            git_commit(repo_path, d.name)
        else:
            print("not changed")
