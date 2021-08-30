"""Bioconductor updates it's PACKAGES.gz when it releases point updates.

The replaced packages get moved to archive/ when that's done.
(starting with 3.6, october 2017)

So we need to download the current packages,
and synthesize the lists as of the date the archive versions were created.
"""
from pathlib import Path
import requests
import re
import datetime
import gzip
import json
import yaml
import io
import pprint
import hashlib
import collections
from typing import Tuple
import functools
import pypipegraph2 as ppg2
from .common import (
    store_path,
    cache_path,
    RPackageParser,
    download_packages,
    read_packages_and_versions_from_json,
    hash_job,
)
from .cran_track import CranTrack


def version_to_tuple(v):
    return tuple([str(int(y)) for y in v.split(".")])


class ReleaseInfo:
    def __init__(self, start_date, end_date):
        self.start_date = start_date
        self.end_date = end_date

    def __str__(self):
        return f"ReleaseInfo({self.start_date}, {self.end_date}) # {self.end_date - self.start_date}"

    def __repr__(self):
        return str(self)


class BioConductorTrack:
    def get_release_date_ranges(self):
        if not hasattr(self, "_get_release_date_ranges"):
            url = "https://bioconductor.org/config.yaml"
            r = requests.get(url)
            i = io.StringIO(r.text)
            y = yaml.safe_load(i)
            release_dates = y["release_dates"]
            r_ver_for_bioc_ver = y["r_ver_for_bioc_ver"]
            release_dates = {
                k: datetime.datetime.strptime(v, "%m/%d/%Y").date()
                for (k, v) in release_dates.items()
            }
            release_dates = [
                (version_to_tuple(x[0]), x[1]) for x in release_dates.items()
            ]
            release_dates = sorted(release_dates, key=lambda x: [int(y) for y in x[0]])
            rinfo = {}
            for cur, plusone in zip(release_dates, release_dates[1:]):
                rinfo[cur[0]] = ReleaseInfo(
                    cur[1], plusone[1] - datetime.timedelta(days=1)
                )
            cur = release_dates[-1]
            rinfo[cur[0]] = ReleaseInfo(cur[1], datetime.date.today())
            self._get_release_date_ranges = rinfo
        return self._get_release_date_ranges

    @staticmethod
    def has_archive(version):
        return version >= (3, 6)

    def get_release(self, version):
        rinfos = self.get_release_date_ranges()
        if isinstance(version, str):
            version = version_to_tuple(version)
        return BioconductorRelease(version, rinfos[version])

    def iter_releases(self):
        for version in self.get_release_date_ranges():
            yield self.get_release(version)

    # def get_archive_as_of_date(self, date):


@functools.total_ordering
class BioconductorRelease:
    def __init__(self, version: Tuple[str, str], release_info):
        self.version = version
        self.str_version = ".".join(version)
        self.release_info = release_info
        self.base_url = f"https://bioconductor.org/packages/{self.str_version}/"
        self.store_path = (
            (store_path / "bioconductor" / self.str_version)
            .absolute()
            .relative_to(Path(".").absolute())
        )
        self.store_path.mkdir(exist_ok=True, parents=True)
        self.date_invariant = ppg2.ParameterInvariant(
            # if the end date changes (current release...), we refetch the packages and archives
            self.store_path / "packages.json.gz",
            (self.release_info.end_date.strftime("%Y-%m-%d"),),
        )
        self.blacklist = None
        # bioconductor deprecates packages, removes their .tar.gz
        # but doesn't bother with fixing the PACKAGES
        # or marking them there in any way...
        if self.version == ("3", "7"):
            self.blacklist = set(["iontree", "domainsignatures"])

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
        phase1 = self.get_packages()

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
        return [phase2, phase1]

    def get_packages(self):
        """Download the PACKAGES.gz for the software packages"""
        return [
            self.get_software_packages(),
            self.get_software_archive(),
            # note that annotation/experiment has no Archive
            self.get_annotation_packages(),
            self.get_experiment_packages(),
        ]

    def get_software_packages(self):
        return download_packages(
            f"{self.base_url}bioc/src/contrib/PACKAGES.gz",
            self.store_path / "packages.bioc.json.gz",
        )

    def get_annotation_packages(self):
        return download_packages(
            f"{self.base_url}data/annotation/src/contrib/PACKAGES.gz",
            self.store_path / "packages.annotation.json.gz",
        )

    def get_experiment_packages(self):
        # note that experiment has no Archive
        return download_packages(
            f"{self.base_url}data/experiment/src/contrib/PACKAGES.gz",
            self.store_path / "packages.experiment.json.gz",
        )

    def get_software_archive(self):
        """Parse the Archives for name:(version, date)"""
        if not self.has_archive():
            return []

        def download(outfilename):
            base = self.base_url + "bioc/src/contrib/"
            packages = {}
            for hit in re.findall(
                'href="([^/][^/]+)/"', requests.get(base + "Archive").text
            ):
                packages[hit] = []
                for tar_hit in re.findall(
                    r'([^>]+)</a></td><td align="right">(\d{4}-\d{2}-\d{2})',
                    requests.get(base + "Archive/" + hit).text,
                ):
                    name, ver = tar_hit[0].replace(".tar.gz", "").split("_", 1)
                    if name != hit:
                        raise ValueError(name, hit)
                    packages[hit].append((ver, tar_hit[1]))
            with gzip.GzipFile(outfilename, "wb") as op:
                op.write(json.dumps(packages, indent=2).encode("utf-8"))

        return ppg2.FileGeneratingJob(
            self.store_path / "archive.json.gz", download
        ).depends_on(self.date_invariant)

    def load_archive(self):
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

    def get_cran_dates(self):
        """Given our package list and what's in the archives,
        what dates actually had changes?

        This is the dates we need CRAN at.
        """
        result = set()
        result.add(self.release_info.start_date)
        available = CranTrack.list_snapshots()
        for package, version_dates in self.load_archive().items():
            for vd in version_dates:
                d = datetime.datetime.strptime(vd[1], "%Y-%m-%d").date()
                d = self.find_closest_available_snapshot(d, available)
                result.add(d)
        return result

    def find_closest_available_snapshot(self, date, available_snapshots):
        """Sometimes MRAN (or Rstudio) does not have a CRAN snapshot
        at the date bioconductor was updated.
        We'll use the next available date instead.
        """
        d = date.strftime("%Y-%m-%d")
        ok = sorted(
            [x for x in available_snapshots if x >= d]
        )  # lexographic sorting for the win
        if not ok:
            print(d, sorted(available_snapshots)[-1])
        return datetime.datetime.strptime(ok[0], "%Y-%m-%d")

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

        archive = self.load_archive()
        for name, entries in archive.items():
            for (ver, date) in entries:
                out[name, ver] = f"bioc/src/contrib/Archive/{name}/{name}_{ver}.tar.gz"
        if self.blacklist:
            out = {
                (name, ver): url
                for ((name, ver), url) in out.items()
                if name not in self.blacklist
            }
        return out
