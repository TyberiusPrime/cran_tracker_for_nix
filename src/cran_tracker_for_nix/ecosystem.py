import pypipegraph2 as ppg2
import pprint
import json
import datetime
from pathlib import Path
import subprocess
from .bioconductor_track import BioConductorTrack
from .cran_track import CranTrack
from .r_track import RTracker
from .common import store_path, write_json, format_date


class REcosystem:
    """Combine CranTrack and BioConductorTrack into
    one ecosystem, and dump it."""

    def __init__(self, filter_to_releases=None):
        self.bc = BioConductorTrack()
        self.r_track = RTracker()
        self.filter_to_releases = filter_to_releases
        self._sha_cache = {}

    def update(self):
        """query everything we don't have yet."""
        try:
            ppg2.new(report_done_filter=5)
            bc_jobs = []
            bcvs = {}
            releases = list(self.bc.iter_releases())
            if self.filter_to_releases:
                releases = [
                    x for x in releases if x.str_version in self.filter_to_releases
                ][:1]
                if not releases:
                    raise ValueError("filtered all")
            for bcv in releases:
                bcvs[bcv.version] = bcv
                bc_jobs.append(bcv.update())
            self.bcvs = bcvs

            self.ct = CranTrack()

            def gen_cran():
                all_the_dates = set()  # snapshot dates that is
                for bcv in bcvs.values():
                    all_the_dates.update(
                        [x[1].strftime("%Y-%m-%d") for x in bcv.get_cran_dates(self.ct)]
                    )
                self.ct.update(sorted(all_the_dates))

            ppg2.JobGeneratingJob("CRAN_gen", gen_cran).depends_on(
                bc_jobs, self.ct.fetch_snapshots()
            )
            self.r_track.update()
            ppg2.run()

        finally:
            commit()

    def dump(self, archive_date, snapshot_date, output_path):
        """Dump a json with all the info we need to build packages from a given date"""

        bioc_version = self.bc.date_to_version(archive_date)
        ct = CranTrack()
        ct.snapshot_dates = [snapshot_date]
        print("using bioc", bioc_version)
        r_version = self.bc.get_R_version_including_minor(
            bioc_version, archive_date, self.r_track
        )
        print("r_version", r_version)
        nixpkgs_info = self.r_track.decide_nixpkgs_rev_for_R_version(
            r_version, archive_date
        )
        print("using nixpkgs", nixpkgs_info["commit"], "dated", nixpkgs_info["date"])
        bioc_release = self.bc.get_release(bioc_version)
        print("using archive date", archive_date)
        print("using snapshot date", snapshot_date)
        header = {
            "R_version": r_version,
            "archive_date": archive_date.strftime("%Y-%m-%d"),
            "snapshot_date": snapshot_date.strftime("%Y-%m-%d"),
        }
        cran_packages = ct.latest_packages_at_date(snapshot_date)
        bioc_experiment_packages = bioc_release.get_packages("experiment", archive_date)
        bioc_annotation_packages = bioc_release.get_packages("annotation", archive_date)
        bioc_software_packages = bioc_release.get_packages("software", archive_date)

        bl = set()
        if bioc_release.blacklist is not None:
            bl.update(bioc_release.blacklist)
        bl.update(bioc_release.get_blacklist_at_date(archive_date))

        all_packages = {}
        duplicates = []  # for when there are multiple, we want to know at once
        for name, v in cran_packages.items():
            if name in bl or ("cran--" + name) in bl:
                print("blacklisted from cran", name)
                continue
            if name in all_packages:
                duplicates.append((name, {}, "cran", v))
            all_packages[name] = {
                "name": name,
                "version": v["version"],
                "depends": sorted(set(v["imports"] + v["depends"] + v["linking_to"])),
                "sha256": self.get_sha(
                    Path(f"data/cran/sha256/{name}_{v['version']}.sha256")
                ),
                "snapshot": snapshot_date,
                "source": "cran",
            }
            if v["needs_compilation"]:
                all_packages[name]["needs_compilation"] = True
            if (name, v["version"]) in ct.manual_url_overwrites:
                all_packages[name]["url"] = ct.manual_url_overwrites[
                    (name, v["version"])
                ]
                del all_packages[name]["source"]
        for name, v in bioc_experiment_packages.items():
            if name in bl or ("experiment--" + name) in bl:
                print("blacklisted from experiment", name)
                continue
            if name in all_packages:
                duplicates.append((name, all_packages[name], "bioc-experiment", v))
            all_packages[name] = {
                "name": name,
                "version": v["version"],
                "depends": sorted(set(v["imports"] + v["depends"] + v["linking_to"])),
                "sha256": self.get_sha(
                    Path(
                        f"data/bioconductor/{bioc_release.str_version}/sha256/{name}_{v['version']}.sha256"
                    )
                ),
                "source": "bioc-experiment",
            }
        for name, v in bioc_annotation_packages.items():
            if name in bl or ("annotation--" + name) in bl:
                print("blacklisted from annotation", name)
                continue
            if name in all_packages:
                duplicates.append((name, all_packages[name], "bioc-annotation", v))
            all_packages[name] = {
                "name": name,
                "version": v["version"],
                "depends": sorted(set(v["imports"] + v["depends"] + v["linking_to"])),
                "sha256": self.get_sha(
                    Path(
                        f"data/bioconductor/{bioc_release.str_version}/sha256/{name}_{v['version']}.sha256"
                    )
                ),
                "source": "bioc-annotation",
            }
        for name, v in bioc_software_packages.items():
            if name in bl or ("bioc--" + name) in bl:
                print("blacklisted from bioc", name)
                continue
            if name in all_packages:
                duplicates.append((name, all_packages[name], "bioc-software", v))
            all_packages[name] = {
                "name": name,
                "version": v["version"],
                "depends": sorted(set(v["imports"] + v["depends"] + v["linking_to"])),
                "sha256": self.get_sha(
                    Path(
                        f"data/bioconductor/{bioc_release.str_version}/sha256/{name}_{v['version']}.sha256"
                    )
                ),
                "source": "bioc-software",
            }
        if duplicates:
            pprint.pprint(duplicates)
            raise ValueError("Duplicate packages")
        missing = self.verify_package_tree(all_packages, False)
        for m in missing:
            print("hunting for missing package", m)
            replacement = ct.find_latest_before_disapperance(m, snapshot_date)
            if replacement is None:
                print("no replacement found")
                continue
            print("replacement", replacement["version"], replacement["snapshot"])
            all_packages[m] = {
                "name": m,
                "version": replacement["version"],
                "depends": sorted(set(replacement["imports"] + replacement["depends"])),
                "sha256": Path(
                    f"data/cran/sha256/{m}_{replacement['version']}.sha256"
                ).read_text(),
                "snapshot": replacement["snapshot"],
            }
            cran_packages[m] = all_packages[m]
        if self.verify_package_tree(all_packages, True):
            raise ValueError("missing dependencies")

        all_packages = {
            k: all_packages[k] for k in sorted(all_packages)
        }  # enforce deterministic output order
        out = {
            "header": header,
            "packages": all_packages,
        }
        self.dump_cran_packages(
            {k: v for (k, v) in all_packages.items() if k in cran_packages and not ('cran--' + k) in bl},
            snapshot_date,
            header,
            output_path / "generated" / "cran-packages.nix",
        )
        self.dump_bioc_packages(
            {k: v for (k, v) in all_packages.items() if k in bioc_software_packages and not ('bioc--' + k) in bl},
            bioc_version,
            header,
            output_path / "generated" / "bioc-packages.nix",
        )
        self.dump_bioc_packages(
            {k: v for (k, v) in all_packages.items() if k in bioc_experiment_packages and not ('experiment--' + k) in bl},
            bioc_version,
            header,
            output_path / "generated" / "bioc-experiment-packages.nix",
        )
        self.dump_bioc_packages(
            {k: v for (k, v) in all_packages.items() if k in bioc_annotation_packages and not ('annotation--' + k) in bl},
            bioc_version,
            header,
            output_path / "generated" / "bioc-annotation-packages.nix",
        )

        self.update_flake_lock(nixpkgs_info, output_path / "flake.lock")

        commit(
            ["."],
            output_path,
            json.dumps(
                {
                    "bioconductor": bioc_version,
                    "r": r_version,
                    "archive_date": archive_date,
                    "nixpkgs": nixpkgs_info["commit"],
                }
            ),
        )

        # write_json(out, output_filename, True)
        return bioc_version

    def dump_cran_packages(self, cran_packages, snapshot_date, header, output_path):
        # snapshot_date = format_date(snapshot_date)
        with open(output_path, "w") as op:
            op.write("# generated by CranTrackForNix\n")
            op.write(
                "\n".join(
                    ("# " + x for x in json.dumps(header, indent=2).strip().split("\n"))
                )
            )
            op.write("\n{ self, derive }:\n")
            op.write(f'let derive2 = derive {{ snapshot = "{snapshot_date}"; }};\n')
            op.write("in with self; {\n")
            for name, info in sorted(cran_packages.items()):
                if not ('snapshot' in info):
                    raise KeyError("missing snapshot", name, info)
                if not isinstance(info["snapshot"], datetime.date):
                    raise ValueError(type(info["snapshot"]), type(snapshot_date), name)
                safe_name = name.replace(".", "_")
                if info["snapshot"] == snapshot_date:
                    op.write(f" {safe_name} = derive2")
                else:
                    op.write(
                        f' {safe_name} = derive {{snapshot = "{info["snapshot"]}";}}'
                    )
                op.write(
                    f' {{ name="{name}"; version="{info["version"]}";'
                    + f' sha256="{info["sha256"]}"; depends=[{" ".join(info["depends"])}];}};\n'
                )
            op.write("}\n")

    def dump_bioc_packages(self, packages, bioc_version, header, output_path):
        with open(output_path, "w") as op:
            op.write("# generated by CranTrackForNix\n")
            op.write(
                "\n".join(
                    ("# " + x for x in json.dumps(header, indent=2).strip().split("\n"))
                )
            )
            op.write("\n{ self, derive }:\n")
            op.write(f'let derive2 = derive {{ biocVersion = "{bioc_version}"; }};\n')
            op.write("in with self; {\n")
            for name, info in sorted(packages.items()):
                safe_name = name.replace(".", "_")
                op.write(
                    f" {safe_name} = derive2"
                    f' {{ name="{name}"; version="{info["version"]}";'
                    + f' sha256="{info["sha256"]}"; depends=[{" ".join(info["depends"])}];}};\n'
                )
            op.write("}\n")

    def update_flake_lock(self, nixpkgs_info, output_path):
        flake = json.loads(output_path.read_text())
        flake["nodes"]["nixpkgs"]["locked"]["narHash"] = nixpkgs_info["sha256"]
        flake["nodes"]["nixpkgs"]["locked"]["rev"] = nixpkgs_info["commit"]
        flake["nodes"]["nixpkgs"]["original"]["rev"] = nixpkgs_info["commit"]
        output_path.write_text(json.dumps(flake, indent=4))

    def get_sha(self, fn):
        """Get the sha256 of a package if we haven't loaded it yet"""
        if not fn in self._sha_cache:
            self._sha_cache[fn] = Path(fn).read_text()
        return self._sha_cache[fn]

    def verify_package_tree(self, packages, complain):
        """Verify that there are no missing dependencies in the package DAG"""
        ok = True
        missing = set()
        for pkg_name, info in packages.items():
            k = "depends"
            for req_name in info[k]:
                if not req_name in packages:
                    missing.add(req_name)
                    if complain:
                        print(f"{k} for {pkg_name} missing {req_name}")
        return missing

    def get_cran_dates(self):
        """Collect cran dates from our bioconductor releases.
        Those are actually tuples: bioconductor archive date, cran snapshot date
        """
        res = set()
        for bioc_release in self.bcvs.values():
            res.update(bioc_release.get_cran_dates(self.ct))
        return sorted(res)


