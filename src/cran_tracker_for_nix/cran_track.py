import json
import hashlib
import datetime
import subprocess
import pypipegraph2 as ppg2
import re
import gzip
import requests
from pathlib import Path

from .common import (
    store_path,
    cache_path,
    RPackageParser,
    download_packages,
    read_json,
    write_json,
    hash_job,
    hash_url,
)


base_url = "https://mran.microsoft.com/snapshot/"


class CranTrack:
    """Track cran packages and their release dates for
    a given list of snapshot dates.

    We record when a package first appeared (amongst the list of snapshots),
    and it's sha256
    """

    def __init__(self, snapshot_dates=None):
        self.store_path = (
            (store_path / "cran").absolute().relative_to(Path(".").absolute())
        )
        self.store_path.mkdir(exist_ok=True, parents=True)
        if snapshot_dates:
            self.snapshot_dates = snapshot_dates
        else:
            self.snapshot_dates = self.list_snapshots()

    @staticmethod
    def get_url(snapshot_date):
        return f"{base_url}{snapshot_date.strftime('%Y-%m-%d')}/"

    @staticmethod
    def list_snapshots():
        """query MRAN for available snapshots"""
        cache_filename = cache_path / (
            datetime.datetime.now().strftime("%Y-%m-%d.snapshots")
        )
        if not cache_filename.exists():
            print("listing snapshots")
            r = requests.get(base_url)
            result = re.findall(r'<a href="(\d{4}-\d{2}-\d{2})/">', r.text)
            cache_filename.write_text(json.dumps(result))
        else:
            result = json.loads(cache_filename.read_text())
        return result

    @staticmethod
    def list_downloaded_snapshots():
        sp = (store_path / "cran").absolute().relative_to(
            Path(".").absolute()
        ) / "packages"
        res = []
        for fn in sp.glob("*.json.gz"):
            d = fn.name[: fn.name.find(".")]
            if re.match(r"^\d{4}-\d{2}-\d{2}$", d):
                res.append(d)
        return sorted(res)

    def refresh_snapshots(self):
        """Download snapshot packages,
        build deltas,
        build assembled database
        """

        (self.store_path / "packages").mkdir(exist_ok=True)

        def download_snapshot_packages(snapshot):
            j = download_packages(
                url=f"{base_url}{snapshot}/src/contrib/PACKAGES.gz",
                output_filename=self.store_path / "packages" / (snapshot + ".json.gz"),
                temp=True,
            )
            j.snapshot = snapshot
            return j

        snapshots = sorted(self.snapshot_dates)
        sn_jobs = [download_snapshot_packages(s) for s in snapshots]

        def read_packages(fn):
            packages = read_json(fn)
            out = {}
            for row in packages:
                out[row[0], row[1]] = row
            return out

        deltas = []
        (self.store_path / "deltas").mkdir(exist_ok=True)

        for a, b in zip([None] + sn_jobs, sn_jobs):

            def build_delta(
                output_filename, a=a.files[0] if a is not None else None, b=b.files[0]
            ):
                def tie_breaker(name, ver, variant_a, variant_b):
                    if (name, ver) in [
                        ("DStree", "1.0"),
                        ("GMD", "0.3.3"),
                        ("Gmisc", "1.4.1"),
                        ("IRTpp", "0.2.6.1"),
                        ("mixture", "1.4"),
                        ("rFTRLProximal", "1.0.0"),
                    ]:
                        # take the one that says 'needs compilation', for they have cpp files
                        if variant_a[-1]:
                            return variant_a
                        elif variant_b[-1]:
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
                                    )
                                )
                if errors:
                    raise ValueError(errors)
                out = [
                    entry
                    for ((name, ver), entry) in pkgs_b.items()
                    if not (name, ver) in pkgs_a
                ]
                write_json(out, output_filename, do_indent=True)

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
            for delta_job in reversed(deltas):
                fn = delta_job.files[0]
                snapshot = delta_job.snapshot
                for name, ver, *others in read_json(fn):
                    out[name, ver] = snapshot, others
            out = [(name, ver, date) for ((name, ver), date) in sorted(out.items())]
            write_json(out, output_filename, do_indent=True)

        assemble_job = ppg2.FileGeneratingJob(
            self.store_path / "package_to_snapshot.json.gz", assemble
        )
        assemble_job.depends_on(deltas)

        return assemble_job

    def assemble_all_packages(self):
        out = {}
        data = read_json(self.store_path / "package_to_snapshot.json.gz")
        for (name, ver, snapshot) in data:
            out[name, ver] = snapshot
        return out

    manual_url_overwrites = {
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

    def update(self):
        package_list_jobs = self.refresh_snapshots()

        def gen_download_and_hash():
            (self.store_path / "sha256").mkdir(exist_ok=True)
            for (
                (name, version),
                (snapshot, others),
            ) in self.assemble_all_packages().items():

                def do(output_filename, snapshot=snapshot, name=name, version=version):
                    # sometimes CRAN apperantly starts listing a package days before
                    # the package file actually exists
                    # example rpart_4.1-12.tar.gz, 2018-01-11, which shows up on the 13th.
                    def add_days(snapshot, offset):
                        date = datetime.datetime.strptime(snapshot, "%Y-%m-%d")
                        date = date + datetime.timedelta(days=offset)
                        return date.strftime("%Y-%m-%d")

                    if (name, version) in self.manual_url_overwrites:
                        hash_url(
                            url=self.manual_url_overwrites[name, version],
                            path=output_filename,
                        )
                    else:

                        offset = 0
                        while offset < 30:  # how far into the future do you want to go?
                            if offset:
                                offset_snapshot = add_days(snapshot, offset)
                            else:
                                offset_snapshot = snapshot
                            try:
                                hash_url(
                                    url=f"{base_url}{offset_snapshot}/src/contrib/{name}_{version}.tar.gz",
                                    path=output_filename,
                                )
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

                ppg2.FileGeneratingJob(
                    self.store_path / "sha256" / (name + "_" + version + ".sha256"),
                    do,
                    depend_on_function=False,
                )

        ppg2.JobGeneratingJob(
            "gen_download_and_hash", gen_download_and_hash
        ).depends_on(package_list_jobs)

    def latest_packages_at_date(self, snapshot_date):
        snapshot_date = snapshot_date
        package_info = read_json(self.store_path / "package_to_snapshot.json.gz")
        result = {}
        for (
            name,
            version,
            (pkg_date, (depends, imports, needs_compilation)),
        ) in package_info:
            pkg_date = datetime.datetime.strptime(pkg_date, "%Y-%m-%d").date()
            if pkg_date <= snapshot_date:
                if not name in result or result[name]["date"] < snapshot_date:
                    result[name] = {
                        "version": version,
                        "date": pkg_date,
                        "depends": depends,
                        "imports": imports,
                        'needs_compilation': needs_compilation,
                    }
        return result
