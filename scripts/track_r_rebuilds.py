from pathlib import Path
import os
import pandas as pd
import collections


def find_packages(date_str):
    res = collections.defaultdict(list)
    f = Path("r_ecosystem_tracks") / date_str
    if not (f / "flake" / "final_done").exists():
        raise KeyError()
    bd = list((f / "builds").glob("*"))[0]
    seen = set()
    for fn in bd.glob("*"):
        fp = fn / "flake" / "result" / "lib" / "R" / "library"
        for fn in fp.glob("*"):
            if fn.is_symlink():
                target = os.readlink(fn)
                target = target[11:]
                target = target[: target.find("/")]
                if target in seen:  # might be referenced in multiple subdirs
                    continue
                seen.add(target)
                version = target[target.rfind("-") :]
                name = target[target.find("-r-") + 3 : target.rfind("-")]
                hash = target[: target.find("-")]
                res["name"].append(name)
                res["hash"].append(hash)
                res["version"].append(version)
    return pd.DataFrame(res)


def delta(a, b):
    a = find_packages(a)
    b = find_packages(b)

    ax = a.set_index("name")
    bx = b.set_index("name")
    combo = pd.concat({"a": ax, "b": bx}, axis=1)
    # combo.columns = ['a','b']
    gained = pd.isnull(combo[("b", "hash")]).sum()  # had no version in b
    lost = pd.isnull(combo[("a", "hash")]).sum()  # had no version in b
    # combo = combo[~pd.isnull(combo).any(axis=1)]
    ver_changed = (
        (combo["a", "version"] != combo["b", "version"])
        & (~pd.isnull(combo).any(axis=1))
    ).sum()
    hash_changed = (
        (combo["a", "hash"] != combo["b", "hash"])
        & (combo["a", "version"] == combo["b", "version"])
        & (~pd.isnull(combo).any(axis=1))
    ).sum()
    return {
        "gained": gained,
        "lost": lost,
        "version_change": ver_changed,
        "hash_changed": hash_changed,
        "total": len(combo),
        "larger_set": max(len(a), len(b)),
    }


if False:
    last = None
    col = []
    for d in sorted(Path("r_ecosystem_tracks").glob("*")):
        if d.is_dir() and d.name >= "2021-10-27":
            print(d)
            if last is not None:
                c = delta(last, d.name)
                c["date"] = d.name
                col.append(c)
            last = d.name

    print(pd.DataFrame(col))

a = find_packages("2021-11-09").set_index("name")
b = find_packages("2021-11-08").set_index("name")

x = pd.concat({"a": a, "b": b}, axis=1)
print(x[(x["a", "version"] == x["b", "version"]) & (x["a", "hash"] != x["b", "hash"])])
