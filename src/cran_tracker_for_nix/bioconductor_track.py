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
import gzip
import json
import yaml
import io
import pprint
import hashlib
import collections
from typing import Tuple
import random
import functools
from lazy import lazy
import pypipegraph2 as ppg2
from . import common
from .common import (
    RPackageParser,
    download_packages,
    read_packages_and_versions_from_json,
    hash_job,
    read_json,
    version_to_tuple,
)


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
        url = "https://bioconductor.org/config.yaml"
        r = requests.get(url)
        i = io.StringIO(r.text)
        return yaml.safe_load(i)

    @lazy
    def release_date_ranges(self):
        """Bioconductor releases, when were they current?"""
        y = self.config_yaml
        release_dates = y["release_dates"]
        r_ver_for_bioc_ver = y["r_ver_for_bioc_ver"]
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

    def get_R_version_including_minor(self, release, archive_date, r_track):
        major = self.get_R_version(release)
        return r_track.latest_minor_release_at_date(major, archive_date)

    @staticmethod
    def has_archive(version):
        return version >= (3, 6)

    def get_release(self, version):
        rinfos = self.release_date_ranges
        if isinstance(version, str):
            version = version_to_tuple(version)
        return BioconductorRelease(version, rinfos[version])

    def iter_releases(self):
        for version in self.release_date_ranges:
            yield self.get_release(version)

    def date_to_version(self, date):
        """Which release was current at {date}"""
        for release, rinfo in self.release_date_ranges.items():
            if rinfo.start_date <= date < rinfo.end_date:
                return release
        raise KeyError(date)


# packages that we kick out of the index
# per bioconductor release, and sometimes per date.
# the world ain't perfect 🤷
# note that we can kick from specific lists by prefixing with one of
# 'experiment--'.
# 'annotation--'.
# 'bioc--'. = bioconductor software
# 'cran--'.
# which is necessary when a package is in multiple but we don't want to kick all of them.

