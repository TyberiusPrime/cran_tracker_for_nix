import pypipegraph2 as ppg2
import sys
import collections
import shutil
import re
import pprint
import json
import datetime
from pathlib import Path
import subprocess
import networkx
from networkx.algorithms.dag import descendants
from loguru import logger
from .bioconductor_track import BioConductorTrack
from .cran_track import CranTrack
from .r_track import RTracker
from .common import store_path, write_json, format_date, flake_source_path, temp_path
from . import bioconductor_track, bioconductor_overrides


class REcosystem:
    """Combine CranTrack and BioConductorTrack into
    one ecosystem, and dump it."""

    def __init__(self, filter_to_releases=None):
        self.bc = BioConductorTrack()
        self.r_track = RTracker()
        self.filter_to_releases = filter_to_releases
        self._sha_cache = {}
        self._url_cache = {}

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

        print("using archive date", archive_date)
        bioc_version = self.bc.date_to_version(archive_date)
        ct = CranTrack()
        ct.snapshot_dates = [snapshot_date]
        print("using bioc", bioc_version)
        # r_version = self.bc.get_R_version_including_minor(
        # bioc_version, archive_date, self.r_track
        # )

        bioc_release = self.bc.get_release(bioc_version)
        flake_info = bioc_release.get_flake_info_at_date(archive_date)
        r_version = flake_info["r_version"]
        print("r_version", r_version)
        print("using snapshot date", snapshot_date)
        header = {
            "Bioconductor": bioc_release.str_version,
            "R": r_version,
            "archive_date": archive_date.strftime("%Y-%m-%d"),
            "snapshot_date": snapshot_date.strftime("%Y-%m-%d"),
            "nixpkgs": flake_info["nixpkgs.url"],
        }
        comment = bioc_release.get_comment_at_date(archive_date)
        if comment:
            header["comment"] = comment
        cran_packages = ct.latest_packages_at_date(snapshot_date)
        bioc_experiment_packages = bioc_release.get_packages("experiment", archive_date)
        bioc_annotation_packages = bioc_release.get_packages("annotation", archive_date)
        bioc_software_packages = bioc_release.get_packages("software", archive_date)

        bl = {}
        if bioc_release.excluded_packages is not None:
            bl.update(bioc_release.excluded_packages)
        bl.update(bioc_release.get_excluded_packages_at_date(archive_date))

        parts = [
            self.map_packages(
                cran_packages,
                "cran",
                Path("data/cran/sha256/"),
                bl,
                ct.manual_url_overrides,
                {"snapshot": snapshot_date},
            ),
            self.map_packages(
                bioc_experiment_packages,
                "bioc_experiment",
                Path(f"data/bioconductor/{bioc_release.str_version}/sha256/"),
                bl,
                None,
            ),
            self.map_packages(
                bioc_annotation_packages,
                "bioc_annotation",
                Path(f"data/bioconductor/{bioc_release.str_version}/sha256/"),
                bl,
                None,
            ),
            self.map_packages(
                bioc_software_packages,
                "bioc_software",
                Path(f"data/bioconductor/{bioc_release.str_version}/sha256/"),
                bl,
                None,
            ),
        ]
        all_packages = {}
        duplicate_detection = collections.Counter()
        for p in parts:
            all_packages.update(p)
            duplicate_detection.update(p.keys())
        duplicates = {k for k, v in duplicate_detection.items() if v > 1}
        if duplicates:
            pprint.pprint(duplicates)
            raise ValueError("Duplicate packages")
        graph = networkx.DiGraph()
        for name, info in all_packages.items():
            graph.add_node(name)
            for d in info["depends"]:
                graph.add_edge(d, name)
        excluded_packages_notes = []
        to_remove = set()
        for m in bl:
            if "--" in m:  # that's the source-- excluded_packagess.
                continue
            excluded_packages_notes.append(f"excluded {m} - {bl[m]}")
            if m in graph.nodes:
                to_remove.add(m)
                for downstream in descendants(graph, m):
                    excluded_packages_notes.append(
                        f"Excluding {downstream} because of (indirect) dependency on {m}"
                    )
                    to_remove.add(downstream)
            else:
                raise ValueError(
                    f"but {m} was not in graph (superflous excluded_packages entry)"
                )
        for name in to_remove:
            graph.remove_node(name)
        were_excluded = to_remove
        to_remove = set()

        missing = set(graph.nodes).difference(all_packages)
        for m in missing:
            if m in bl:
                raise NotImplementedError("Do not expect this to happen", m)
            else:
                excluded_packages_notes.append(f"hunting for missing package {m}")
                replacement = ct.find_latest_before_disapperance(m, snapshot_date)
                if replacement is None:
                    excluded_packages_notes.append("no replacement found")
                    continue
                excluded_packages_notes.append(
                    f"replaced missing {m}  with {replacement['version']} from snapshot {replacement['snapshot']} because of CRAN availability"
                )
                all_packages.update(
                    self.map_packages(
                        {m: replacement},
                        "cran",
                        Path("data/cran/sha256/"),
                        bl,
                        None,
                    )
                )
                all_packages[m]["snapshot"] = replacement["snapshot"]

                for d in all_packages[m]["depends"]:
                    graph.add_edge(d, m)
        for name in to_remove:
            graph.remove_node(name)
            del all_packages[name]
        were_excluded.update(to_remove)
        # print("\n".join(excluded_packages_notes))

        missing = set(graph.nodes).difference(all_packages)
        if missing:
            for m in missing:
                print(m, list(graph.successors(m)), list(graph.predecessors(m)))
            raise ValueError("missing dependencies in graph", missing)

        # quick check on the letter distribution - so we can
        # decide on the sharding.
        histo = collections.Counter()
        for name in all_packages:
            histo[name[0].lower()] += 1
        print("most common package start letters", histo.most_common())

        bioc_release.patch_native_dependencies(
            graph, all_packages, were_excluded, archive_date
        )

        all_packages = {
            k: all_packages[k] for k in sorted(graph.nodes)
        }  # enforce deterministic output order
        out = {
            "header": header,
            "packages": all_packages,
        }
        self.clear_output(output_path)

        self.fill_flake(output_path, bioc_release, archive_date)

        (output_path / "generated").mkdir(exist_ok=True)
        (output_path / "excluded_packages.txt").write_text(
            "\n".join(excluded_packages_notes)
        )

        readme_text = (output_path / "README.md").read_text()
        readme_text += "# In this commit\n\n"
        for k, v in sorted(header.items()):
            readme_text += f"  * {k}: {v}\n"
        readme_text += "\n"

        # date_notes = bioconductor_overrides.extra_snapshots.get(
        # ".".join(bioc_version), {}
        # ).get(format_date(archive_date))
        # if date_notes:
        # readme_text += "# Notes on this revision:\n\n" + date_notes.strip() + "\n\n"
        (output_path / "README.md").write_text(readme_text)

        self.dump_cran_packages(
            {k: v for (k, v) in all_packages.items() if v["source"] == "cran"},
            snapshot_date,
            header,
            output_path / "generated" / "cran-packages.nix",
        )
        self.dump_bioc_packages(
            {k: v for (k, v) in all_packages.items() if v["source"] == "bioc_software"},
            bioc_version,
            header,
            output_path / "generated" / "bioc-packages.nix",
        )
        self.dump_bioc_packages(
            {
                k: v
                for (k, v) in all_packages.items()
                if v["source"] == "bioc_experiment"
            },
            bioc_version,
            header,
            output_path / "generated" / "bioc-experiment-packages.nix",
        )
        self.dump_bioc_packages(
            {
                k: v
                for (k, v) in all_packages.items()
                if v["source"] == "bioc_annotation"
            },
            bioc_version,
            header,
            output_path / "generated" / "bioc-annotation-packages.nix",
        )

        add(["."], output_path)

        self.run_nix_build(output_path)
        self.assert_r_version(output_path, r_version)

        disjoint_package_sets = self.build_disjoint_package_sets(all_packages)
        test_file = Path(temp_path / ("packages_tested" + format_date(archive_date)))
        if test_file.exists():
            offset = int(test_file.read_text())
        else:
            offset = 0
        for ii, package_set in enumerate(disjoint_package_sets):
            if ii >= offset:
                print(f"testing package set {ii+1}/{len(disjoint_package_sets)}")
                self.test_package_set_build(output_path, package_set, archive_date)
                test_file.write_text(str(ii + 1))

        test_file.unlink()

        commit(
            ["."],
            output_path,
            json.dumps(
                {
                    "bioconductor": bioc_release.str_version,
                    "R": r_version,
                    "archive_date": format_date(archive_date),
                    "snapshot_date": format_date(snapshot_date),
                    "nixpkgs": flake_info["nixpkgs.url"],
                }
            ),
        )

        # write_json(out, output_filename, True)
        return bioc_version

    def map_packages(
        self,
        package_dict,
        source,
        sha_path,
        excluded_packages,
        manual_url_overrides,
        defaults={},
    ):
        res = {}

        for name, v in package_dict.items():
            # we filter the source-- right here, since there will be another
            # package of the same name., the other excluded_packages is filtered upstream
            if (source + "--" + name) in excluded_packages:
                print(f"excluded from {source}: {name} (presumably present in others)")
                continue
            res[name] = {
                "name": name,
                "version": v["version"],
                "depends": sorted(set(v["imports"] + v["depends"] + v["linking_to"])),
                "suggests": sorted(set(v["suggests"])),
                "sha256": self.get_sha(sha_path / f"{name}_{v['version']}.sha256"),
                "url": self.get_url(sha_path / f"{name}_{v['version']}.url"),
                "source": source,
                "needs_compilation": v["needs_compilation"],
            }
            if "patches" in v:
                res[name]["patches"] = v["patches"]
            res[name].update(defaults)
            if manual_url_overrides and (name, v["version"]) in manual_url_overrides:
                res[name]["url"] = manual_url_overrides[(name, v["version"])]
                # del all_packages[name]["source"]
        return res

    def clear_output(self, output_path):
        for fn in output_path.glob("*"):
            if fn.name != ".git":
                if fn.is_symlink():
                    fn.unlink()
                elif fn.is_dir():
                    shutil.rmtree(fn)
                else:
                    fn.unlink()

    def fill_flake(self, output_path, bioc_release, archive_date):
        source_path = flake_source_path / "default"
        if not source_path.exists():
            raise ValueError("No flake source found")
        shutil.copytree(source_path, output_path, dirs_exist_ok=True)
        input = (output_path / "flake.nix").read_text()
        flake_info = bioc_release.get_flake_info_at_date(archive_date)
        print(flake_info)
        patches = flake_info.get("patches", [])
        patches = " ".join(patches)
        output = (
            input.replace(
                "github:TyberiusPrime/nixpkgs?rev=f0d6591d9c219254ff2ecd2aa4e5d22459b8cd1c",
                flake_info["nixpkgs.url"],
            )
            .replace("3.1.3", flake_info["r_version"])
            .replace(
                "04kk6wd55bi0f0qsp98ckjxh95q2990vkgq4j83kiajvjciq7s87",
                flake_info.get(
                    "r_tar_gz_sha256",
                    "0000000000000000000000000000000000000000000000000000",
                ),
            )
            .replace(
                "patches = []; # R_patches-generated",
                "patches = [" + patches + "]; # R_patches-generated",
            )
        )
        (output_path / "flake.nix").write_text(output)

    def dump_cran_packages(self, cran_packages, snapshot_date, header, output_path):
        def extract_snapshot_from_url(name, version, url):
            matches = re.findall(
                r"(\d{4}-\d{2}-\d{2})/src/contrib/"
                + name
                + "_"
                + version
                + r"\.tar\.gz",
                url,
            )
            if matches:
                return matches[0]
            else:
                return None

        # snapshot_date = format_date(snapshot_date)
        with open(output_path, "w") as op:
            op.write("# generated by CranTrackForNix\n")
            op.write(
                "\n".join(
                    ("# " + x for x in json.dumps(header, indent=2).strip().split("\n"))
                )
            )
            op.write("\n{ self, derive, pkgs, breakpointHook }:\n")
            # we use the most common snapshot to save some byte here
            snapshot_counts = collections.Counter()
            snapshot_counts.update(
                (
                    extract_snapshot_from_url(
                        info["name"], info["version"], info["url"]
                    )
                    for info in cran_packages.values()
                )
            )
            if None in snapshot_counts:
                del snapshot_counts[None]
            most_common_snapshot = snapshot_counts.most_common(1)[0][0]
            op.write(
                f'let derive2 = derive {{ snapshot = "{most_common_snapshot}"; }};\n'
            )
            op.write("in with self; {\n")
            for name, info in sorted(cran_packages.items()):
                # if not ("snapshot" in info):
                # raise KeyError("missing snapshot", name, info)  # will have rissen in count
                if not isinstance(info["snapshot"], datetime.date):
                    raise ValueError(type(info["snapshot"]), type(snapshot_date), name)
                safe_name = name.replace(".", "_")
                # we want to use the same url we retrieved the sha256 from.
                # for cran at one time apparently rebuild some packages
                # same content, different build date -> different tar.gz
                # so we can't fall back to Archive.
                if ("/" + most_common_snapshot + "/") in info["url"]:
                    op.write(f" {safe_name} = derive2 ")
                else:
                    matches = extract_snapshot_from_url(
                        info["name"], info["version"], info["url"]
                    )
                    if matches:
                        op.write(f' {safe_name} = derive {{snapshot = "{matches}";}}')
                    else:
                        op.write(f' {safe_name} = derive {{url = "{info["url"]};}}' "")

                self._write_package(name, info, op)
            op.write("}\n")

    def _write_package(self, name, info, op):
        args = [
            f'name="{name}"',
            f'version="{info["version"]}"',
            f'sha256="{info["sha256"]}"',
            "depends=[ " + " ".join(info["depends"]).replace(".", "_") + "]",
        ]

        for (key, arg) in [
            ("native_build_inputs", "nativeBuildInputs"),
            ("build_inputs", "buildInputs"),
            ("patches", "patches"),
        ]:
            if key in info:
                args.append(f"{arg} = [" + " ".join(sorted(info[key])) + "]")
        if info.get("needs_x", False):
            args.append(f"requireX=true")
        if info.get("skip_check", False):
            args.append(f"doCheck=false")
        op.write("{ " + " ".join((x + ";" for x in args)) + "};\n")

    def dump_bioc_packages(self, packages, bioc_version, header, output_path):
        bioc_version = ".".join(bioc_version)
        with open(output_path, "w") as op:
            op.write("# generated by CranTrackForNix\n")
            op.write(
                "\n".join(
                    ("# " + x for x in json.dumps(header, indent=2).strip().split("\n"))
                )
            )
            op.write("\n{ self, derive, pkgs, breakpointHook }:\n")
            op.write(f'let derive2 = derive {{ biocVersion = "{bioc_version}"; }};\n')
            op.write("in with self; {\n")
            for name, info in sorted(packages.items()):
                safe_name = name.replace(".", "_")
                op.write(f" {safe_name} = derive2")
                self._write_package(name, info, op)
            op.write("}\n")

    def run_nix_build(self, output_path):
        subprocess.check_call(
            [
                "nix",
                "build",
                "--show-trace",
                "--verbose",
                "--max-jobs",
                "auto",
                "--cores",
                "4",  # it's pretty bad at using the cores either way, so let's oversubscribe ab it...
                "--keep-going",
            ],
            cwd=output_path,
        )

    def assert_r_version(self, output_path, r_version):
        raw = subprocess.check_output(
            [output_path / "result" / "bin" / "R", "-e", "sessionInfo()"],
            env={"LC_ALL": "C"},
        ).decode("utf-8")
        actual = re.findall("R version ([^ ]+)", raw)[0]
        assert r_version == actual

    def test_package_set_build(self, output_path, packages, archive_date):
        temp_flake_path = temp_path / "test_flake" / format_date(archive_date)
        if temp_flake_path.exists():
            shutil.rmtree(temp_flake_path)
        temp_flake_path.mkdir()
        subprocess.check_call(["git", "init", "."], cwd=temp_flake_path)
        path = str(
            (
                Path(__file__).parent.parent.parent.parent / "r_ecosystem_track"
            ).absolute()
        )
        (temp_flake_path / "flake.nix").write_text(
            """
{
  description = "test flake to check package build";

  inputs = rec {
    r_flake.url = "path:"""
            + path
            + """";

  };

  outputs = { self, r_flake}: {
    defaultPackage.x86_64-linux = with r_flake;
      rWrapper.x86_64-linux.override {
        packages = with rPackages.x86_64-linux; [ %PACKAGES% ];
      };
  };
}
""".replace(
                "%PACKAGES%", " ".join(packages).replace(".", "_")
            )
        )
        subprocess.check_call(["git", "add", "flake.nix"], cwd=temp_flake_path)
        subprocess.check_call(
            ["nix", "build", "-j", "auto", "--cores", "2", "--verbose", "--keep-going"],
            cwd=temp_flake_path,
        )

    def get_sha(self, fn):
        """Get the sha256 of a package if we haven't loaded it yet"""
        if not fn in self._sha_cache:
            self._sha_cache[fn] = Path(fn).read_text()
        return self._sha_cache[fn]

    def get_url(self, fn):
        fn = Path(fn)
        if not fn in self._url_cache:
            if fn.exists():
                self._url_cache[fn] = fn.read_text()
            else:
                self._url_cache[fn] = None
        return self._url_cache[fn]

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
            dates = bioc_release.get_cran_dates(
                self.ct
            )  # that's a set of (archive_date, snapshot_date)
            start = bioc_release.release_info.start_date
            end = bioc_release.release_info.end_date
            invalid_dates = [x[0] for x in dates if not (start <= x[0] < end)]
            if invalid_dates:
                raise ValueError(
                    f"Bioconducter {bioc_release.version} cran dates outside of start/end date ({bioc_release.release_info}): {invalid_dates}"
                )
            # print("bioc_release.version", bioc_release.version, dates)
            res.update(dates)
        return sorted(res)

    def build_disjoint_package_sets(self, all_packages):
        """Built a list of package sets that are
        not interconnected - discrete subcomponents of the dependency graph
        in essence"""

        g = networkx.Graph()  # technically a DAG, but this should do
        for pkg_name, info in all_packages.items():
            for req_name in info["depends"]:
                g.add_edge(req_name, pkg_name)
        return sorted(networkx.connected_components(g), key=len)


