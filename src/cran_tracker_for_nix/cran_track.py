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
        self.store_path = self.store_path = (
            (store_path / "cran").absolute().relative_to(Path(".").absolute())
        )
        self.store_path.mkdir(exist_ok=True, parents=True)
        if snapshot_dates:
            self.snapshot_dates = snapshot_dates
        else:
            self.snapshot_dates = self.list_snapshots()

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
                if a is None:
                    pkgs_a = {}
                else:
                    pkgs_a = read_packages(a)
                pkgs_b = read_packages(b)
                for ((name, ver), entry) in pkgs_b.items():
                    if (name, ver) in pkgs_a:
                        if pkgs_a[name, ver] != entry:
                            raise ValueError(
                                "ParanoiaError - same version, but different dependencies?",
                                name,
                                ver,
                                entry,
                                a[name, ver],
                            )
                out = [
                    entry
                    for ((name, ver), entry) in pkgs_b.items()
                    if not (name, ver) in pkgs_a
                ]
                write_json(out, output_filename)

            j = ppg2.FileGeneratingJob(
                self.store_path
                / "deltas"
                / f"delta_{a.snapshot if a else None}_{b.snapshot}.json.gz",
                build_delta,
            ).depends_on(a, b)
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
            write_json(out, output_filename)

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

    def update(self):
        package_list_jobs = self.refresh_snapshots()

        def gen_download_and_hash():
            (self.store_path / "sha256").mkdir(exist_ok=True)
            for (
                (name, version),
                (snapshot, others),
            ) in self.assemble_all_packages().items():

                def do(output_filename, snapshot=snapshot):
                    # sometimes CRAN apperantly starts listing a package days before 
                    # the package file actually exists
                    # example rpart_4.1-12.tar.gz, 2018-01-11, which shows up on the 13th.
                    def add_days(snapshot, offset):
                        date = datetime.datetime.strptime(snapshot, "%Y-%m-%d")
                        date = date + datetime.timedelta(days=offset)
                        return date.strftime("%Y-%m-%d")

                    offset = 0
                    while offset < 10:  # how far into the future do you want to go?
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
                            if "404" in str(ValueError):
                                offset = 1
                            else:
                                raise

                ppg2.FileGeneratingJob(
                    self.store_path / "sha256" / (name + "_" + version + ".sha256"),
                    do,
                    depend_on_function=False,
                )

        ppg2.JobGeneratingJob(
            "gen_download_and_hash", gen_download_and_hash
        ).depends_on(package_list_jobs)
