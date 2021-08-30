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
    "R",
    "base",
    "boot",
    "class",
    "cluster",
    "codetools",
    "compiler",
    "datasets",
    "foreign",
    "graphics",
    "grDevices",
    "grid",
    "KernSmooth",
    "lattice",
    "MASS",
    "Matrix",
    "methods",
    "mgcv",
    "nlme",
    "nnet",
    "parallel",
    "rpart",
    "spatial",
    "splines",
    "stats",
    "stats4",
    "survival",
    "tcltk",
    "tools",
    "utils",
}


class RPackageParser:
    @staticmethod
    def get_dependencies():
        return ppg2.FunctionInvariant(RPackageParser.parse_from_str)

    def parse_from_str(self, raw):
        pkgs = {}
        errors = []
        for p in self.parse(raw):
            # p["name"] = p["Package"]
            out = {}
            for x in ("Depends", "Imports", "LinkingTo"):  # "Suggests",
                if p[x]:
                    out[x.lower()] = list(set(p[x]) - build_into_r)
            version = p["Version"] if p["Version"] else ""
            out["NeedsCompilation"] = p.get("NeedsCompilation", "no") == "yes"
            # p["url"] = ( self.base_url + "src/contrib/" + p["name"] + "_" + p["version"] + ".tar.gz")
            if p["Package"] in pkgs:
                errors.append((p, pkgs[p["name"]]))
            else:
                pkgs[p["Package"], version] = out
        if errors:
            print("Number of duplicate, unhandled packages", len(errors))
            for p1, p2 in errors:
                import pprint

                print(p1["name"])
                pprint.pprint(p1)
                pprint.pprint(p2)
                print("")
            raise ValueError("Duplicate packages within %s repository!" % self.name)
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


def write_json(data, fn):
    # you absolutely need to fix the mtime, or your gzip files will always be different
    gzip.GzipFile(fn, "wb", mtime=0).write(json.dumps(data).encode("utf-8"))


def hash_url(url, path):
    r = requests.get(url)
    if r.status_code != 200:
        raise ValueError("non 200 return", r.status_code)

    h = hashlib.sha256(r.content).hexdigest()
    path.write_text(h)


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
