"""Bioconductor updates it's PACKAGES.gz when it releases point updates.

The replaced packages get moved to archive/ when that's done.
(starting with 3.6, october 2017)

So we need to download the current packages,
and synthesize the lists as of the date the archive versions were created.

Note that we filter for releases >= 3.0,
which is when microsoft started their CRAN snapshotting.
The CRAN archive goes back to 2008 (bioconductor 2.2),
but we would have to synthesize the dependencies/PACKAGES.gz
and I deemed this to be outside of our scope.

"""
from pathlib import Path
import requests
import re
import datetime
import networkx
import multiprocessing
import gzip
import json
import bisect
import yaml
import io
from typing import Tuple
import time
import random
import functools
from lazy import lazy
import pypipegraph2 as ppg2
from . import common
from .common import (
    download_packages,
    read_packages_and_versions_from_json,
    hash_job,
    read_json,
    write_json,
    version_to_tuple,
    parse_date,
    format_date,
    is_nix_literal,
    nix_literal,
)
from . import bioconductor_overrides
from .bioconductor_overrides import match_override_keys


class ReleaseInfo:
    """Just a data class"""

    def __init__(self, start_date, end_date):
        self.start_date = start_date
        self.end_date = end_date

    def __str__(self):
        return f"ReleaseInfo({self.start_date}, {self.end_date}) # {self.end_date - self.start_date}"

    def __repr__(self):
        return str(self)


class BioConductorTrack:
    """Answer questions such as what bioconductor releases are there,
    do they have an Archive (a folder where the maintainers move package_version.tar.gz
    when it's superseeded within one bioconductor release", what R version does this
    release need etc"""

    @lazy
    def config_yaml(self):
        """Retrieve the helpfully provided bioconductor metainformation"""
        cache_path = common.store_path / "bioconductor" / "config.json.gz"
        if cache_path.exists():
            date, raw = read_json(cache_path)
            if date == datetime.date.today():
                i = io.StringIO(raw)
                return yaml.safe_load(i)
        url = "https://bioconductor.org/config.yaml"
        r = requests.get(url)
        raw = r.text
        write_json([datetime.datetime.today(), raw], cache_path)
        i = io.StringIO(raw)
        return yaml.safe_load(i)

    @lazy
    def release_date_ranges(self):
        """Bioconductor releases, when were they current?"""
        y = self.config_yaml
        release_dates = y["release_dates"]
        release_dates = {
            k: datetime.datetime.strptime(v, "%m/%d/%Y").date()
            for (k, v) in release_dates.items()
        }
        release_dates = [(version_to_tuple(x[0]), x[1]) for x in release_dates.items()]
        release_dates = sorted(release_dates, key=lambda x: [int(y) for y in x[0]])
        release_dates = [
            x for x in release_dates if x[0] >= ("3", "0")
        ]  # no CRAN snapshots before
        rinfo = {}
        for cur, plusone in zip(release_dates, release_dates[1:]):
            rinfo[cur[0]] = ReleaseInfo(cur[1], plusone[1] - datetime.timedelta(days=1))
        cur = release_dates[-1]
        rinfo[cur[0]] = ReleaseInfo(cur[1], datetime.date.today())
        return rinfo

    def get_R_version(self, release):
        """Map release to R version"""
        y = self.config_yaml
        if isinstance(release, tuple):
            key = ".".join(release)
        else:
            key = release
        return y["r_ver_for_bioc_ver"][key]

    @staticmethod
    def has_archive(version):
        return version >= (3, 6)

    def get_release(self, version):
        rinfos = self.release_date_ranges
        if isinstance(version, str):
            version = version_to_tuple(version)
        return BioconductorRelease(
            version, rinfos[version], self.get_R_version(version)
        )

    def iter_releases(self):
        for version in self.release_date_ranges:
            yield self.get_release(version)

    def date_to_version(self, date):
        """Which release was current at {date}"""
        for release, rinfo in self.release_date_ranges.items():
            if rinfo.start_date <= date < rinfo.end_date:
                return release
        raise KeyError(date)


