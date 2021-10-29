import datetime
import pypipegraph2 as ppg2
import re
import requests
from pathlib import Path
from lazy import lazy


from . import common
from .common import (
    download_packages,
    read_json,
    write_json,
    hash_url,
    parse_date,
    dict_minus_keys,
    extract_snapshot_from_url,
)
from .bioconductor_overrides import match_override_keys
from . import bioconductor_overrides


base_url = "https://mran.microsoft.com/snapshot/"
# base_url = "https://packagemanager.rstudio.com/cran/" # only goes back to 2017


class CranTrack:
    """Track cran packages and their release dates for
    a given list of snapshot dates.

    We record when a package first appeared (amongst the list of snapshots),
    and it's sha256
    """

    def __init__(self):
        self.store_path = (
            (common.store_path / "cran").absolute().relative_to(Path(".").absolute())
        )
        self.store_path.mkdir(exist_ok=True, parents=True)

    @staticmethod
    def get_url(snapshot_date):
        return f"{base_url}{snapshot_date.strftime('%Y-%m-%d')}/"

    def fetch_snapshots(self):
        def download(output_filename):
            r = requests.get(base_url)
            result = re.findall(r'<a href="(\d{4}-\d{2}-\d{2})/">', r.text)
            write_json(result, output_filename)

        fn = self.store_path / "snapshots.json.gz"
        return ppg2.FileGeneratingJob(fn, download).depends_on(
            ppg2.ParameterInvariant(fn, datetime.datetime.now().strftime("%Y-%m-%d"))
        )

    @lazy
    def snapshots(self):
        """query MRAN for available snapshots"""
        return read_json(self.store_path / "snapshots.json.gz")

    @staticmethod
    def list_downloaded_snapshots():
        sp = common.store_path / "cran" / "packages"
        res = []
        for fn in sp.glob("*.json.gz"):
            d = fn.name[: fn.name.find(".")]
            if re.match(r"^\d{4}-\d{2}-\d{2}$", d):
                res.append(d)
        return sorted(res)

    def refresh_snapshots(self, snapshot_dates):
        """Download snapshot packages,
        build deltas,
        build assembled database
        """

        (self.store_path / "packages").mkdir(exist_ok=True)

        def download_snapshot_packages(snapshot):
            j = download_packages(
                url=f"{base_url}{snapshot}/src/contrib/PACKAGES.gz",
                output_filename=self.store_path / "packages" / (snapshot + ".json.gz"),
                temp=False,
            )
            j.snapshot = snapshot
            return j

        snapshots = sorted(snapshot_dates)
        sn_jobs = [download_snapshot_packages(s) for s in snapshots]

        def read_packages(fn):
            packages = read_json(fn)
            out = {}
            for row in packages:
                if row["os_type"] != "windows":
                    out[row["name"], row["version"]] = row
            return out

        deltas = []
        (self.store_path / "deltas").mkdir(exist_ok=True)

        for a, b in zip([None] + sn_jobs, sn_jobs):

            def build_delta(
                output_filename, a=a.files[0] if a is not None else None, b=b.files[0]
            ):
                def tie_breaker(name, ver, variant_a, variant_b):
                    if name == "partools":
                        if (variant_a["os_type"] == "unix") and (
                            variant_b["os_type"]
                            == "Linux/Mac/Unix needed for the dbs() debugging tool"
                        ):
                            return variant_a
                        elif (variant_b["os_type"] == "unix") and (
                            variant_a["os_type"]
                            == "Linux/Mac/Unix needed for the dbs() debugging tool"
                        ):
                            return variant_b

                    but_needs_comp_a = dict_minus_keys(
                        variant_a, ["needs_compilation", "suggests"]
                    )
                    but_needs_comp_b = dict_minus_keys(
                        variant_b, ["needs_compilation", "suggests"]
                    )

                    if but_needs_comp_a == but_needs_comp_b:
                        # only differe in compilation needed
                        # take the one that says 'needs compilation', for they have cpp files
                        if variant_a["needs_compilation"]:
                            return variant_a
                        elif variant_b["needs_compilation"]:
                            return variant_b
                        else:  # they are identical up to sgugest
                            la = len(variant_a["suggests"])
                            lb = len(variant_b["suggests"])
                            if la > lb:
                                return variant_a
                            else:
                                return variant_b

                    return None  # I have no solution for you today

                errors = []
                if a is None:
                    pkgs_a = {}
                else:
                    pkgs_a = read_packages(a)
                pkgs_b = read_packages(b)
                for ((name, ver), entry) in pkgs_b.items():
                    if (name, ver) in pkgs_a:
                        if pkgs_a[name, ver] != entry:
                            what_to_use = tie_breaker(
                                name, ver, entry, pkgs_a[name, ver]
                            )
                            if what_to_use is not None:
                                # monkey patch the lists
                                pkgs_b[name, ver] = what_to_use
                                del pkgs_a[name, ver]
                            else:
                                errors.append(
                                    (
                                        "ParanoiaError - same version, but different dependencies/needsCompilation?",
                                        name,
                                        ver,
                                        entry,
                                        pkgs_a[name, ver],
                                        a,
                                        b,
                                    )
                                )
                if errors:
                    raise ValueError(errors)
                gained = [
                    entry
                    for ((name, ver), entry) in pkgs_b.items()
                    if not (name, ver) in pkgs_a
                ]
                pkgs_b_names = set([x[0] for x in pkgs_b.keys()])
                lost = [
                    name
                    for ((name, _ver), _entry) in pkgs_a.items()
                    if name not in pkgs_b_names
                ]
                write_json(
                    {"gained": gained, "lost": lost}, output_filename, do_indent=True
                )

            j = ppg2.FileGeneratingJob(
                self.store_path
                / "deltas"
                / f"delta_{a.snapshot if a else None}_{b.snapshot}.json.gz",
                build_delta,
            )
            j.depends_on(a)
            j.depends_on(b)
            j.snapshot = b.snapshot
            deltas.append(j)

        def assemble(output_filename):
            out = {}
            latest = {}
            prev_snapshot = None
            for delta_job in deltas:
                fn = delta_job.files[0]
                snapshot = delta_job.snapshot
                j = read_json(fn)
                for info in j["gained"]:
                    name = info["name"]
                    ver = info["version"]
                    if name in latest:
                        out[name, latest[name]]["end_date"] = prev_snapshot
                    if not (name, ver) in out:
                        out[name, ver] = {
                            "start_date": snapshot,
                            "end_date": None,
                            "imports": info["imports"],
                            "depends": info["depends"],
                            "linking_to": info["linking_to"],
                            "suggests": info["suggests"],
                            "needs_compilation": info["needs_compilation"],
                        }
                        latest[name] = ver
                for lost_name in j["lost"]:
                    key = (lost_name, latest[lost_name])
                    info = out[
                        key
                    ]  # so that's (snapshot, others) or (snapshot, others, lost_date)
                    if info["end_date"] is None:
                        out[key]["end_date"] = prev_snapshot
                    else:
                        # this package&ver was added, lost, and added again
                        # but since we'll be pulling it from the first snapshot anyway
                        # and the nix-flake will fall back to /Archive
                        # we'll just keep it from the first add till the last lost...
                        pass
                prev_snapshot = snapshot
            out = [
                (name, ver, info)
                for ((name, ver), info) in sorted(out.items())
                if name not in common.build_into_r
            ]
            write_json(out, output_filename, do_indent=True)

        assemble_job = ppg2.FileGeneratingJob(
            self.store_path / "package_to_snapshot.json.gz", assemble
        )
        assemble_job.depends_on(deltas)

        return assemble_job

    def assemble_all_packages(self):
        out = {}
        data = read_json(self.store_path / "package_to_snapshot.json.gz")
        for (name, ver, info) in data:
            out[name, ver] = info
        return out

    manual_url_overrides = {
        # sometimes the snashots don't have the file specified by PACKAGES
        # within +1 month of the date we're looking for.
        # this helps out then,
        # either by using another snapshot
        # or the /Archive of CRAN
        # or in the no-such-file-anywhere case,
        # by substituting another file.
        (
            "Cairo",
            "1.5-12.1"
            # this goes from -12.tar.gz directly to -12.2.tar.gz
            # (on the transition of  2020-07-07 / 2020-07-08)
            # and is listed as .2 on 07-08
            # but is listed as .1 in packages at 2020-10-28 (and had no .1 at 2020-04-28)
            # no clue why this would have gone backwards,
        ): "https://mran.microsoft.com/snapshot/2020-07-08/src/contrib/Cairo_1.5-12.2.tar.gz",
        # the same is true for cairodevice, some dates.
        (
            "cairoDevice",
            "2.28.1"
            # the very same argument, the very same transition points as Cairo above
        ): "https://mran.microsoft.com/snapshot/2020-07-08/src/contrib/cairoDevice_2.28.2.tar.gz",
        (
            "cairoDevice",
            "2.28.2",
        ): "https://mran.microsoft.com/snapshot/2020-07-08/src/contrib/cairoDevice_2.28.2.tar.gz",
        # fun fact, 2.28.2 is identical to the 2.28.tar.gz that cran/Archive delivers
        (
            "foreign",
            "0.8-70",
            # had both .70 and .69 entries ath the snapshot date of 2017-12-04
            # but only the .69 in the snapshot...
        ): "https://cran.r-project.org/src/contrib/Archive/foreign/foreign_0.8-70.tar.gz",
        (
            "foreign",
            "0.8-70.1",
            # also missing from snapshot
        ): "https://cran.r-project.org/src/contrib/Archive/foreign/foreign_0.8-70.1.tar.gz",
        (
            "foreign",
            "0.8-70.2",
            # also missing from snapshot
        ): "https://cran.r-project.org/src/contrib/Archive/foreign/foreign_0.8-70.2.tar.gz",
        (
            "foreign",
            "0.8-77",
            # also missing from snapshot
        ): "https://cran.r-project.org/src/contrib/Archive/foreign/foreign_0.8-77.tar.gz",
        (
            "foreign",
            "0.8-78",
            # also missing from snapshot
        ): "https://cran.r-project.org/src/contrib/Archive/foreign/foreign_0.8-78.tar.gz",
        (
            "rpart",
            "4.1-12",  # not in snapshot, but in archive
        ): "https://cran.r-project.org/src/contrib/Archive/rpart/rpart_4.1-12.tar.gz",
        (
            "sivipm",
            "1.1-4",  # not in snapshot, but in archive
        ): "https://cran.r-project.org/src/contrib/Archive/sivipm/sivipm_1.1-4.tar.gz",
        (
            "sivipm",
            "1.1-4.1",  # not in snapshot, but in archive
        ): "https://cran.r-project.org/src/contrib/Archive/sivipm/sivipm_1.1-4.1.tar.gz",
        (
            "survival",
            "2.42-3.1",
            # not in snapshot, but in archive
        ): "https://cran.r-project.org/src/contrib/Archive/survival/survival_2.42-3.1.tar.gz",
        (
            "MASS",
            "7.3-51.2",
        ): "https://cran.r-project.org/src/contrib/Archive/MASS/MASS_7.3-51.2.tar.gz",
        (
            "Delaporte",
            "7.0.0",
        ): "https://cran.r-project.org/src/contrib/Archive/Delaporte/Delaporte_7.0.0.tar.gz",
        (
            "adimpro",
            "0.9.0.1",
        ): "https://cran.r-project.org/src/contrib/Archive/adimpro/adimpro_0.9.2.tar.gz",  # only appears from 2019-10-30 till 11-15, but the file is never present.
        (
            "aws",
            "2.2-1.1",  # can't find that one anywhere
        ): "https://cran.r-project.org/src/contrib/Archive/aws/aws_2.3-0.tar.gz",
        (
            "frailtypack",
            "3.0.3.2.1",
        ): "https://cran.r-project.org/src/contrib/Archive/frailtypack/frailtypack_3.0.3.2.1.tar.gz",
        (
            "frailtypack",
            "3.1.0.1",  # can't find that anywhere
        ): "https://cran.r-project.org/src/contrib/Archive/frailtypack/frailtypack_3.2.0.tar.gz",
        (
            "ggiraph",
            "0.7.0.1",
        ): "https://cran.r-project.org/src/contrib/Archive/ggiraph/ggiraph_0.7.0.1.tar.gz",
        (
            "rvg",
            "0.2.4.1",
        ): "https://cran.r-project.org/src/contrib/Archive/rvg/rvg_0.2.4.1.tar.gz",
        ("svglite", "1.2.3.1"):  # this was quickly updated to be R >1, and .2 be R >4,
        # and bioconductor at this point is R 4.0, so it's ok to use this one
        "https://mran.microsoft.com/snapshot/2020-07-08/src/contrib/svglite_1.2.3.2.tar.gz",  #
        (
            "vdiffr",
            "0.3.2.1",
        ): "https://mran.microsoft.com/snapshot/2020-07-08/src/contrib/vdiffr_0.3.2.2.tar.gz",  # replaced within the week.
        # }
    }

    def update(self, snapshot_dates):
        package_list_jobs = self.refresh_snapshots(snapshot_dates)

        def gen_download_and_hash():
            (self.store_path / "sha256").mkdir(exist_ok=True)
            for ((name, version), info,) in self.assemble_all_packages().items():

                def do(
                    output_filenames,
                    snapshot=info["start_date"],
                    name=name,
                    version=version,
                ):
                    # sometimes CRAN apperantly starts listing a package days before
                    # the package file actually exists
                    # example rpart_4.1-12.tar.gz, 2018-01-11, which shows up on the 13th.
                    def add_days(snapshot, offset):
                        date = datetime.datetime.strptime(snapshot, "%Y-%m-%d")
                        date = date + datetime.timedelta(days=offset)
                        return date.strftime("%Y-%m-%d")

                    if (name, version) in self.manual_url_overrides:
                        url = self.manual_url_overrides[name, version]
                        hash_url(
                            url=url, path=output_filenames["sha256"],
                        )
                        output_filenames["url"].write_text(url)
                    else:

                        offset = 0
                        while offset < 30:  # how far into the future do you want to go?
                            if offset:
                                offset_snapshot = add_days(snapshot, offset)
                            else:
                                offset_snapshot = snapshot
                            try:
                                url = f"{base_url}{offset_snapshot}/src/contrib/{name}_{version}.tar.gz"
                                hash_url(
                                    url, path=output_filenames["sha256"],
                                )
                                output_filenames["url"].write_text(url)
                                break
                            except ValueError:
                                if "404" in str(ValueError) or "500" in str(
                                    ValueError
                                ):  # the server has a tendency to report 500 for certain ssnaphsots
                                    offset = 1
                                else:
                                    raise ValueError(
                                        "Could not find "
                                        + f"{base_url}{snapshot}/src/contrib/{name}_{version}.tar.gz"
                                    )

                ppg2.MultiFileGeneratingJob(
                    {
                        "sha256": self.store_path
                        / "sha256"
                        / (name + "_" + version + ".sha256"),
                        "url": self.store_path
                        / "sha256"
                        / (name + "_" + version + ".url"),
                    },
                    do,
                    depend_on_function=False,
                )

        ppg2.JobGeneratingJob(
            "gen_download_and_hash", gen_download_and_hash
        ).depends_on(package_list_jobs)

    @lazy
    def package_info(self):
        return read_json(self.store_path / "package_to_snapshot.json.gz")

    def latest_packages_at_date(self, snapshot_date, bioc_str_version):
        snapshot_date = snapshot_date
        package_info = self.package_info
        result = {}

        additional_dependencies = bioconductor_overrides.additional_r_dependencies.get(
            bioc_str_version, {}
        ).get("cran", {})

        for (name, version, info,) in package_info:
            pkg_date = parse_date(info["start_date"])
            if pkg_date <= snapshot_date:
                pkg_end_date = info["end_date"]
                if pkg_end_date is not None:
                    pkg_end_date = parse_date(pkg_end_date)
                    if pkg_end_date < snapshot_date:  # end date is inclusive
                        continue
                if name in additional_dependencies:
                    info["depends"] += additional_dependencies[name]
                if name not in result or result[name]["date"] < snapshot_date:
                    result[name] = {
                        "version": version,
                        "date": pkg_date,
                        "depends": info["depends"],
                        "imports": info["imports"],
                        "linking_to": info["linking_to"],
                        "suggests": info["suggests"],
                        "needs_compilation": info["needs_compilation"],
                        "snapshot": snapshot_date,
                    }
        too_much_additional_deps = set(additional_dependencies.keys()).difference(
            result
        )
        if too_much_additional_deps:
            raise ValueError(
                "CRAN packages in additional_dependencies that are not in cran",
                sorted(too_much_additional_deps),
            )

        downgrades = match_override_keys(
            bioconductor_overrides.downgrades, "-", snapshot_date, release_info=False
        )
        for name, version in downgrades.items():
            if name not in result:
                raise ValueError(
                    f"downgrade for package {name} that's not in packages at this date?"
                )
            result[name]["version"] = version
            result[name]["snapshot"] = parse_date(
                self.find_snapshot_for_version(name, version)
            )
        return result

    def find_snapshot_for_version(self, name, version):
        """use the stored urls to find the right snapshot"""
        fn = self.store_path / "sha256" / (f"{name}_{version}.url")
        url = fn.read_text()
        return extract_snapshot_from_url(name, version, url)

    def find_latest_before_disapperance(self, package, before_date):
        """Some packages just disappear from CRAN, but of course
        without pruning downstream packages.
        Let's slip in the last known version instead.

        This is not necessarily the latest version CRAN ever had.
        Just the latest within our set of snapshots that we're looking at.
        """
        package_info = self.package_info
        out = None
        end_date = None
        for (name, version, info) in package_info:
            if name == package:
                if parse_date(info["start_date"]) < before_date:
                    if not end_date or end_date < info["end_date"]:
                        end_date = info["end_date"]
                        out = (name, version, info)
        if not out:
            return None
        # print("replaced", package)
        return {
            "name": out[0],
            "version": out[1],
            "depends": out[2]["depends"],
            "imports": out[2]["imports"],
            "linking_to": out[2]["linking_to"],
            "suggests": out[2]["suggests"],
            "needs_compilation": out[2]["needs_compilation"],
            "snapshot": parse_date(info["start_date"]),
        }