blacklist = {
    ("3.0"): [
        "arrayQualityMetrics",  # missing SVGAnnotation
        "excel.link",  # missing RDCOMClient (omegahat / github only?)
        "HierO",  # missing XMLRPC
        "pubmed.mineR",  # missing SSOAP (omegahat / github only?)
        "RCytoscape",  #  missing XMLRPC
        "rneos",  # missing XMLRPC
        "rols",  # SSOAP and XMLSchema (omegahat)
        # indirect - due to above
        "RamiGO",  # depends on RCytoscape
        "NCIgraph",  # depends on RCytoscape
        "categoryCompare",  # depends on RCytoscape
        "DEGraph",  # depends on NCIgraph
        # these are in both annotation and experiment, but the annotation version number is higher
        # (3.0.0 vis 1.1.0)
        "experiment--MafDb.ALL.wgs.phase1.release.v3.20101123",
        "experiment--MafDb.ESP6500SI.V2.SSA137.dbSNP138",
        "experiment--phastCons100way.UCSC.hg19",
        # bioconductor has never versions
        "cran--GOsummaries",
        "cran--gdsfmt",
        "cran--oposSOM",
    ],
    ("3.1"): [
        "arrayQualityMetrics",  # missing SVGAnnotation
        "excel.link",  # missing RDCOMClient
        "RCytoscape",  # missing XMLRPC
        "rols",  # missing SSOAP, XMLSchema
        # indirect - due to above
        "NCIgraph",  # depends on RCytoscape
        "RamiGO",  # depends on RCytoscape
        "categoryCompare",  # depends on RCytoscape
        "DEGraph",  # depends on NCIgraph
    ],
    (
        "3.1",
        "2015-04-17",
    ): [  # missing at release, but appear in the extra_snapshot below
        "OmicsMarkeR",  # missing assertive.base
        "seqplots",  # missing DT, which was not in PACKAGES at release, but showed up at 06-09
    ],
    ("3.2"): [
        "RCytoscape",  # missing XMLRPC
        "rols",  # SSOAP and XMLSchema (omegahat)
        "arrayQualityMetrics",  # missing SVGAnnotation
        # indirect - due to above
        "NCIgraph",  # depends on RCytoscape
        "RamiGO",  # depends on RCytoscape
        "categoryCompare",  # depends on RCytoscape
        "DEGraph",  # depends on NCIgraph
    ],
    ("3.2", "2015-10-14"): [
        "MSstats",  # missing ggrepel - added sometime within this bioconductor release, see extra_snapshots
    ],
    ("3.3"): [
        "RCytoscape",  # depends on XMLRPC
        "arrayQualityMetrics",  # missing SVGAnnotation
        # indirect - due to above
        "NCIgraph",  # depends on RCytoscape
        "RamiGO",  # depends on RCytoscape
        "categoryCompare",  # depends on RCytoscape
        "EGAD",  # depends on arrayQualityMetrics
        "DEGraph",  # depends on NCIgraph
    ],
    ("3.4"): [
        "RCytoscape",  # depends on XMLRPC
        "arrayQualityMetrics",  # missing SVGAnnotation
        # indirect - due to above
        "NCIgraph",  # depends on RCytoscape
        "RamiGO",  # depends on RCytoscape
        "categoryCompare",  # depends on RCytoscape
        "EGAD",  # depends on arrayQualityMetrics
        "DEGraph",  # depends on NCIgraph
    ],
    ("3.5"): [
        "RCytoscape",  # depends on XMLRPC
        "arrayQualityMetrics",  # missing SVGAnnotation
        # indirect - due to above
        "NCIgraph",  # depends on RCytoscape
        "RamiGO",  # depends on RCytoscape
        "categoryCompare",  # depends on RCytoscape
        "EGAD",  # depends on arrayQualityMetrics
        "DEGraph",  # depends on NCIgraph
    ],
    ("3.5", "2017-04-25"): [
        "grasp2db",  # missing dbplyr
        "BiocFileCache",  # missing dbplyr
        "Organism.dplyr",  # missing dbplyr
        "metagenomeFeatures",  # missing dbplyr
        # indirect
        "greengenes13.5MgDb",  # missing metagenomeFeatures
    ],
    ("3.6"): [
        "RCytoscape",  # depends on XMLRPC which is not in cran (was apperantly at one point on r-forge, is no longer). Might be in conda
        "RamiGO",  # needs RCytoscape
    ],
    ("3.7"): [
        "iontree",
        "domainsignatures"
        # bioconductor deprecates packages, removes their .tar.gz
        # but doesn't bother with fixing the PACKAGES
        # or marking them there in any way...
    ],
    ("3.10"): [
        "charmData",  # missing charm, which has deprecated
    ],
    ("3.10", "<2019-11-15"): [
        "animalcules",  # missing reactable - 3.10 was release on "2019-10-30", but reactable doesn't show up before 2019-11-16
    ],
    ("3.11"): [
        "REIDS",  # missing GenomeGraphs, wich was deprecated in 3.10 already and is missing in 3.11
        "MTseekerData",  # missing MTseeker, wich was deprecated in 3.10 already and is missing in 3.11
        "RIPSeekerData",  # missing RIPSeeker, wich was deprecated in 3.10 already and is missing in 3.11
        "lpNet",  # missing nem, wich was deprecated in 3.10 already and is missing in 3.11
    ],
    ("3.12"): [
        # deseq is deprecated in 3.12
        "AbsFilterGSEA",  # missing DESeq
        "APAlyzer",  # missing DESeq
        "apmsWAPP",  # missing DESeq
        "ArrayExpressHTS",  # missing DESeq
        "DBChIP",  # missing DESeq
        "DEsubs",  # missing DESeq
        "EDDA",  # missing DESeq
        "MAMA",  # missing MergeMaid
        "MAMA",  # missing metaArray
        "metaseqR",  # missing DESeq
        "Polyfit",  # missing DESeq
        "REIDS",  # missing GenomeGraphs
        "rnaSeqMap",  # missing DESeq
        "scGPS",  # missing DESeq
        "SeqGSEA",  # missing DESeq
        "Tnseq",  # missing DESeq
        "tRanslatome",  # missing DESeq
        "vulcan",  # missing DESeq
        "funbarRF",  # missing BioSeqClass bioseqclass is deprecated
        "facsDorit",  # missing prada, prada is deprecated
        "RNAither",  # missing prada
        "cellHTS2",  # missing prada
        "FunciSNP",  # missing FunciSNP.data, dep is depreceated
        "GeneExpressionSignature",  # missing PGSEA, dep is depreceated
        "Nebulosa",  # missing SeuratObject
        "RchyOptimyx",  # missing flowType, dep is depreceated
        "miRLAB",  # missing Roleswitch, dep is depreceated
        "PGA",  # missing rTANDEM, dep is deprecated
        "sapFinder",  # missing rTANDEM, dep is deprecated
        "shinyTANDEM",  # missing rTANDEM, dep is deprecated
        "msgbsR",  # missing easyRNASeq # easyRNAseq - there is a mac binary, but no source, and it's not in PACKAGES.gz. It does reappear in 3.13
        # indirect
        "RNAinteract",  # missing cellHTS2
        "gespeR",  # missing cellHTS2
        "imageHTS",  # missing cellHTS2
        "metagene",  # missing DBChIP
        "staRank",  # missing cellHTS2
        # third level
        "RNAinteractMAPK",  # missing RNAinteract
        "Imetagene",  # missing metagene
        "eiR",  # missing gespeR
    ],
    ("3.12", "<2021-01-23"): [
        "spicyR",  # missing spatstat.core # this shows up 2021-01-23 in mran
    ],
    ("3.12", "<2021-01-16"): [
        "spicyR",  # missing spatstat.geom # this show sup 2021-01-16
    ],
    ("3.12", "<2021-03-02"): [
        "systemPipeShiny",  # missing drawer # drawer shows up 2021-03-02
    ],
    ("3.12", "<2021-02-25"): [
        "systemPipeShiny",  # missing spsComps # this shows up 2021-02-25, # missing spsUtil # this shows up 2021-02-17
    ],
    ("3.13"): [
        # all with deprecated dependencies, or removed because they were deprecated before.
        "AbsFilterGSEA",  # missing DESeq
        "Tnseq",  # missing DESeq
        "apmsWAPP",  # missing DESeq
        "ArrayBin",  # missing SAGx
        "BACA",  # missing RDAVIDWebService
        "CompGO",  # missing RDAVIDWebService
        "MAMA",  # missing MergeMaid
        "MAMA",  # missing metaArray
        "REIDS",  # missing GenomeGraphs
        "funbarRF",  # missing BioSeqClass
        "methyAnalysis",  # missing genoset
        "humarray",  # missing genoset
        "synapterdata",  # missing synapter  # no source package
        "CytoTree",  # missing destiny # no source package
        "ctgGEM",  # missing destiny
        "methyAnalysis",  # missing bigmemoryExtras
        "phemd",  # missing destiny
        "greengenes13.5MgDb",  # missing metagenomeFeatures
        "ribosomaldatabaseproject11.5MgDb",  # missing metagenomeFeatures
        "silva128.1MgDb",  # missing metagenomeFeatures
    ],
    ("3.13", "<2021-08-16"): [
        # yulab.utils only shows up at this date
        "clusterProfiler",  # missing yulab.utils
        "ggtree",  # missing yulab.utils
        "meshes",  # missing yulab.utils
        "seqcombo",  # missing yulab.utils
        # indirect
        "AutoPipe",  # missing clusterProfiler
        "MoonFinder",  # missing clusterProfiler
        "RVA",  # missing clusterProfiler
        "immcp",  # missing clusterProfiler
        "CEMiTool",  # missing clusterProfiler
        "CeTF",  # missing clusterProfiler
        "DAPAR",  # missing clusterProfiler
        "GDCRNATools",  # missing clusterProfiler
        "IRISFGM",  # missing clusterProfiler
        "MAGeCKFlute",  # missing clusterProfiler
        "MoonlightR",  # missing clusterProfiler
        "PFP",  # missing clusterProfiler
        "RNASeqR",  # missing clusterProfiler
        "TCGAbiolinksGUI",  # missing clusterProfiler
        "TimiRGeN",  # missing clusterProfiler
        "bioCancer",  # missing clusterProfiler
        "conclus",  # missing clusterProfiler
        "debrowser",  # missing clusterProfiler
        "eegc",  # missing clusterProfiler
        "enrichTF",  # missing clusterProfiler
        "esATAC",  # missing clusterProfiler
        "famat",  # missing clusterProfiler
        "fcoex",  # missing clusterProfiler
        "methylGSA",  # missing clusterProfiler
        "miRspongeR",  # missing clusterProfiler
        "multiSight",  # missing clusterProfiler
        "netboxr",  # missing clusterProfiler
        "signatureSearch",  # missing clusterProfiler
        # missing ggtree, which is missing because of ggfun (see below) and yulab.utils
        "dowser",
        "enrichplot",  # missing ggtree
        "genBaRcode",  # missing ggtree
        "ggtreeExtra",  # missing ggtree
        "harrietr",  # missing ggtree
        "LymphoSeq",  # missing ggtree
        "miaViz",  # missing ggtree
        "MicrobiotaProcess",  # missing ggtree
        "philr",  # missing ggtree
        "RAINBOWR",  # missing ggtree
        "singleCellTK",  # missing ggtree
        "sitePath",  # missing ggtree
        "STraTUS",  # missing ggtree
        "systemPipeTools",  # missing ggtree
        "treekoR",  # missing ggtree
        # third level
        "signatureSearchData",  # missing signatureSearch
        "Prostar",  # missing DAPAR
        "SpidermiR",  # missing MAGeCKFlute
        "miRSM",  # missing miRspongeR
        "ChIPseeker",  # missing enrichplot
        "ReactomePA",  # missing enrichplot
        # fourth level
        "StarBioTrek",  # missing SpidermiR
        # fourth level
        "cinaR",  # missing ChIPseeker
        "ALPS",  # missing ChIPseeker
        "epihet",  # missing ReactomePA
        "profileplyr",  # missing ChIPseeker
        "scTensor",  # missing ReactomePA
        "pathwayTMB",  # missing clusterProfiler
        #
    ],
    ("3.13", "<2021-07-01"): [
        "ggtree",  # missing ggfun
    ],
}

