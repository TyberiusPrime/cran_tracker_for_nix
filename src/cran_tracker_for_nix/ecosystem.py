import pypipegraph2 as ppg2
import os
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
from .common import (
    store_path,
    write_json,
    format_date,
    flake_source_path,
    temp_path,
    format_nix_value,
    parse_date,
    extract_snapshot_from_url,
)
from . import bioconductor_track, bioconductor_overrides
from .bioconductor_overrides import match_override_keys


class REcosystem:
    """Combine CranTrack and BioConductorTrack into
    one ecosystem, and dump it."""

    def __init__(self, filter_to_releases=None):
        self.bc = BioConductorTrack()
        self.r_track = RTracker()
        self.filter_to_releases = filter_to_releases
        self._sha_cache = {}
        self._url_cache = {}
        self.loaded_packages = {}

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
                        [
                            x[1].strftime("%Y-%m-%d")
                            for x in bcv.get_cran_dates(self.ct, self.r_track)
                        ]
                    )
                self.ct.update(sorted(all_the_dates))

            ppg2.JobGeneratingJob("CRAN_gen", gen_cran).depends_on(
                bc_jobs, self.ct.fetch_snapshots()
            )
            self.r_track.update()
            ppg2.run()

        finally:
            commit()

    def dump(self, archive_date, snapshot_date, output_path_top_level):
        """Dump a json with all the info we need to build packages from a given date"""

        # preliminaries
        # print("using archive date", archive_date)
        bioc_version = self.bc.date_to_version(archive_date)
        ct = CranTrack()
        ct.snapshot_dates = [snapshot_date]
        r_track = RTracker()
        # print("using bioc", bioc_version)
        bioc_release = self.bc.get_release(bioc_version)
        flake_info = bioc_release.get_flake_info_at_date(archive_date, r_track)
        r_version = flake_info["r_version"]
        # print("r_version", r_version)
        # print("using snapshot date", snapshot_date)
        header = {
            "Bioconductor": bioc_release.str_version,
            "R": r_version,
            "archive_date": format_date(archive_date),
            "is_release_date": archive_date == bioc_release.release_info.start_date,
            "snapshot_date": format_date(snapshot_date),
            "nixpkgs": flake_info["nixpkgs.url"],
        }
        comment = bioc_release.get_comment_at_date(archive_date)
        if comment:
            header["comment"] = comment

        # now the jobs
        output_path = output_path_top_level / "flake"
        output_path.mkdir(exist_ok=True, parents=True)
        job_fill_flake = self.fill_flake(
            output_path, bioc_release, archive_date, r_track
        )
        job_readme = self.write_readme(output_path, header).depends_on(job_fill_flake)

        job_packages = self.load_packages(
            ct,
            bioc_release,
            archive_date,
            snapshot_date,
        )

        def dump_excluded_packages(output_filename, archive_date=archive_date):
            output_filename.write_text(
                json.dumps(
                    self.loaded_packages[archive_date]["excluded_packages_notes"],
                    indent=2,
                )
            )

        job_excluded_packages = (
            ppg2.FileGeneratingJob(
                output_path / "excluded_packages.json", dump_excluded_packages
            )
            .depends_on(job_fill_flake)
            .depends_on(job_packages)
        )

        job_cran = self.dump_cran_packages(
            archive_date,
            snapshot_date,
            header,
            output_path / "generated" / "cran-packages.nix",
        ).depends_on(job_fill_flake, job_packages)
        job_bioc_software = self.dump_bioc_packages(
            "bioc_software",
            bioc_version,
            header,
            output_path / "generated" / "bioc-packages.nix",
            archive_date,
        ).depends_on(job_fill_flake, job_packages)
        job_bioc_experiment = self.dump_bioc_packages(
            "bioc_experiment",
            bioc_version,
            header,
            output_path / "generated" / "bioc-experiment-packages.nix",
            archive_date,
        ).depends_on(job_fill_flake, job_packages)
        job_bioc_annotation = self.dump_bioc_packages(
            "bioc_annotation",
            bioc_version,
            header,
            output_path / "generated" / "bioc-annotation-packages.nix",
            archive_date,
        ).depends_on(job_fill_flake, job_packages)

        def dump_header(output_file, header=header):
            output_file.write_text(json.dumps(header, indent=2))

        job_header = ppg2.FileGeneratingJob(
            output_path / "header.json", dump_header
        ).depends_on(job_fill_flake)

        downgrades = match_override_keys(
            bioconductor_overrides.downgrades, "-", snapshot_date, release_info=False
        )

        def dump_downgrades(output_file, downgrades=downgrades):
            output_file.write_text(
                json.dumps(
                    downgrades,
                    indent=2,
                )
            )

        job_downgrades = ppg2.FileGeneratingJob(
            output_path / "downgraded_packages.json", dump_downgrades, empty_ok=True
        ).depends_on(job_fill_flake)

        input_jobs = [
            job_cran,
            job_bioc_software,
            job_bioc_annotation,
            job_bioc_experiment,
        ]

        def gen_tests():
            disjoint_package_sets = self.build_disjoint_package_sets(
                self.loaded_packages[archive_date]["all_packages"]
            )
            test_jobs = []
            for ii, package_set in enumerate(disjoint_package_sets):
                test_path = output_path_top_level / "builds" / str(ii)
                test_path.mkdir(exist_ok=True, parents=True)

                def run_test(
                    output_file,
                    package_set=package_set,
                    archive_date=archive_date,
                    test_path=test_path,
                ):
                    self.test_package_set_build(
                        Path(__file__).parent.parent.parent.parent
                        / "r_ecosystem_tracks"
                        / format_date(archive_date)
                        / "flake",
                        test_path / "flake",
                        package_set,
                    )
                    (test_path / "output").mkdir(exist_ok=True)
                    self.run_nix_build(test_path / "flake", test_path / "output")
                    if ii == 0:
                        self.assert_r_version(test_path / "flake", r_version)
                    output_file.write_text("done")

                j = (
                    ppg2.FileGeneratingJob(
                        test_path / "output/done",
                        run_test,
                        # resources=ppg2.Resources.AllCores,
                    )
                    .depends_on(input_jobs)
                    .depends_on(
                        ppg2.ParameterInvariant(
                            f"{format_date(archive_date)}_{ii}", package_set
                        )
                    )
                )
                if test_jobs:
                    j.depends_on(test_jobs[-1])  # make them run in a chain
                test_jobs.append(j)

            def mark_done(of):
                raise ValueError()
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
                of.write_text("Yes")

            ppg2.FileGeneratingJob(output_path / " done", mark_done).depends_on(
                test_jobs
            )

        if not (output_path / " done").exists():
            # no need to gen if we are done
            ppg2.JobGeneratingJob(
                "gen_test" + format_date(archive_date), gen_tests
            ).depends_on(job_packages, job_fill_flake)

        # write_json(out, output_filename, True)
        return bioc_version

    def load_packages(self, ct, bioc_release, archive_date, snapshot_date):
        excluded_packages = bioc_release.get_excluded_packages_at_date(archive_date)
        downgrades = match_override_keys(
            bioconductor_overrides.downgrades, "-", snapshot_date, release_info=False
        )

        def calc():
            # packages, blacklists, etc
            cran_packages = ct.latest_packages_at_date(snapshot_date)
            bioc_experiment_packages = bioc_release.get_packages(
                "experiment", archive_date
            )
            bioc_annotation_packages = bioc_release.get_packages(
                "annotation", archive_date
            )
            bioc_software_packages = bioc_release.get_packages("software", archive_date)

            bl = {}
            bl.update(excluded_packages)

            parts = [
                self.map_packages(
                    cran_packages,
                    "cran",
                    Path("cran_tracker_for_nix/data/cran/sha256/"),
                    bl,
                    ct.manual_url_overrides,
                ),
                self.map_packages(
                    bioc_experiment_packages,
                    "bioc_experiment",
                    Path(
                        f"cran_tracker_for_nix/data/bioconductor/{bioc_release.str_version}/sha256/"
                    ),
                    bl,
                    None,
                ),
                self.map_packages(
                    bioc_annotation_packages,
                    "bioc_annotation",
                    Path(
                        f"cran_tracker_for_nix/data/bioconductor/{bioc_release.str_version}/sha256/"
                    ),
                    bl,
                    None,
                ),
                self.map_packages(
                    bioc_software_packages,
                    "bioc_software",
                    Path(
                        f"cran_tracker_for_nix/data/bioconductor/{bioc_release.str_version}/sha256/"
                    ),
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
                raise ValueError("Duplicate packages", duplicates)
            graph = networkx.DiGraph()
            for name, info in all_packages.items():
                graph.add_node(name)
                for d in info["depends"]:
                    graph.add_edge(d, name)
            excluded_packages_notes = {}
            to_remove = set()
            # print("blacklist", bl)
            for m in bl:
                if "--" in m:  # that's the source-- excluded_packages.
                    continue
                excluded_packages_notes[m] = bl[m]
                if m in graph.nodes:
                    to_remove.add(m)
                    for downstream in descendants(graph, m):
                        excluded_packages_notes[
                            downstream
                        ] = f"(indirect) dependency on {m}"

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
                    replacement = ct.find_latest_before_disapperance(m, snapshot_date)
                    if replacement is None:
                        continue
                    downgrades[m] = replacement["version"]
                    # f"replaced missing {m}  with {replacement['version']} from snapshot {replacement['snapshot']} because of CRAN availability"
                    # )
                    all_packages.update(
                        self.map_packages(
                            {m: replacement},
                            "cran",
                            Path("cran_tracker_for_nix/data/cran/sha256/"),
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

            data = {
                "all_packages": all_packages,
                "excluded_packages_notes": excluded_packages_notes,
            }
            self.loaded_packages[archive_date] = data
            return data

        cache_path = Path("cache")
        # cache_path.mkdir(exist_ok=True)
        res = ppg2.DataLoadingJob(
            cache_path
            / (format_date(archive_date) + "_" + bioc_release.str_version + "_load"),
            calc,
            resources=ppg2.Resources.AllCores,
        )
        res.depends_on_params(
            (
                ct.manual_url_overrides,
                snapshot_date,
                excluded_packages,
                downgrades,
                bioc_release.get_build_inputs(archive_date),
            )
        )
        return res

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
            # package of the same name., the other excluded_packages is filtered by caller
            if (source + "--" + name) in excluded_packages:
                print(f"excluded from {source}: {name} (presumably present in others)")
                continue

            res[name] = {
                "name": name,
                "version": v["version"],
                "depends": sorted(set(v["imports"] + v["depends"] + v["linking_to"])),
                "suggests": sorted(set(v["suggests"])),
                "sha256": (
                    self.get_sha(sha_path / f"{name}_{v['version']}.sha256")
                    if not name in excluded_packages
                    else "00000000000000000000000000000000"
                ),
                "url": (
                    self.get_url(sha_path / f"{name}_{v['version']}.url")
                    if not name in excluded_packages
                    else ""
                ),
                "source": source,
                "needs_compilation": v["needs_compilation"],
            }
            for k in ["patches", "snapshot"]:
                if k in v:
                    res[name][k] = v[k]
            res[name].update(defaults)
            if manual_url_overrides and (name, v["version"]) in manual_url_overrides:
                res[name]["url"] = manual_url_overrides[(name, v["version"])]
                # del all_packages[name]["source"]
        return res

    def clear_output(self, output_path):
        for fn in output_path.glob("*"):
            if not fn.name in [".git", ".packages_tested.ignore"]:
                if fn.is_symlink():
                    fn.unlink()
                elif fn.is_dir():
                    shutil.rmtree(fn)
                else:
                    fn.unlink()

    def fill_flake(self, output_path, bioc_release, archive_date, r_track):
        source_path = flake_source_path / "default"
        input_files = [
            fn
            for fn in Path(source_path).glob("**/*")
            if fn.name != "README.md" and not fn.is_dir()
        ]
        output_files = [output_path / fn.relative_to(source_path) for fn in input_files]
        input_files = [fn.relative_to(Path(".").absolute()) for fn in input_files]

        def generate(output_files, r_track=r_track):
            self.clear_output(output_path)
            if not source_path.exists():
                raise ValueError("No flake source found")
            shutil.copytree(source_path, output_path, dirs_exist_ok=True)
            input = (output_path / "flake.nix").read_text()
            flake_info = bioc_release.get_flake_info_at_date(archive_date, r_track)
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
            (output_files[0]).write_text(output)
            (output_path / "generated").mkdir(exist_ok=True)
            if not (output_path / ".git").exists():  # flakes must be git repos
                subprocess.check_call(["git", "init"], cwd=output_path)
            add(["."], output_path)  # and flake.nix must be commited

        output_files = []
        res = ppg2.MultiFileGeneratingJob(
            [output_path / "flake.nix"] + output_files, generate
        )
        for fn in input_files:
            res.depends_on_file(fn)
        return res

    def write_readme(self, output_path, header):
        def gen(output_filename):
            readme_text = (flake_source_path / "default" / "README.md").read_text()
            readme_text += "# In this commit\n\n"
            for k, v in sorted(header.items()):
                readme_text += f"  * {k}: {v}\n"
            readme_text += "\n"
            output_filename.write_text(readme_text)

        return ppg2.FileGeneratingJob(output_path / "README.md", gen).depends_on(
            ppg2.ParameterInvariant(output_path / "README.md", header)
        )

    def dump_cran_packages(self, archive_date, snapshot_date, header, output_path):
        # snapshot_date = format_date(snapshot_date)
        def gen(
            output_path,
            snapshot_date=snapshot_date,
            header=header,
        ):
            cran_packages = {
                k: v
                for (k, v) in self.loaded_packages[archive_date]["all_packages"].items()
                if v["source"] == "cran"
            }

            with open(output_path, "w") as op:
                op.write("# generated by CranTrackForNix\n")
                op.write(
                    "\n".join(
                        (
                            "# " + x
                            for x in json.dumps(header, indent=2).strip().split("\n")
                        )
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
                        raise ValueError(
                            type(info["snapshot"]), type(snapshot_date), name
                        )
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
                            op.write(
                                f' {safe_name} = derive {{snapshot = "{matches}";}}'
                            )
                        else:
                            op.write(
                                f' {safe_name} = derive {{url = "{info["url"]};}}' ""
                            )

                    self._write_package(name, info, op)
                op.write("}\n")

        return ppg2.FileGeneratingJob(output_path, gen).depends_on(
            ppg2.ParameterInvariant(output_path, (archive_date, snapshot_date, header))
        )

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
        if "hooks" in info:
            args.append(f"hooks = {format_nix_value(info['hooks'])}")
        if "needs_x" in info:
            args.append(f"requireX=true")
        if "skip_check" in info:
            args.append(f"doCheck=false")
        op.write("{ " + " ".join((x + ";" for x in args)) + "};\n")

    def dump_bioc_packages(
        self, source, bioc_version, header, output_path, archive_date
    ):
        def gen(output_path, source=source, bioc_version=bioc_version, header=header):
            packages = {
                k: v
                for (k, v) in self.loaded_packages[archive_date]["all_packages"].items()
                if v["source"] == source
            }
            bioc_version = ".".join(bioc_version)
            with open(output_path, "w") as op:
                op.write("# generated by CranTrackForNix\n")
                op.write(
                    "\n".join(
                        (
                            "# " + x
                            for x in json.dumps(header, indent=2).strip().split("\n")
                        )
                    )
                )
                op.write("\n{ self, derive, pkgs, breakpointHook }:\n")
                op.write(
                    f'let derive2 = derive {{ biocVersion = "{bioc_version}"; }};\n'
                )
                op.write("in with self; {\n")
                for name, info in sorted(packages.items()):
                    safe_name = name.replace(".", "_")
                    op.write(f" {safe_name} = derive2")
                    self._write_package(name, info, op)
                op.write("}\n")

        return ppg2.FileGeneratingJob(output_path, gen).depends_on(
            ppg2.ParameterInvariant(output_path, (bioc_version, header, source))
        )

    def run_nix_build(self, flake_path, output_path, exit_on_failure=False):
        stderr_path = Path(output_path / "stderr")
        stderr_handle = open(stderr_path, "wb")
        filtered_filename = Path(output_path / "stderr_filtered")
        stderr_filtered_handle = open(filtered_filename, "wb")
        cmd = [
            "nix",
            "build",
            "--show-trace",
            "--verbose",
            "--max-jobs",
            # o"auto",
            #str(ppg2.util.CPUs()),
            '1',
            "--cores",
            "4",  # it's pretty bad at using the cores either way, so let's oversubscribe ab it...
            "--keep-going",
            #'--json'
        ]
        p = subprocess.Popen(
            cmd,
            # stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=flake_path,
        )
        for line in p.stderr:
            stderr_handle.write(line)
            stderr_handle.flush()
            # sys.stderr.buffer.write(line)
            # sys.stderr.flush()
            if (
                not b"dependencies couldn't be built" in line
                and not line.startswith(b"building")
                and not line.startswith(b"warning: unknown setting")
                and not line.startswith(b"warning: Git tree")
                and not line.startswith(b"warning: creating lock")
                and not line.startswith(b"downloading ")
                and not line.startswith(b"querying info ")
                and not line.startswith(b"copying ")
            ):
                stderr_filtered_handle.write(line)
                stderr_filtered_handle.flush()

        p.communicate()
        stderr_handle.close()
        stderr_filtered_handle.close()
        stderr = stderr_path.read_text()
        # j = json.loads(stdout.decode("utf-8"))
        # Path(output_path / "stdout_json").write_text(json.dumps(j, indent=4))
        if p.returncode != 0:
            if exit_on_failure:
                logger.error(
                    f"Nixbld failed - check logs - {filtered_filename} . return code {p.returncode}"
                )
                sys.exit(1)
            else:
                raise ValueError(
                    f"Nixbld failed - check logs - {filtered_filename} . return code {p.returncode}"
                )

    def assert_r_version(self, output_path, r_version):
        raw = subprocess.check_output(
            [output_path / "result" / "bin" / "R", "-e", "sessionInfo()"],
            env={"LC_ALL": "C"},
        ).decode("utf-8")
        actual = re.findall("R version ([^ ]+)", raw)[0]
        assert r_version == actual

    def test_package_set_build(self, input_flake_path, test_flake_path, packages):
        if test_flake_path.exists():
            shutil.rmtree(test_flake_path)
        test_flake_path.mkdir()
        subprocess.check_call(["git", "init", "."], cwd=test_flake_path)
        path = str((input_flake_path).absolute())
        (test_flake_path / "flake.nix").write_text(
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
        subprocess.check_call(["git", "add", "flake.nix"], cwd=test_flake_path)

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
                self.ct,
                self.r_track,
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

    output_toplevel = Path("r_ecosystem_tracks")
    os.chdir(Path("..").absolute())

    ppg2.new()
    if len(sys.argv) <= 1:
        count = 0
        for archive_date, snapshot_date in cran_dates:
            bc_version = r.dump(
                archive_date,
                snapshot_date,
                output_toplevel / format_date(archive_date),
            )
            count += 1
            if count > 330:
                break

        # commit(
        # add_paths=["dumped", "data"],
        # message="autocommit data update & data after update",
        # )
    else:
        query_date = sys.argv[1]
        output_toplevel = Path("r_ecosystem_tracks")
        for archive_date, snapshot_date in cran_dates:
            if archive_date == parse_date(query_date):
                bc_version = r.dump(
                    archive_date,
                    snapshot_date,
                    output_toplevel / format_date(archive_date),
                )
                break
        else:
            raise KeyError("Not found")
    ppg2.run()


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
