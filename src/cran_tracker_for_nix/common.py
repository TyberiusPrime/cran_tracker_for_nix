import re
import hashlib
import json
import requests
import gzip
import pypipegraph2 as ppg2
from pathlib import Path

cache_path = Path("~/.cache/cran_track_for_nix").expanduser()
store_path = Path(__file__).absolute().parent.parent.parent / "data"

build_into_r = {
    # built in
    "base",
    "boot",
    "compiler",
    "datasets",
    "grDevices",
    "graphics",
    "grid",
    "methods",
    "parallel",
    "R",
    "splines",
    "stats",
    "stats4",
    "tcltk",
    "tools",
    "utils",
    # 'recommended', and not on CRAN
    "nlme",
    'BiocInstaller', # that's the bioconductor install package, which is neither in CRAN, nor in bioconductor's package ilsts
    # "class",
    # "cluster",
    # "codetools",
    # "compiler",
    # "datasets",
    # "foreign",
    # "graphics",
    # "grDevices",
    # "grid",
    # "KernSmooth",
    # "lattice",
    # "MASS",
    # "Matrix",
    # "methods",
    # "mgcv",
    # "nlme",
    # "nnet",
    # "parallel",
    # "rpart",
    # "spatial",
    # "splines",
    # "stats",
    # "stats4",
    # "survival",
    # "tcltk",
    # "tools",
    # "utils",
}


def version_to_tuple(v):
    return tuple([str(int(y)) for y in re.split("[.-]", v)])


def version_to_tuple_int(v):
    return tuple([int(y) for y in re.split("[.-]", v)])


def handle_duplicate_packages_entry(a, b):
    """CRAN package lists are not well kept.
    They contain duplicate entries.
    We shall default to the one with the largest version.
    If identical, the one with the largest imports/depends set
    And if that's identical, to the earlier one in the file (b)

    """
    va = version_to_tuple_int(a["Version"])
    vb = version_to_tuple_int(b["Version"])
    if va > vb:
        return a
    elif va < vb:
        return b
    else:
        depends_a = (
            len(set(a.get("Depends", [])))
            + len(set(a.get("Imports", [])))
            + len(set(a.get("LinkingTo", [])))
        )
        depends_b = (
            len(set(b.get("Depends", [])))
            + len(set(b.get("Imports", [])))
            + len(set(b.get("LinkingTo", [])))
        )
        if depends_a > depends_b:
            return a
        else:
            return b


class RPackageParser:
    @staticmethod
    def get_dependencies():
        return [
            ppg2.FunctionInvariant(RPackageParser.parse_from_str),
            ppg2.ParameterInvariant("R_builtins", build_into_r),
        ]

    def parse_from_str(self, raw):
        pkgs = {}
        errors = []
        for p in self.parse(raw):
            if p["Package"] in build_into_r:
                continue
            # p["name"] = p["Package"]
            out = {}
            for x in ("Depends", "Imports", "LinkingTo"):  # "Suggests",
                if p[x]:
                    out[x.lower()] = list(set(p[x]) - build_into_r)
            version = p["Version"] if p["Version"] else ""
            out["Version"] = version
            out["NeedsCompilation"] = p.get("NeedsCompilation", "no") == "yes"
            # p["url"] = ( self.base_url + "src/contrib/" + p["name"] + "_" + p["version"] + ".tar.gz")
            if p["Package"] in pkgs:
                replacement = handle_duplicate_packages_entry(out, pkgs[p["Package"]])
                if replacement is None:
                    errors.append((p, pkgs[p["Package"]]))
                    continue
                else:
                    out = replacement  # that was already treated
            pkgs[p["Package"]] = out
        if errors:
            print("Number of duplicate, unhandled packages", len(errors))
            for p1, p2 in errors:
                import pprint

                print(p1["Package"])
                pprint.pprint(p1)
                pprint.pprint(p2)
                print("")
            raise ValueError("Duplicate packages within repository!")
        pkgs = {(name, p["Version"]): p for (name, p) in pkgs.items()}
        return pkgs

    def parse(self, raw):
        lines = raw.split("\n")
        result = []
        current = {}
        for line in lines:
            m = re.match("([A-Za-z0-9_]+):", line)
            if m:
                key = m.groups()[0]
                value = line[line.find(":") + 2 :].strip()
                if key == "Package":
                    if current:
                        result.append(current)
                        current = {}
                if key in current:
                    raise ValueError(key)
                current[key] = value
            elif line.strip():
                current[key] += line.strip()

        if current:
            result.append(current)
        for current in result:
            for k in ["Depends", "Imports", "Suggests", "LinkingTo"]:
                if k in current:
                    current[k] = re.split(", ?", current[k].strip())
                    current[k] = set(
                        [re.findall("^[^ ()]+", x)[0] for x in current[k] if x]
                    )
                else:
                    current[k] = set()
        return result


def download_packages(url, output_filename, temp=False):
    def download(outfilename, url=url):
        r = requests.get(url)
        packages = RPackageParser().parse_from_str(
            gzip.decompress(r.content).decode("utf-8", errors="replace")
        )
        output = [
            (
                name,
                ver,
                sorted(info.get("depends", [])),
                sorted(info.get("imports", [])),
                info["NeedsCompilation"],
            )
            for ((name, ver), info) in sorted(packages.items())
        ]
        write_json(output, output_filename)

    if temp:
        jc = ppg2.TempFileGeneratingJob
    else:
        jc = ppg2.FileGeneratingJob

    return jc(
        output_filename,
        download,
        depend_on_function=False,
    ).depends_on(RPackageParser.get_dependencies())


def read_packages_and_versions_from_json(fn):
    for entry in read_json(fn):
        yield (entry[0], entry[1])


def read_json(fn):
    return json.loads(gzip.GzipFile(fn, "rb").read().decode("utf-8"))


def write_json(data, fn, do_indent=False):
    # you absolutely need to fix the mtime, or your gzip files will always be different
    gzip.GzipFile(fn, "wb", mtime=0).write(
        json.dumps(data, indent=2 if do_indent else None).encode("utf-8")
    )


def hash_url(url, path, retries=1):
    try:
        with requests.get(url, stream=True) as r:
            if r.status_code != 200:
                raise ValueError("non 200 return", r.status_code)
            h = hashlib.sha256()
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                h.update(chunk)
    except requests.ConnectionError as e:
        if "timed out" in str(e) and retries:
            return hash_url(url, path, retries - 1)
        else:
            raise
    path.write_text(h.hexdigest())


def hash_job(url, path):
    def do(
        output_filename,
    ):
        hash_url(url, output_filename)

    ppg2.FileGeneratingJob(
        path,
        do,
        depend_on_function=False,
    )


if __name__ == "__main__":
    import gzip

    f = gzip.GzipFile("2020-06-30.gz")
    p = RPackageParser()
    r = p.parse_from_str(f.read().decode("utf-8"))
    #x = set()
    #for v in r.values():
        #x.add(v["NeedsCompilation"])
    for (k,x),v in r.items():
        if k == 'svglite':
            print(x,v)
    #print(x)
