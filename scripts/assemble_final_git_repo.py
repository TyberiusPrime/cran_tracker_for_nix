import subprocess
import json
from pathlib import Path
import re
import bisect

repo_path = Path("r_ecosystem_tracks_output")
input_path = Path("r_ecosystem_tracks")


def get_branches(repo_path):
    b = subprocess.check_output(["git", "branch", "--list"], cwd=repo_path).decode(
        "utf-8"
    )
    return [x.replace("*",'').lstrip() for x in (b.strip().split("\n")) if not x.startswith("(")]


def get_tags(repo_path):
    return (
        subprocess.check_output(["git", "tag", "--list"], cwd=repo_path)
        .decode("utf-8")
        .strip()
        .split("\n")
    )


def checkout(repo_path, tag):
    return subprocess.check_call(["git", "checkout", tag, "-q"], cwd=repo_path)


def tag(repo_path, tag):
    return subprocess.check_call(["git", "tag", tag], cwd=repo_path)


def branch(repo_path, tag):
    print(tag, known_branches)
    if tag in known_branches:
        return subprocess.check_call(["git", "checkout", tag], cwd=repo_path)
    else:
        return subprocess.check_call(["git", "checkout", "-b", tag], cwd=repo_path)


def add_all(repo_path):
    return subprocess.check_call(["git", "add", "--all"], cwd=repo_path)


def rsync(source, target):
    # print("rsync", source.name)
    subprocess.check_call(
        [
            "rsync",
            str(source) + "/",
            str(target),
            "--exclude=.git",
            "--exclude=final_done",
            "--delete",
            "-r",
        ]
    )


def reset(repo_path):
    subprocess.check_call(["git", "reset", "--hard", "-q"], cwd=repo_path)


def changed(repo_path):
    s = subprocess.check_output(["git", "status", "-s"], cwd=repo_path).decode("utf-8")
    # print("changed", repr(s))
    if "nothing to commit" in s:
        return False
    return s != ""


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
    subprocess.check_call(["git", "tag", "initial"], cwd=repo_path)

known_tags = [x for x in get_tags(repo_path) if starts_with_date(x)]
known_branches = sorted([x for x in get_branches(repo_path) if starts_with_date(x)])

for d in sorted(input_path.glob("*")):
    if (
        d.is_dir()
        and starts_with_date(d.name)
        and len(d.name) == 10
        and (d / "flake" / "final_done").exists()
    ):
        print(d)
        matching_tags = [x for x in known_tags if x.startswith(d.name)]
        if matching_tags:
            latest = max(matching_tags)
            next = str(int(latest[latest.rfind("_") + 1 :]) + 1)
        else:
            latest = "initial"
            # if len(known_tags) > 1:
            #     smaller = [x for x in known_tags if x[:10] < d.name]
            #     if smaller:
            #         latest = max(smaller)
            #     else:
            #         latest = "main"
            # else:
            #     latest = "main"
            next = 1
        full_next = d.name + "_" + str(next)
        print("checkout", latest)
        reset(repo_path)
        checkout(repo_path, latest)
        branch(repo_path, d.name)
        reset(repo_path)

        rsync(d / "flake", repo_path)
        add_all(repo_path)
        if changed(repo_path):
            print("switching to", full_next)
            info = json.loads((d / "flake/header.json").read_text())
            msg = f"Bioconductor: {info['Bioconductor']}, {info['archive_date']}"
            if info["is_release_date"]:
                msg += "(release date)"
            git_commit(repo_path, msg)
            tag(repo_path, full_next)
            if info["is_release_date"]:
                tag(repo_path, info["Bioconductor"] + "_" + str(next))
        else:
            print("not changed")