@functools.total_ordering
class BioconductorRelease:
    """Data fetcher for one bioconductor release"""

    def __init__(self, version: Tuple[str, str], release_info, major_r_version):
        self.version = version
        self.str_version = ".".join(version)
        self.release_info = release_info
        self.major_r_version = major_r_version
        self.base_urls = [
            f"https://bioconductor.org/packages/{self.str_version}/",
            # just to distribute the load (and reduce the runtime) somewhat.
            f"https://bioconductor.statistik.tu-dortmund.de/packages/{self.str_version}/",
        ]
        if self.str_version in ("3.1", "3.8"):
            self.base_url = self.base_urls[
                0
            ]  # because the mirror does not actually have these
        else:
            self.base_url = random.choice(self.base_urls)
        self.store_path = (
            (common.store_path / "bioconductor" / self.str_version)
            .absolute()
            .relative_to(Path(".").absolute())
        )
        self.store_path.mkdir(exist_ok=True, parents=True)
        self.excluded_packages = bioconductor_overrides.excluded_packages.get(
            self.str_version, None
        )  # we need these for all_packages early on.
        self.broken_packages = bioconductor_overrides.broken_packages.get(
            self.str_version, None
        )  # we need these for all_packages early on.

        self.patch_packages = bioconductor_overrides.package_patches.get(
            self.str_version, {}
        )
        for kind, entries in self.patch_packages.items():
            self.patch_packages[kind] = self._fix_patches_to_exclude_buildins(entries)

    def _fix_patches_to_exclude_buildins(self, entries):
        res = []
        for entry in entries:
            entry = entry.copy()
            entry["depends"] = [
                x for x in entry["depends"] if x not in common.build_into_r
            ]
            entry["imports"] = [
                x for x in entry["imports"] if x not in common.build_into_r
            ]
            entry["linking_to"] = [
                x for x in entry["linking_to"] if x not in common.build_into_r
            ]
            res.append(entry)
        return res

    @lazy
    def date_invariant(self):
        """A ppg invariant to redownload the packages.gz
        of the current release when ran again later
        """
        return ppg2.ParameterInvariant(
            # if the end date changes (current release...), we refetch the packages and archives
            self.store_path / "packages.json.gz",
            (self.release_info.end_date.strftime("%Y-%m-%d"),),
        )

    def __eq__(self, other):
        """Compare with other BioconductorRelease, or version tuples, or strings"""
        if isinstance(other, BioconductorRelease):
            return self == other
        elif isinstance(other, tuple) and isinstance(other[0], int):
            return self.version == tuple([str(x) for x in other])
        elif isinstance(other, tuple) and isinstance(other[0], str):
            return self.version == other
        elif isinstance(other, str):
            return self.version == tuple([str(int(x)) for x in other.split(".")])
        else:
            raise ValueError()

    def __gt__(self, other):
        """Compare with other BioconductorRelease, or version tuples, or strings"""
        mine = tuple([int(x) for x in self.version])
        if isinstance(other, BioconductorRelease):
            theirs = tuple([int(x) for x in other.version])
        elif isinstance(other, tuple):
            theirs = tuple([int(x) for x in other])
        elif isinstance(other, str):
            theirs = tuple([int(x) for x in other.split(".")])

        else:
            raise ValueError()
        return mine > theirs

    def update(self):
        """Create the jobs to get this up to date"""
        phase1 = self.download_packages()

        def gen_download_and_hash():
            (self.store_path / "sha256").mkdir(exist_ok=True)
            for ((name, version), url) in self.assemble_all_packages().items():
                hash_job(
                    url=f"{self.base_url}{url}",
                    path=self.store_path
                    / "sha256"
                    / (name + "_" + version + ".sha256"),
                )

        phase2 = ppg2.JobGeneratingJob(
            f"gen_download_and_hash_bioconductor_{self.version}", gen_download_and_hash
        )
        phase2.depends_on(phase1)
        # no need to depende no assembl_all_packages / package pages - it's being done anyway
        return [phase2, phase1]

    def download_packages(self):
        """Download the PACKAGES.gz for the software packages"""
        return [
            self.get_software_packages(),
            self.get_software_archive(),
            # note that annotation/experiment has no Archive
            self.get_annotation_packages(),
            self.get_experiment_packages(),
        ]

    def get_url(self, kind, archive=False):
        if archive:
            if kind == "software":
                return f"{self.base_url}bioc/src/contrib/Archive"
            else:
                raise ValueError(kind)
        else:
            if kind == "software":
                return f"{self.base_url}bioc/src/contrib/"
            elif kind == "experiment":
                return f"{self.base_url}data/experiment/src/contrib/"
            elif kind == "annotation":
                return f"{self.base_url}data/annotation/src/contrib/"
            else:
                raise ValueError(kind)

    def get_software_packages(self):
        return download_packages(
            f"{self.base_url}bioc/src/contrib/PACKAGES.gz",
            self.store_path / "packages.bioc.json.gz",
            list_packages=False,
        )

    def get_annotation_packages(self):
        return download_packages(
            f"{self.base_url}data/annotation/src/contrib/PACKAGES.gz",
            self.store_path / "packages.annotation.json.gz",
            list_packages=False,
        )

    def get_experiment_packages(self):
        # note that experiment has no Archive
        return download_packages(
            f"{self.base_url}data/experiment/src/contrib/PACKAGES.gz",
            self.store_path / "packages.experiment.json.gz",
            list_packages=False,
        )

    def get_software_archive(self):
        """Parse the Archives for name:(version, date)"""
        if not self.has_archive():
            return []

        def download(outfilename):
            base = (
                self.base_urls[0] + "bioc/src/contrib/"
            )  # dortmund has a different layout
            packages = {}
            r1 = requests.get(base + "Archive")
            r1.raise_for_status()
            for hit in re.findall('href="([^/][^/]+)/"', r1.text):
                if hit == "..":
                    continue
                packages[hit] = []
            pool = multiprocessing.Pool(6)
            for hit, result in pool.map(
                versions_from_archive, [(hit, base) for hit in packages]
            ):
                packages[hit] = result
            with gzip.GzipFile(outfilename, "wb") as op:
                op.write(json.dumps(packages, indent=2).encode("utf-8"))

        return (
            ppg2.FileGeneratingJob(
                self.store_path / "archive.json.gz",
                download,
                resources=ppg2.Resources.AllCores,
            )
            .depends_on(self.date_invariant)
            .depends_on_func(versions_from_archive, "version_from_archive")
        )

    def load_archive(self):
        """load the archive data - if applicable"""
        if self.has_archive():
            return json.loads(
                gzip.GzipFile(self.store_path / "archive.json.gz")
                .read()
                .decode("utf-8")
            )
        else:
            return {}

    def has_archive(self):
        """Bioconductor started having 'archived' versions with 3.6.
        If you need something earlier, I suppose you're out of luck
        """
        return self >= (3, 6)

    def get_R_version_including_minor(self, archive_date, r_track):
        if self.str_version in bioconductor_overrides.r_versions:
            return bioconductor_overrides.r_versions[self.str_version]
        elif (
            self.str_version,
            format_date(archive_date),
        ) in bioconductor_overrides.r_versions:
            return bioconductor_overrides.r_versions[
                (self.str_version, format_date(archive_date))
            ]
        else:
            return r_track.latest_minor_release_at_date(
                self.major_r_version, archive_date
            )

    def get_cran_dates(self, cran_tracker, r_track):
        """Given our package list and what's in the archives,
        what dates actually had changes?

        This is the dates we need CRAN at.
        """
        result = set()
        available = cran_tracker.snapshots
        for archive_date in r_track.minor_release_dates(self.major_r_version):
            if (
                self.release_info.start_date
                <= archive_date
                < self.release_info.end_date
            ):
                snapshot_date = self.find_closest_available_snapshot(
                    archive_date, available
                )
                result.add((archive_date, snapshot_date))

        result.add(
            (
                self.release_info.start_date,
                self.find_closest_available_snapshot(
                    self.release_info.start_date, available
                ),
            )
        )
        for package, version_dates in self.load_archive().items():
            for vd in version_dates:
                archive_date = datetime.datetime.strptime(vd[1], "%Y-%m-%d").date()
                snapshot_date = self.find_closest_available_snapshot(
                    archive_date, available
                )
                result.add((archive_date, snapshot_date))
        for str_date in bioconductor_overrides.extra_snapshots.get(
            self.str_version, {}
        ):
            d = datetime.datetime.strptime(str_date, "%Y-%m-%d").date()
            # we use these mostly in non-archived Bioconductor versions,
            # so it's safe to set archive date = snapshot date.
            result.add((d, d))
        return result

    def find_closest_archive_date(self, date: datetime.date):
        """Find the closest (previous) date in the archive"""
        all_dates = set()
        for package, version_dates in self.load_archive().items():
            for _version, a_date in version_dates:
                all_dates.add(
                    datetime.datetime.strptime(
                        a_date,
                        "%Y-%m-%d",
                    ).date()
                )
        if all(x > date for x in all_dates):  # release date, or shortly after?
            all_dates.add(date)
        candidates = sorted([x for x in all_dates if x <= date])
        return candidates[-1]

    def find_closest_available_snapshot(self, date, available_snapshots):
        """Sometimes MRAN (or Rstudio) does not have a CRAN snapshot
        at the date bioconductor was updated.
        We'll use the previous available date instead.
        (Not the next, that's unstable if it's today that wasn't snapshoted")
        """
        d = date.strftime("%Y-%m-%d")
        ok = sorted(
            [x for x in available_snapshots if x <= d]
        )  # lexographic sorting for the win
        if not ok:
            raise ValueError(
                "none <=", d, "latest available", sorted(available_snapshots)[-1]
            )
        return datetime.datetime.strptime(ok[-1], "%Y-%m-%d").date()

    def assemble_all_packages(self):
        out = {}
        for name, ver in read_packages_and_versions_from_json(
            self.store_path / "packages.bioc.json.gz"
        ):
            out[name, ver] = f"bioc/src/contrib/{name}_{ver}.tar.gz"
        for name, ver in read_packages_and_versions_from_json(
            self.store_path / "packages.experiment.json.gz"
        ):
            out[name, ver] = f"data/experiment/src/contrib/{name}_{ver}.tar.gz"
        for name, ver in read_packages_and_versions_from_json(
            self.store_path / "packages.annotation.json.gz"
        ):
            out[name, ver] = f"data/annotation/src/contrib/{name}_{ver}.tar.gz"

        if self.patch_packages:
            for entry in self.patch_packages.get("experiment", []):
                out[
                    entry["name"], entry["version"]
                ] = f"data/experiment/src/contrib/{entry['name']}_{entry['version']}.tar.gz"
            for entry in self.patch_packages.get("software", []):
                raise ValueError("todo")
            for entry in self.patch_packages.get("annotation", []):
                raise ValueError("todo")

        archive = self.load_archive()
        for name, entries in archive.items():
            for (ver, date) in entries:
                out[name, ver] = f"bioc/src/contrib/Archive/{name}/{name}_{ver}.tar.gz"
        if self.excluded_packages:
            # for excluded packages, we don't even try to download a sha
            # ( some exclusions are because the package is no longer present in bioconductor)
            out = {
                (name, ver): url
                for ((name, ver), url) in out.items()
                if name not in self.excluded_packages
            }
        return out

    def get_packages(self, kind, query_date):
        def find_right_archive_date(archive_dates, query_date):
            """take archive_dates -> version, return version to use"""
            o = sorted(archive_dates.keys())
            i = bisect.bisect_left(o, query_date)
            if i < len(o):
                return archive_dates[o[i]]
            else:  # beyond latest archived date?, use last
                #raise ValueError(query_date, o[-2:])
                return False #archive_dates[o[-1]]

        if kind in ("experiment", "annotation", "software"):
            if kind == "software":
                akind = "bioc"
            else:
                akind = kind
            source = self.store_path / f"packages.{akind}.json.gz"
        else:
            raise ValueError(kind)

        package_info = read_json(source)
        result = {}
        for info in package_info:
            name = info["name"]
            if name in result:
                raise ValueError("Duplicate in packages", kind, name)
            if info["os_type"] != "windows":
                result[name] = {
                    "version": info["version"],
                    "depends": info["depends"],
                    "imports": info["imports"],
                    "linking_to": info["linking_to"],
                    "suggests": info["suggests"],
                    "needs_compilation": info["needs_compilation"],
                }
        if kind == "software":
            result.update(
                bioconductor_overrides.missing_in_packages_gz.get(self.str_version, {})
            )
        if kind == "software":
            for package, version_dates in self.load_archive().items():
                if package not in result:
                    if package == "BiocInstaller":
                        # yeah...  you never distributed biocInstaller via bioconductor otherwise,
                        # so we're going to ignore you
                        continue
                    else:
                        raise ValueError(
                            f"Package {package} in archive that was not in PACKAGES.gz"
                        )
                archive_dates = {
                    datetime.datetime.strptime(date, "%Y-%m-%d").date(): v
                    for (v, date) in version_dates
                }
                v = find_right_archive_date(
                    archive_dates, query_date
                )
                if v: 
                    result[package]["version"] = v
                    result[package]["archive"] = True

        adr = bioconductor_overrides.additional_r_dependencies.get(
            self.str_version, {}
        ).get(kind, {})

        dadr = set(adr.keys()).difference(result.keys())
        if dadr:
            raise ValueError(
                f"additional_r_dependencies for {kind} that are not in {kind}: {sorted(dadr)}"
            )

        for name, add_deps in adr.items():
            result[name]["depends"] += add_deps

        for entry in self.patch_packages.get(kind, []):
            print("patching", entry["name"])
            result[entry["name"]] = {
                "version": entry["version"],
                "depends": entry["depends"],
                "imports": entry["imports"],
                "linking_to": entry["linking_to"],
                "suggests": entry["suggests"],
                "needs_compilation": entry["needs_compilation"],
            }

        return result

    def get_excluded_packages_at_date(self, date):
        return match_override_keys(
            bioconductor_overrides.excluded_packages,
            self.str_version,
            date,
            release_info=self.release_info,
        )  # which includes the inherited entries

    def get_broken_packages_at_date(self, date):
        return match_override_keys(
            bioconductor_overrides.broken_packages,
            self.str_version,
            date,
            release_info=self.release_info,
        )  # which includes the inherited entries


    def get_flake_info_at_date(self, date, r_track):
        minor_r_version = self.get_R_version_including_minor(date, r_track)
        r_sha = r_track.get_sha(minor_r_version)

        nixpkgs_to_use = None
        nixpkgs_comment = ""
        for str_release_date, (nixpkgs_url, this_comment) in sorted(
            bioconductor_overrides.nix_releases.items()
        ):
            if parse_date(str_release_date) <= date:
                nixpkgs_to_use = nixpkgs_url
                nixpkgs_comment = this_comment
        if nixpkgs_to_use is None:
            raise ValueError("Failed to find nixpkgs_to_use")
        if self.str_version in bioconductor_overrides.comments:
            nixpkgs_comment += "\n" + bioconductor_overrides.comments[self.str_version]
        nixpkgs_comment = nixpkgs_comment.strip()

        result = {
            "r_version": minor_r_version,
            "r_tar_gz_sha256": r_sha,
            "nixpkgs.url": nixpkgs_to_use,
            "comment": nixpkgs_comment,
        }
        if minor_r_version in bioconductor_overrides.r_patches:
            result["patches"] = bioconductor_overrides.r_patches[minor_r_version]
        if minor_r_version in bioconductor_overrides.additional_r_overrides:
            result[
                "additionalOverrides"
            ] = bioconductor_overrides.additional_r_overrides[minor_r_version]
        if minor_r_version in bioconductor_overrides.flake_overrides:
            result["flake_override"] = bioconductor_overrides.flake_overrides[
                minor_r_version
            ]

        return result

    def get_comment_at_date(self, date):
        return match_override_keys(
            bioconductor_overrides.comments,
            self.str_version,
            date,
            none_ok=True,
            default=lambda: "",
            release_info=self.release_info,
        )

    def get_build_inputs(self, date):  # for dependency tracking
        res = {}
        for what in ["native_build_inputs", "build_inputs"]:
            nbi = match_override_keys(
                getattr(bioconductor_overrides, what),
                self.str_version,
                date,
                release_info=self.release_info,
            )
            res[what] = nbi
        res["skip"] = match_override_keys(
            bioconductor_overrides.skip_check,
            self.str_version,
            date,
            none_ok=True,
            default=lambda: [],
            release_info=self.release_info,
        )
        for what in ["patches", "attrs", "overrideDerivations"]:
            res[what] = match_override_keys(
                getattr(bioconductor_overrides, what),
                self.str_version,
                date,
                none_ok=True,
                release_info=self.release_info,
            )
        res["patches_by_version"] = bioconductor_overrides.patches_by_package_version
        res["needs_x"] = bioconductor_overrides.needs_x
        res[
            "additional_r_dependencies"
        ] = bioconductor_overrides.additional_r_dependencies.get(self.str_version, {})
        return res

    def patch_native_dependencies(self, graph, all_packages, excluded, date):
        # this is here because it's bioc version dependent
        # but it also handles cran packages
        def repl_dep(n):
            if is_nix_literal(n):
                return n
            elif "." not in n and (n != "breakpointHook"):
                return nix_literal(f"pkgs.{n}")
            else:
                return nix_literal(n)

        errors = []
        for what in ["native_build_inputs", "build_inputs"]:
            nbi = match_override_keys(
                getattr(bioconductor_overrides, what),
                self.str_version,
                date,
                release_info=self.release_info,
            )
            for pkg_name, deps in nbi.items():
                if pkg_name not in graph.nodes and pkg_name not in excluded:
                    errors.append(
                        f"package with {what} but not in graph or excluded: {pkg_name} {date}"
                    )
                    continue
                if pkg_name in excluded:
                    continue
                if not isinstance(deps, (list)) and not is_nix_literal(deps):
                    raise ValueError(nbi, pkg_name, "must be list")
                if is_nix_literal(deps):
                    all_packages[pkg_name][what] = deps
                else:
                    all_packages[pkg_name][what] = sorted([repl_dep(n) for n in deps])
        skip = match_override_keys(
            bioconductor_overrides.skip_check,
            self.str_version,
            date,
            none_ok=True,
            default=lambda: [],
            release_info=self.release_info,
        )
        for pkg_name in skip:
            if pkg_name in all_packages:
                all_packages[pkg_name]["skip_check"] = True
            else:
                errors.append(f"{pkg_name} in skip_check, but not in all_packages")

        for what in ["patches", "attrs", "overrideDerivations"]:
            mok = match_override_keys(
                getattr(bioconductor_overrides, what),
                self.str_version,
                date,
                none_ok=True,
                release_info=self.release_info,
            )
            # first we apply the 'inherit from upstream values
            for pkg_name, values in mok.items():
                if pkg_name.endswith("->") or pkg_name.endswith("->>"):
                    upstream_pkg_name = pkg_name[: pkg_name.rfind("-")]
                    recursive = pkg_name.endswith("->>")
                    if (
                        upstream_pkg_name not in all_packages
                        and upstream_pkg_name not in excluded
                    ):
                        errors.append(
                            f"package-> with {what} but not in graph or excluded: {pkg_name}"
                        )
                    for (
                        downstream_pkg_name
                    ) in networkx.algorithms.traversal.depth_first_search.dfs_preorder_nodes(
                        graph,
                        source=upstream_pkg_name,
                        depth_limit=1 if not recursive else None,
                    ):
                        v = all_packages[downstream_pkg_name]
                        if what in v:
                            if isinstance(values, dict):
                                v[what].update(values)
                            else:
                                v[what] += values
                        else:
                            v[what] = values

            # then the per package ones
            for pkg_name, values in mok.items():
                if not (pkg_name.endswith("->") or pkg_name.endswith("->>")):
                    if pkg_name not in all_packages and pkg_name not in excluded:
                        errors.append(
                            f"package with {what} but not in graph or excluded: {pkg_name}"
                        )
                    if pkg_name in all_packages:
                        v = all_packages[pkg_name]
                        if what in v:
                            if isinstance(values, dict):
                                v[what].update(values)
                            else:
                                v[what] += values
                        else:
                            v[what] = values

        for pkg_name, info in all_packages.items():
            key = pkg_name, info["version"]
            if key in bioconductor_overrides.patches_by_package_version:
                all_packages[pkg_name][
                    "patches"
                ] = bioconductor_overrides.patches_by_package_version[key]

        if errors:
            # print(sorted(all_packages.keys()))
            # print(excluded)
            raise ValueError(
                "\n".join(errors),
            )

        # extra special magic for samtools injecting zlib
        for node in graph.successors("Rsamtools"):
            build_inputs = all_packages[node].get("native_build_inputs", [])
            build_inputs.append(nix_literal("pkgs.zlib"))
            all_packages[node]["native_build_inputs"] = build_inputs

        needs_x = set(bioconductor_overrides.needs_x.copy())
        also_needs_x = []
        for pkg_name, info in all_packages.items():
            try:
                if needs_x.intersection(info["suggests"]) or needs_x.intersection(
                    info["depends"]  # which is depends + linking_to + imports
                ):
                    also_needs_x.append(pkg_name)
            except KeyError:
                print(info)
                raise

        needs_x.update(also_needs_x)
        for pkg_name in needs_x:
            if pkg_name in graph.nodes:
                all_packages[pkg_name]["needs_x"] = True
                # for node in descendants(graph, pkg_name):
                # all_packages[node]["needs_x"] = True
                # print("setting needs_x", node, pkg_name)


archive_hit_regexps = re.compile(
    r'([^>]+)</a></td><td align="right">(\d{4}-\d{2}-\d{2})'
)


def versions_from_archive(args):
    hit, base = args
    r2 = requests.get(base + "Archive/" + hit)
    r2.raise_for_status()
    found = False
    result = []
    for tar_hit in archive_hit_regexps.findall(r2.text):
        name, ver = tar_hit[0].replace(".tar.gz", "").split("_", 1)
        if name != hit:
            raise ValueError(name, hit)
        result.append((ver, tar_hit[1]))
        found = True
    if not found:
        raise ValueError()
    time.sleep(0.1) # don't hammer the server, ok?
    return hit, result