@ppg2.util.pretty_log_errors
def main():
    """Collect the ecosystem information (in data/),
    and dump it, per bioconductor-change-day
    to a git repo in ./r_ecosystem_track/
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

    already_dumped = [
        fn.name for fn in dump_track_dir.glob("*") if not fn.name.startswith("updated")
    ]
    if len(sys.argv) <= 1:
        for archive_date, snapshot_date in cran_dates:
            if not format_date(archive_date) in already_dumped:
                print("dumping", archive_date)
                bc_version = r.dump(
                    archive_date, snapshot_date, Path("../r_ecosystem_track")
                )
                Path(dump_track_dir / (format_date(archive_date))).write_text("")

        commit(
            add_paths=["dumped", "data"],
            message="autocommit data update & data after update",
        )
    else:
        query_date = sys.argv[1]
        output_path = Path("../r_ecosystem_track_" + query_date)
        for archive_date, snapshot_date in cran_dates:
            if archive_date == parse_date(query_date):
                output_path.mkdir(exist_ok=True)
                bc_version = r.dump(archive_date, snapshot_date, Path(output_path))
                break
        else:
            raise KeyError("Not found")


#    r.dump(datetime.date(year=2018, month=1, day=15), Path("./r_ecosystem_track"))


def add(add, cwd):
    subprocess.check_call(["git", "add"] + add, cwd=cwd)


def commit(add_paths=["data"], cwd=store_path.parent, message="autocommit"):
    """commit a github repository"""
    add(add_paths, cwd)
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