# At one time I though we had to add packages back in that were present
# but inexplicably missing from PACKAGES.gz
# that didn't turn out to be the case, but the code is written...
package_patches = {
    # {'version': {'bioc|experiment|annotation': [{'name':..., 'version': ..., 'depends': [...], 'imports': [...], 'needs_compliation': True}]}}
}


# these get added in addition to the release date / archive date snapshots
# because sometimes the snapshots at release are simply missing packages.
# the value is why we added them.
extra_snapshots = {
    "3.1": {
        "2015-08-01": """DT, required by seqplots shows up on  '2015-06-09', but we strive to have only one date.
assertive.base  is required by OmicsMarkeR
"""
    },
    "3.2": {"2016-01-10": "ggrepel was added to CRAN 2016-01-10"},
    "3.5": {"2017-06-10": "dbplyr was added to CRAN 2017-06-09"},
}


@functools.total_ordering
class BioconductorRelease:
    """Data fetcher for one bioconductor release"""

    def __init__(self, version: Tuple[str, str], release_info):
        self.version = version
        self.str_version = ".".join(version)
        self.release_info = release_info
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
        self.blacklist = blacklist.get(self.str_version, None)
        self.patch_packages = package_patches.get(self.str_version, {})

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

    def get_cran_dates(self, cran_tracker):
        """Given our package list and what's in the archives,
        what dates actually had changes?

        This is the dates we need CRAN at.
        """
        result = set()
        available = cran_tracker.snapshots
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
        for str_date in extra_snapshots.get(self.str_version, {}):
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
        We'll use the next available date instead.
        """
        d = date.strftime("%Y-%m-%d")
        ok = sorted(
            [x for x in available_snapshots if x >= d]
        )  # lexographic sorting for the win
        if not ok:
            raise ValueError(
                "none >=", d, "latest available", sorted(available_snapshots)[-1]
            )
        return datetime.datetime.strptime(ok[0], "%Y-%m-%d").date()

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
            for kind, entries in self.patch_packages.items():
                for entry in entries:
                    out[entry["name"], entry["version"]] = entry["path"]

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

    def get_packages(self, kind, archive_date):
        if kind in ("experiment", "annotation", "software"):
            if kind == "software":
                kind = "bioc"
            source = self.store_path / f"packages.{kind}.json.gz"
        else:
            raise ValueError(kind)

        package_info = read_json(source)
        result = {}
        for (
            name,
            version,
            depends,
            imports,
            linking_to,
            needs_compilation,
        ) in package_info:
            if name in result:
                raise ValueError("Duplicate in packages", kind, name)
            result[name] = {
                "version": version,
                "depends": depends,
                "imports": imports,
                "linking_to": linking_to,
                "needs_compilation": needs_compilation,
            }
        if kind == "bioc":
            for package, version_dates in self.load_archive().items():
                if not package in result:
                    if package == "BiocInstaller":
                        # yeah...  you never distributed biocInstaller via bioconductor otherwise,
                        # so we're going to ignore you
                        continue
                    else:
                        raise ValueError(
                            "Package in archive that was not in PACKAGES.gz"
                        )

                for version, date in sorted(version_dates, key=lambda vd: vd[1]):
                    date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
                    if date <= archive_date:
                        result[package]["version"] = version
                        result[package]["archive"] = True
        for entries in self.patch_packages.get(kind, []):
            for entry in entries:
                print("patching", entry["name"])
                result[entry["name"]] = {
                    "version": entry["version"],
                    "depends": entry["depnds"],
                    "imports": entry["imports"],
                    "linking_to": entry["linking_to"],
                    "needs_compilation": entry["needs_compilation"],
                }

        return result

    def get_blacklist_at_date(self, date):
        key = f"{date:%Y-%m-%d}"
        print("get_blacklist_at_date", key)
        if (self.str_version, key) in blacklist:
            return blacklist[(self.str_version, key)]
        else:
            # consider all <= date as relevant
            res = set()
            for bl_key in blacklist:
                if (
                    isinstance(bl_key, tuple)
                    and (bl_key[0] == self.str_version)
                    and (bl_key[1][0] == "<")
                    and (key <= bl_key[1][1:])
                ):
                    res.update(blacklist[bl_key])
            return list(res)