def main():
    """Collect the ecosystem information (in data/),
    and dump it, per bioconductor-change-day
    to a git repo in ../r_ecosystem_track/
    (one commit per day).

    We keep track of what's been dumped in dumped/.
    """

    r = REcosystem()

    dump_track_dir = Path("dumped")
    dump_track_dir.mkdir(exist_ok=True)
    check_file = dump_track_dir / f"updated_{datetime.date.today():%Y-%m-%d}"
    if not check_file.exists():
        print("running update")
        r.update()
        check_file.write_text(
            "\n".join(
                [
                    f"{date[0]:%Y-%m-%d} {date[1]:%Y-%m-%d}"
                    for date in r.get_cran_dates()
                ]
            )
        )
    # we don't want to have two code paths.
    cran_dates = (x.split(" ") for x in check_file.read_text().split("\n"))
    cran_dates = [
        (
            datetime.datetime.strptime(x[0], "%Y-%m-%d").date(),
            datetime.datetime.strptime(x[1], "%Y-%m-%d").date(),
        )
        for x in cran_dates
    ]

    already_dumped = [fn.name for fn in dump_track_dir.glob("*")]
    for archive_date, snapshot_date in cran_dates:
        if not archive_date.strftime("%Y-%m-%d") in already_dumped:
            print("dumping", archive_date)
            bc_version = r.dump(
                archive_date, snapshot_date, Path("../r_ecosystem_track")
            )
            break

    # commit(add=["dumped"], message="autocommit dumped")


#    r.dump(datetime.date(year=2018, month=1, day=15), Path("../r_ecosystem_track"))


def commit(add=["data"], cwd=store_path.parent, message="autocommit"):
    """commit a github repository"""
    subprocess.check_call(["git", "add"] + add, cwd=cwd)
    p = subprocess.Popen(
        ["git", "commit", "-m", message],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
    )
    stdout, stderr = p.communicate()
    if p.returncode == 0 or b"no changes added" in stdout:
        return True
    else:
        raise ValueError("git error return", p.returncode, stdout)
