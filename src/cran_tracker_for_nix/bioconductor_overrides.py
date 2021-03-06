from .common import parse_date, format_date, nix_literal
import copy

"""Current roadblocks (ie. packages that block 'many' other packages
(the numbers are 'package instances' blocked and 'unique packages' blocked (by name)

stringi 21029 2020 - perhaps solvable by passing in icu correctly
nloptr 9087 1009 - we have solved this for later bioconductors, investigate
oligoClasses 5946 202 - does our patch work?
affy 3338  153 - patch anew where the current patch fails
RcppArmadillo 1348  1348 - that's std::random_device.get_entropy() it's missing??
rgdal 1008 62 - try again after promoting the attrs to 3.0
igraph 590 576 - find out what's wrong in 3.6
rpanel 471 - debug
V8 424 99 -  no clue.'
Rhdf5lib 356 184 - I feel like this should be 'straghtforward'ish, just get the right dependency &paths on the earlier bioconductors?
SDMTools 294 24 - already patched, rebuild should fix it 
GenomicFeatures 265
OrganismDbi 251
XMLRPC 224 - can we perhaps get the correct versions from github?
rhdf5 211 37
AnnotationHub 177 100
interactiveDisplayBase 152
rjags 152 39
pbdSLAP 145
units 142
ncdfFlow 121
Rsymphony 103
RGtk2 88
ROracle 74 - nothing to do here
OpenCL 68 -right dependencies?'
Rmosek 67 - proprietory product, won't support
ChIPpeakAnno 66 # biocinstaller, patchable?
rsbml 66
SVGAnnotation 59
XMLSchema 58

"""


nl = nix_literal


def dict_add(*dicts):
    res = {}
    for a in dicts:
        for k, v in a.items():
            res[k] = v
    return res


def match_override_keys(
    input_dict,
    version,
    date,
    debug=False,
    none_ok=False,
    default=dict,
    release_info=None,
):
    """Retrieve the right data from the overrides.
    Either an exact match,
    the latest date before,
    or the 'bc_version' entry.

    if that fails:
        Raise an exception if none_ok==False
    or:
        return default()


    release_info is used for sanity checking
    """
    if release_info is None:
        raise ValueError("release_info must be passed (or explicitly set to False)")
    res = _match_override_keys(
        input_dict, version, date, debug, none_ok, default, release_info
    )
    if isinstance(res, str):
        return res
    else:
        return res.copy()


def _match_override_keys(
    input_dict, version, date, debug, none_ok, default, release_info
):
    key = f"{date:%Y-%m-%d}"
    if debug:
        raise ValueError()
    if (version, key) in input_dict:
        if debug:
            print("exact match")
        return input_dict[(version, key)]
    else:
        matching = []
        for k in input_dict:
            if isinstance(k, tuple):
                (kversion, kdate) = k
                if kversion == version:
                    if kdate < key:
                        matching.append(kdate)
                    if release_info is not False and not (
                        release_info.start_date
                        <= parse_date(kdate)
                        < release_info.end_date
                    ):
                        raise ValueError(
                            "entry outside of bioconductor release range",
                            kdate,
                            format_date(release_info.start_date),
                            format_date(release_info.end_date),
                        )
        matching = sorted(matching)  # should be unnecessary
        if matching:
            if debug:
                print("using latest date: ", matching[-1])
            return input_dict[version, matching[-1]]

    if version in input_dict:
        if debug:
            print("falling back to version match")
        return input_dict[version]
    else:
        if none_ok:
            return default()
        else:
            raise KeyError(version, date)


def _get_last(collector, new_key, default, copy_anyway):
    """Abstraction to get the last entry.
    See inherit(...) for  semantics.
    """
    if isinstance(new_key, tuple):
        try:
            parse_date(new_key[1])
        except Exception as e:
            raise ValueError("invalid spec", new_key, e)
    last = default()
    if collector:
        last_key = collector[-1][0]
        if copy_anyway:
            last = collector[-1][1]
        else:
            if isinstance(last_key, tuple) and isinstance(new_key, tuple):
                if new_key[0] == last_key[0]:
                    if new_key[1] <= last_key[1]:
                        raise ValueError(
                            "adding later date after earlier date", new_key, last_key
                        )
                    else:
                        last = collector[-1][1]
            elif (
                isinstance(last_key, str)
                and isinstance(new_key, tuple)
                and new_key[0] == last_key
            ):
                last = collector[-1][1]
    return last


class Inheritor:
    def __init__(self, mode="dict"):
        """Collect values in an inherit from previous except if bioconductor changed
        way"""
        self.mode = mode
        self.collector = []
        if not mode in ("dict", "list", "nested_dicts"):
            raise ValueError("invalid mode")

    def inherit(self, new_key, new, remove=None, copy_anyway=False, rewriter=None):
        """
        Inherit the values from the last entry iff
            - copy_anway is set
        or
            - last_key == new_key[0] or last_key[0] == new_key[0]
            ie. the bioconductor version matches

        The rewriter get's passed the copied values, not the new ones

        For nested dict, remove must be (outer_key, inner_key)

        """
        assert isinstance(copy_anyway, bool)
        assert remove is None or isinstance(remove, list)
        assert isinstance(new_key, (tuple, str))
        if self.mode == "dict":
            assert isinstance(new, dict)
            gen = dict
        elif self.mode == "nested_dicts":
            assert isinstance(new, dict)
            for v in new.values():
                assert isinstance(v, dict)
            gen = dict
        elif self.mode == "list":
            assert isinstance(new, list)
            gen = list
        else:
            raise NotImplementedError()
        last = _get_last(self.collector, new_key, gen, copy_anyway)

        out = copy.deepcopy(last)  # necesasry for the nested ones.
        if rewriter is not None:
            out = rewriter(out)
        if remove:
            if self.mode == "dict":
                remove = set(remove)
                for k in remove:
                    if not k in out:
                        raise ValueError("unnecessary remove", k)
                out = {k: v for (k, v) in out.items() if k not in remove}
            elif self.mode == "nested_dicts":
                remove = set(remove)
                for k in remove:
                    if not k[0] in out:
                        raise ValueError("unnecessary remove (first level)", k)
                    if not k[1] in out[k[0]]:
                        raise ValueError("unnecessary remove (second level)", k)
                    del out[k[0]][k[1]]
                    if not out[k[0]]:
                        del out[k[0]]
            elif self.mode == "list":
                remove = set(remove)
                out = [x for x in out if x not in remove]
            else:
                raise NotImplementedError()
        if self.mode == "dict":
            out.update(new)
        elif self.mode == "nested_dicts":
            for k in new:
                if not k in out:
                    out[k] = {}
                for k2, v in new[k].items():
                    out[k][k2] = v
        elif self.mode == 'list':
            out.extend(new)
        else:
            raise NotImplementedError()
        self.collector.append((new_key, out))

    def to_dict(self):
        return {x[0]: x[1] for x in self.collector}


# all of these follow the following rules for their keys
comments = {
    "3.10": """The import package was renamed import_, since assert is a reserved keyword in nix""",
    "3.12": """The assert package was renamed assert_, since assert is a reserved keyword in nix""",
}

# overrides, default is by date
r_versions = {
    # key is bioconductor str_release,
    # or (bioconductor str_release, date)
    "3.0": "3.1.3",  # 3.1.1 by date, but 3.1.3 is the first in nixpkgs passing it's tests
    "3.3": "3.3.3",  # 3.3.0 by date , and 3.3.0 fails timezone tests, 3.3.1&2 fails because MASS is not available (we build without-recommended-packages...)
    "3.4": "3.3.3",  # 3.3.1 by date (but only for 13 days), and 3.3.1 and 3.3.2 fails their tests (because MASS in not available - we build without recommendoed packages...).
}

# override, because I want to decide this manually
nix_releases = {
    # we had to overwrite some font package shas/md5s for 15.09
    "2013-05-16": (
        "github:TyberiusPrime/nixpkgs?rev=f0d6591d9c219254ff2ecd2aa4e5d22459b8cd1c",
        "15.09 (Uses https://github.com/TyberiusPrime/nixpkgs instead of nixOS/nixpgs. Font sha256s needed patching)",
    ),
    "2016-03-31": (
        "github:nixOS/nixpkgs?rev=d231868990f8b2d471648d76f07e747f396b9421",
        "16.03",
    ),
    "2016-10-01": (
        "github:nixOS/nixpkgs?rev=f22817d8d2bc17d2bcdb8ac4308a4bce6f5d1d2b",
        "16.09",
    ),
    "2017-03-30": (
        "github:nixOS/nixpkgs?rev=1849e695b00a54cda86cb75202240d949c10c7ce",
        "17.03",
    ),
    "2017-09-29": (
        "github:nixOS/nixpkgs?rev=39cd40f7bea40116ecb756d46a687bfd0d2e550e",
        "17.09",
    ),
    "2018-04-04": (
        "github:nixOS/nixpkgs?rev=120b013e0c082d58a5712cde0a7371ae8b25a601",
        "18.03",
    ),
    "2018-10-05": (
        "github:nixOS/nixpkgs?rev=6a3f5bcb061e1822f50e299f5616a0731636e4e7",
        "18.09",
    ),
    "2019-04-08": (
        "github:nixOS/nixpkgs?rev=f52505fac8c82716872a616c501ad9eff188f97f",
        "19.03",
    ),
    "2019-10-09": (
        "github:nixOS/nixpkgs?rev=d5291756487d70bc336e33512a9baf9fa1788faf",
        "19.09",
    ),
    "2020-04-20": (
        "github:nixOS/nixpkgs?rev=5272327b81ed355bbed5659b8d303cf2979b6953",
        "20.03",
    ),
    "2020-10-25": (
        "github:nixOS/nixpkgs?rev=cd63096d6d887d689543a0b97743d28995bc9bc3",
        "20.09",
    ),
    "2021-05-31": (
        "github:nixOS/nixpkgs?rev=7e9b0dff974c89e070da1ad85713ff3c20b0ca97",
        "21.05",
    ),
}

# since we're not using 'nixpkgs that had this exact R'
# but 'nix pkgs x.y, patched to R z',
# we have to manage the patches ourselves
bp = ["./r_patches/no-usr-local-search-paths.patch"]
r_patches = {
    "3.2.2": bp + ["./r_patches/fix-tests-without-recommended-packages.patch"],
    "3.2.3": bp,
    "3.2.4": bp,
    "3.3.0": bp
    + [
        "./r_patches/zlib-version-check.patch",
        "./r_patches/3.3.0_fix_reg-test-1c.patch",  #    PR#17456 :   ^^ a version that also matches in a --disable-nl
    ],  # never in nixpkgs
    # "3.3.1": bp
    # + [
    # "./r_patches/zlib-version-check.patch",
    # this one fails 'base 'tests' without further details
    # ],  # never in nixpkgs
    # "3.3.2": bp + ["./r_patches/zlib-version-check.patch"], # won't pass tests
    "3.3.3": bp,
    "3.4.0": bp
    + [
        "./r_patches/fix-sweave-exit-code.patch",
        "./r_patches/3.3.0_fix_reg-test-1c.patch",
    ],
    "3.4.1": bp,
    "3.4.2": bp,
    "3.4.3": bp,
    "3.4.4": bp,
    "3.5.0": bp,
    "3.5.1": bp,
    "3.5.2": bp,
    "3.5.3": bp,
    "3.6.0": bp
    + [
        "./r_patches/aeb75e12863019be06fe6c762ab705bf5ed8b38c.patch"
    ],  # for the test suite
    "3.6.1": bp,
    "3.6.2": bp
    + [
        "stdenv.lib.optionals stdenv.hostPlatform.isAarch64 [./r_patches/0001-Disable-test-pending-upstream-fix.patch ]"
    ],  # Remove a test which fails on aarch64.
    "3.6.3": bp
    + [
        "stdenv.lib.optionals stdenv.hostPlatform.isAarch64 [./r_patches/0001-Disable-test-pending-upstream-fix.patch ]"
    ],  # Remove a test which fails on aarch64.
    "4.0.0": bp + ["./r_patches/fix-failing-test.patch"],
    "4.0.1": bp + ["./r_patches/fix-failing-test.patch"],
    "4.0.2": bp + ["./r_patches/fix-failing-test.patch"],
    "4.0.3": bp + ["./r_patches/fix-failing-test.patch"],
    "4.0.4": bp + ["./r_patches/fix-failing-test.patch"],
    "4.1.0": bp
    + [
        "./r_patches/7543c28b931db386bb254e58995973493f88e30d.patch",
        "./r_patches/7715c67cabe13bb15350cba1a78591bbb76c7bac.patch",
    ],
    "4.1.1": bp + ["./r_patches/skip-check-for-aarch64.patch"],
}

include_tz = """preCheck = "export TZ=CET; bin/Rscript -e 'sessionInfo()'";\n"""
additional_r_overrides = {
    "3.3.0": include_tz,  # by 17.09 this is in the nixpkgs R pkg, but not in 17.03 which we use for 3.4.0
    "3.4.0": include_tz,  # by 17.09 this is in the nixpkgs R pkg, but not in 17.03 which we use for 3.4.0
}
flake_overrides = {
    # R version - path in ./flakes/
    # get's merged with the default flake
    "3.5.0": "3.5.0",
    "4.0.0": "4.0.0",
    "4.1.0": "4.1.0",
}

missing_in_packages_gz = {
    "3.13": {
        "IntramiRExploreR": {
            "version": "1.14.",
            "depends": [],
            "imports": ["igraph", "FGNet", "knitr"],
            "linking_to": [],
            "suggests": [
                # "RDAVIDWebService",
                "gProfileR",
                "topGO",
                "org.Dm.eg.db",
                "rmarkdown",
                "testthat",
            ],
            "needs_compilation": False,
        }
    }
}


# packages that we kick out of the index
# per bioconductor release, and sometimes per date.
# the world ain't perfect ????
# note that we can kick from specific lists by prefixing with one of
# 'bioc_experiment--'.
# 'bioc_annotation--'.
# 'bioc_software--'. = bioconductor software
# 'cran--'.
# which is necessary when a package is in multiple but we don't want to kick all of them.
# not to be confused with broken packgaes, which simply don't build..p.

excluded_packages = Inheritor("dict")
excluded_packages.inherit(
    "3.0",
    {
        # repository doublettes
        "bioc_experiment--MafDb.ALL.wgs.phase1.release.v3.20101123": "newer in bioconductor-annotation",
        "bioc_experiment--MafDb.ESP6500SI.V2.SSA137.dbSNP138": "newer in bioconductor-annotation",
        "bioc_experiment--phastCons100way.UCSC.hg19": "newer in bioconductor-annotation",
        "cran--GOsummaries": "newer in bioconductor",
        "cran--gdsfmt": "newer in bioconductor",
        "cran--oposSOM": "newer in bioconductor",
    },
)
excluded_packages.inherit(
    "3.1",
    {
        "cran--saps": "newer in bioconductor",
        "cran--muscle": "newer in bioconductor",
    },
)
excluded_packages.inherit("3.2", {})
excluded_packages.inherit(
    "3.3",
    {
        "bioc_experiment--IHW": "newer in bioconductor-software",
    },
)
excluded_packages.inherit(
    "3.4",
    {
        "cran--PharmacoGx": "newer in bioconductor",
        "cran--statTarget": "newer in bioconductor",
        "cran--synergyfinder": "newer in bioconductor",
    },
)
excluded_packages.inherit("3.5", {})
excluded_packages.inherit(
    "3.6",
    {
        "bioc_software--JASPAR2018": "same package present in annotation",
    },
)
excluded_packages.inherit(
    "3.7",
    {
        "bioc_software--JASPAR2018": "newer package present in annotation",
        "bioc_software--MetaGxOvarian": "newer package present in experiment",
        "iontree": "deprecated in 3.6, removed in 3.7, but still in PACKAGES",
        "domainsignatures": "deprecated in 3.6, removed in 3.7, but still in PACKAGES",
    },
)
excluded_packages.inherit(
    "3.8",
    {
        "cran--mixOmics": "newer in bioconductor",
    },
)
excluded_packages.inherit("3.9", {})
excluded_packages.inherit("3.10", {})
excluded_packages.inherit("3.11", {})
excluded_packages.inherit("3.12", {})
excluded_packages.inherit(
    "3.13",
    {
        "metagenomeFeatures": "deprecated, but still in PACKAGES.gz",
        "cran--interacCircos": "newer in bioconductor",
        "cran--RCSL": "newer in bioconductor",
        "synapter": "no source package / build error according to bioconductor",
        "RDAVIDWebService": "deprecated, but still in PACKAGES.gz",
        "bigmemoryExtras": "deprecated, but still in PACKAGES.gz",
        "ggfun": "show up on 2021-07-02",
        "genoset": "deprecated, but still in PACKAGES.gz",
        "destiny": "no source package / build error according to bioconductor",
        "yulab.utils": "show up on 2021-08-17",
    },
)
excluded_packages.inherit(
    ("3.13", "2021-06-02"),
    {"gama": "removed from cran, but 'Clustering' still depends on it"},
    [],
)
excluded_packages.inherit(("3.13", "2021-07-02"), {}, ["ggfun"])
excluded_packages.inherit(("3.13", "2021-08-17"), {}, ["yulab.utils"])

excluded_packages.inherit(
    "3.14",
    {
        "synapter": "no source package / build error according to bioconductor",
        "metagenomeFeatures": "deprecated, not in 3.14, but still in the dependencies of other packages",
        "destiny": "no source package / build error according to bioconductor",
        "cran--interacCircos": "newer in bioconductor",
        "cran--RCSL": "newer in bioconductor",
    },
)
excluded_packages = excluded_packages.to_dict()

broken_packages = Inheritor()
broken_packages.inherit(
    "3.0",
    {
        # actual excludes
        "bigGP": "build is broken",
        "bioassayR": "wants RSQLite 1.0.0, which only appeared on 14-10-25",
        "BiocCheck": "requires BiocInstaller",
        "BRugs": "needs OpenBUGS, not in nixpkgs. Or in ubuntu. And the website change log says it hasn't updated since 2014. And the ssl certificate is expired.",
        "clpAPI": "missing clp library",
        "cudaBayesreg": "build is broken, needs nvcc",
        "cummeRbund": "wants RSQLite 1.0.0, which only appeared on 14-10-25",
        "doMPI": "build is broken with mpi trouble",
        "easyRNASeq": "needs LSD=3.0, which shows up on 2015-01-10",  # bc
        # "gWidgetstcltk": "tcl invalid command name 'font'",
        "HilbertVisGUI": "needs OpenCL, not available in nixpkgs 15.09",
        "HiPLARM": "build is broken, and the package never got any updates and was removed in 2017-07-02",
        "HSMMSingleCell": "needs VGAM  0.9.5, that shows up on 11-07",  # bc
        "interactiveDisplayBase": "wants to talk to bioconductor.org during installation",
        "jvmr": "broken build. Wants to talk to ddahl.org. Access /home/dahl during build",
        "ltsk": "missing lRlacpack und lRblas?",
        "MSeasyTkGUI": "Needs Tk",
        "MSGFgui": "needs shiny.=0.11.0 which shows up on 2015-02-11",  # bc
        "ncdfFlow": "no hdf5.dev in this nixpkgs",
        "NCmisc": "requires BiocInstaller",
        "nloptr": "nlopt library is broken in nixpkgs 15.09",
        "npRmpi": "build is broken with mpi trouble",
        # "oligoClasses": "requires biocInstaller during installation",
        "OpenCL": "needs OpenCL, not available in nixpkgs 15.09",
        "pbdSLAP": "build is broken with mpi trouble",
        "permGPU": "build is broken, needs nvcc",
        "plethy": "wants RSQLite 1.0.0, which only appeared on 14-10-25",
        "qtpaint": "missing libQtCore.so.4 and was listed as broken in nixpkgs 15.09",
        "QuasR": "requires BiocInstaller",
        "Rcplex": "unfree. Cplex not in nixpkgs",
        "RcppOctave": "build seems incompatible with octave version in nixpkgs.",
        # "rgdal": "not compatible with GDAL2 (which is what's in nixpkgs at this point)",
        "rhdf5": "no hdf5.dev in this nixpkgs",
        "Rmosek": "build is broken according to R/default.nix",
        "ROracle": "unfree. Oracle OCI not in nixpkgs",
        "rpanel": "build broken, wants DISPLAY?",
        "RQuantLib": "hquantlib ( if that's even the right package) is broken in nixpgks 15.09)",
        "RSAP": "misssing sapnwrfc.h",
        "rsbml": "libsmbl isn't packagd in nixpkg ",
        "seqplots": "needs shiny.=0.11.0 which shows up on 2015-02-11",  # bc
        "SOD": "build broken without libOpenCL",
        "SSOAP": "(omegahat / github only?)",
        "SVGAnnotation": "github only?",
        "sybilSBML": "configure checks for /usr/include and /usr/local/include - and possibly also needs libsmbl, judging by the name?",
        "trackViewer": "tcl issue",
        "UniProt.ws": "wants to talk to uniprot.org",
        "VariantFiltering": "wants RSQLite 1.0.0, which only appeared on 14-10-25",
        "XMLRPC": "(omegahat / github only?)",
        "XMLSchema": "(omegahat / github only?)",
    },
)
broken_packages.inherit(
    ("3.0", "2014-10-26"),
    {
        "metaMix": "R install fails with MPI problem",
    },
    # RSQLite 1.0.0 becomes available
    ["bioassayR", "plethy", "cummeRbund", "VariantFiltering"],
)

broken_packages.inherit(
    ("3.0", "2014-10-28"),
    {},
)

broken_packages.inherit(
    ("3.0", "2014-11-07"),
    {},
    ["HSMMSingleCell"],
)

broken_packages.inherit(
    ("3.0", "2015-01-11"),
    {
        "Rsymphony": "can't find SYMPHONY in nixpkgs",
        "V8": "mismatch between the nixpkgs version and what R wants",
        "iFes": "nvcc  Unsupported gpu architecture 'compute_10'",
    },
    [
        "easyRNASeq",
        "seqplots",
        "MSGFgui",
    ],  # could enable easyRNAseq on 2015-01-10 already.
)


broken_packages.inherit(
    ("3.1"),
    {
        #  simply missing
        # "affy": "requires BiocInstaller",
        "bigGP": "build is broken with mpi trouble",
        "BiocCheck": "requires BiocInstaller",
        "BRugs": "needs OpenBUGS, not in nixpkgs. Or in ubuntu. And the website change log says it hasn't updated since 2014. And the ssl certificate is expired.",
        "ChIPpeakAnno": "requires BiocInstaller",
        "cudaBayesreg": "build is broken, needs nvcc",
        "doMPI": "build is broken with mpi trouble",
        "HilbertVisGUI": "needs OpenCL, not available in nixpkgs 15.09",
        "HiPLARM": "build is broken, and the package never got any updates and was removed in 2017-07-02",
        "iFes": "nvcc  Unsupported gpu architecture 'compute_10'",
        "IlluminaHumanMethylation450k.db": "uses 'Defunct' function",
        "interactiveDisplayBase": "wants to talk to bioconductor.org during installation",
        "jvmr": "broken build. Wants to talk to ddahl.org. Access /home/dahl during build",
        "metaMix": "R install fails with MPI problem",
        "mongolite": "won't find openssl even with pkgs.openssl as dependency",
        "MSeasyTkGUI": "Needs Tk",
        "ncdfFlow": "no hdf5.dev in this nixpkgs",
        "nloptr": "nlopt library is broken in nixpkgs 15.09",
        # "oligoClasses": "requires biocInstaller during installation",
        "OpenCL": "needs OpenCL, not available in nixpkgs 15.09",
        "pbdSLAP": "build is broken with mpi trouble",
        "permGPU": "build is broken, needs nvcc",
        "qdap": "build segfaults",
        "qtpaint": "missing libQtCore.so.4 and was listed as broken in nixpkgs 15.09",
        "QuasR": "requires BiocInstaller",
        "Rcplex": "unfree. Cplex not in nixpkgs",
        "RcppAPT": "needs APT/Debian system",
        "RcppOctave": "build seems incompatible with octave version in nixpkgs.",
        # "rgdal": "not compatible with GDAL2 (which is what's in nixpkgs at this point)",
        "rhdf5": "no hdf5.dev in this nixpkgs",
        "Rmosek": "build is broken according to R/default.nix. And changed hash without version change.",
        "ROracle": "unfree. Oracle OCI not in nixpkgs",
        "rpanel": "can't find BWidget",
        "RQuantLib": "hquantlib ( if that's even the right package) is broken in nixpgks 15.09)",
        "RSAP": "misssing sapnwrfc.h",
        "rsbml": "libsmbl isn't packagd in nixpkg ",
        "Rsymphony": "can't find SYMPHONY in nixpkgs",
        # "SDMTools": "all downstreams fail with  undefined symbol: X",
        "SOD": "build broken without libOpenCL",
        "spectral.methods": "needs clusterify from Rssa which that package apperantly never had",
        "SSOAP": "(omegahat / github only?)",
        "SVGAnnotation": "github only?",
        "sybilSBML": "configure checks for /usr/include and /usr/local/include - and possibly also needs libsmbl, judging by the name?",
        "XMLRPC": "(omegahat / github only?)",
        "XMLSchema": "(omegahat / github only?)",
        "V8": "mismatch between the nixpkgs version and what R wants",
        "PAA": "requires Rcpp =0.11.6, which only became available on 2017-05-02",
        "bamboo": "shows up on CRAN at 2017-05-16",
        "seqplots": "DT, required by seqplots shows up on CRAN at 2017-06-09",
        "NetPathMiner": "Needs igraph = 1.0.0",  # bc
        "BioNet": "Needs igraph = 1.0.0",
        "assertive.base": "assertive.base showed up on 2015-07-15",
        "DT": "dt shows up on 2015-08-01",
        "clipper": "missing export in igraph. Needs 1.0.0, perhaps?",
        "NGScopy": "required changepoint version shows up 2015-10-01",
        #'WideLM': 'ncvv too old (missing option)',
    },
)
broken_packages.inherit(
    ("3.1", "2015-04-27"),
    {},
)


broken_packages.inherit(
    ("3.1", "2015-05-02"),
    {
        "h5": "no hdf5.dev in this nixpkgs",
    },
    [],
)

broken_packages.inherit(("3.1", "2015-05-16"), {}, ["bamboo"])
broken_packages.inherit(("3.1", "2015-06-09"), {}, ["seqplots"])
broken_packages.inherit(
    ("3.1", "2015-07-02"),
    {
        "iptools": "can't find boost::regex",
    },
)
broken_packages.inherit(
    ("3.1", "2015-07-07"),
    {},
    [
        "NetPathMiner",
        "BioNet",
        "clipper",
    ],
)
broken_packages.inherit(
    ("3.1", "2015-07-15"),
    {},
    ["assertive.base"],
)
broken_packages.inherit(("3.1", "2015-08-01"), {}, ["DT"])
broken_packages.inherit(
    ("3.1", "2015-10-01"),
    {
        "FIACH": "unknown output-sync type 'RTIFY_SOURCE=2'?",
        "regRSM": "MPI trouble",
        "Rblpapi": "blpapi is bloomberg professional API - unfree, not in nixpkgs",
    },
    ["NGScopy"],
)

broken_packages.inherit(  # start anew.
    ("3.2"),
    {
        # I expect these to stay broken
        "SSOAP": "(omegahat / github only?)",
        "XMLRPC": "(omegahat / github only?)",
        "XMLSchema": "(omegahat / github only?)",
        "SVGAnnotation": "github only?",
        "RcppAPT": "needs APT/Debian system",
        "RSAP": "misssing sapnwrfc.h",
        "HiPLARM": "build is broken, and the package never got any updates and was removed in 2017-07-02",
        "BRugs": "needs OpenBUGS, not in nixpkgs. Or in ubuntu. And the website change log says it hasn't updated since 2014. And the ssl certificate is expired.",
        "interactiveDisplayBase": "wants to talk to bioconductor.org during installation",
        "jvmr": "broken build. Wants to talk to ddahl.org. Access /home/dahl during build",
        # possibly unbreak when we leave 15.09 behind
        "ROracle": "unfree. Oracle OCI not in nixpkgs",
        "h5": "no hdf5.dev in this nixpkgs",
        "nloptr": "nlopt library is broken in nixpkgs 15.09",
        "RQuantLib": "hquantlib ( if that's even the right package) is broken in nixpgks 15.09)",
        "HilbertVisGUI": "needs OpenCL, not available in nixpkgs 15.09",
        "OpenCL": "needs OpenCL, not available in nixpkgs 15.09",
        "iptools": "can't find boost::regex",
        "cudaBayesreg": "build is broken, needs nvcc",
        # "SDMTools": "all downstreams fail with  undefined symbol: X",
        # "stringi": "Wants to download icudt55l.zip",
        "rsbml": "libsmbl isn't packagd in nixpkg ",
        "sybilSBML": "configure checks for /usr/include and /usr/local/include - and possibly also needs libsmbl, judging by the name?",
        # "affy": "requires BiocInstaller",
        "QuasR": "requires BiocInstaller",
        "Rsymphony": "can't find SYMPHONY in nixpkgs",  # that does come back up eventually, judging from 21.03
        "rhdf5": "no hdf5.dev in this nixpkgs",
        "rpanel": "build broken, wants DISPLAY?",
        "permGPU": "build is broken, needs nvcc",
        "IlluminaHumanMethylation450k.db": "uses 'Defunct' function",
        "OrganismDbi": "needs biocInstaller",
        # "oligoClasses": "requires biocInstaller during installation",
        "bigGP": "build is broken",
        "MSeasyTkGUI": "Needs Tk",
        "SOD": "build broken without libOpenCL",
        "Rblpapi": "blpapi is bloomberg professional API - unfree, not in nixpkgs",
        "doMPI": "build is broken with mpi trouble",
        "regRSM": "MPI trouble",
        "V8": "mismatch between the nixpkgs version and what R wants",
        "Rmosek": "build is broken according to R/default.nix",  # that does come back up eventually, judging from 21.03
        "Rcplex": "unfree. Cplex not in nixpkgs",
        "mongolite": "won't find openssl even with pkgs.openssl as dependency",
        "pbdSLAP": "build is broken with mpi trouble",
        # get better within this release
        "flowCore": "needs BH 1.60.0.1 - available starting 2015-12-29",
        "ggrepel": "was added only in 10-2016",
        "spliceSites": "needs rbamtools 2.14.3 - available",
        "iFes": "nvcc  Unsupported gpu architecture 'compute_10'",
        #'WideLM': 'ncvv too old (missing option)',
    },
)
broken_packages.inherit(("3.2", "2015-12-29"), {}, ["flowCore"])
broken_packages.inherit(
    ("3.2", "2016-01-10"),
    {
        "rjags": "Wrong JAGS version in nixpkgs 15.09",
        "rmumps": "needs libseq, can't find in nixpkgs 15.09",
    },
    ["ggrepel"],
)
broken_packages.inherit(("3.2", "2016-02-08"), {}, ["spliceSites"])

broken_packages.inherit(
    ("3.3"),  # 2016-05-04
    {
        "XMLRPC": "(omegahat / github only?)",
        "SVGAnnotation": "github only?",
        "nloptr": "nlopt library is broken in nixpkgs 16.03",
        "ChemmineOB": "openbabel is broken in nixpkgs 16.03",
        "RcppOctave": "octave-package segfaults during build",
    },
)

broken_packages.inherit(  # start anew.
    ("3.4"),
    {
        "XMLRPC": "(omegahat / github only?)",
        "SVGAnnotation": "github only?",
        #
        "nloptr": "nlopt library is broken in nixpkgs 17.04",
        "ChemmineOB": "openbabel is broken in nixpkgs 17.04",
    },
)
broken_packages.inherit(
    ("3.5"),  # 2017-04-25
    {
        "AnnotationHub": "missing BiocInstaller - todo: patch?",
        "BiocCheck": "requires BiocInstaller",  # todo: patch?
        "BRugs": "needs OpenBUGS, not in nixpkgs. Or in ubuntu. And the website change log says it hasn't updated since 2014. And the ssl certificate is expired.",
        "ccmap": "missing BiocInstaller - todo: patch?",
        "chinese.misc": "Wants write access to nix store. Possibly patchable",
        "clpAPI": "missing clp library",
        "CountClust": "object 'switch_axis_position' is not exported by 'namespace:cowplot', try newer cowplot after 2017-07-30",
        "cudaBayesreg": "build is broken, needs nvcc",
        "dbplyr": "only shows up on 2017-06-10",
        "devEMF": "undefined symbol: XftCharExists",
        "EMCC": "'template with c linkage' error",
        "GenomicFeatures": "needs Rsqlite=2.0, try after 2017-06-19",
        "gpuR": "OpenCL",
        "h5": "won't find h5c++",
        "HiPLARM": "build is broken, and the package never got any updates and was removed in 2017-07-02",
        "IlluminaHumanMethylation450k.db": 'build fails with "fun is defunct"',
        "interactiveDisplay": "tries to access bioconductor.org",
        "InterfaceqPCR": "segfaults on build",
        "jvmr": "broken build. Wants to talk to ddahl.org. Access /home/dahl during build",
        "limmaGUI": "install needs BiocInstaller",  # todo: patch
        "lpsymphony": "cpp errors",
        "mcPAFit": "objects 'GenerateNet', 'GetStatistics', 'PAFit' are not exported by 'namespace:PAFit'",
        "MonetDBLite": "missing libmonetdb5",
        "mongolite": "mongolite.so: undefined symbol: BIO_push",
        "ncdfFlow": "no hdf5.dev in this nixpkgs, possibly patchable?",
        "nloptr": "nlopt library is broken in nixpkgs 17.03",
        "odbc": "can't find unixodbc-dev, possibly patchable?",  # todo
        # "oligoClasses": "requires biocInstaller during installation",  # todo: pach?
        "OpenCL": "needs OpenCL, not available in nixpkgs 17.03",
        "pbdBASE": "requires blasc_gridinfo from intel?",
        "permGPU": "build is broken, needs nvcc",
        "plink": "object 'windows' is not exported by 'namespace:grDevices'. Try newer version at 2017-04-26",
        "psygenet2r": "needs biocinstaller",  # todo patch?
        # "qtpaint": "build failure",
        "QUBIC": "compilation failure, was not updated within this BC release",
        "randstr": "queries www.random.org",
        "Rblpapi": "blpapi is bloomberg professional API - unfree, not in nixpkgs",
        "Rcplex": "unfree. Cplex not in nixpkgs",
        "RcppAPT": "needs APT/Debian system",
        "RcppOctave": "build seems incompatible with octave version in nixpkgs.",
        "remoter": "error: file '~' does not exist",
        "rhdf5": "wrong hdf5.dev version?",
        "rlo": "needs python&numpy",  # todo: decide how we take the python to use
        "Rmosek": "needs 'mosek', unavailable",
        "rmumps": "needs libseq, can't find in nixpkgs 17.03",
        "ROracle": "unfree. Oracle OCI not in nixpkgs",
        "rpanel": "build broken, wants DISPLAY?",
        "RQuantLib": "hquantlib is a haskell package - don't think that's what's required?",
        "RSAP": "misssing sapnwrfc.h",
        "rsbml": "libsmbl isn't packagd in nixpkg",
        "RSQLServer": "object 'src_translate_env' is not exported by 'namespace:dplyr', try after 2017-06-09 for newer dpylr",
        "Rsymphony": "can't find SYMPHONY in nixpkgs",  # that does come back up eventually, judging from 21.03
        # "SDMTools": "all downstreams fail with  undefined symbol: X",
        "SnakeCharmR": "needs python",  # Todo
        "SVGAnnotation": "github only?",
        "sybilSBML": "configure checks for /usr/include and /usr/local/include - and possibly also needs libsmbl, judging by the name?",
        "tesseract": "missing baseapi.h?",
        "textTinyR": "boost trouble",  # todo
        # "V8": "mismatching
        "warbleR": "trying to use CRAN without setting a mirror",
        "XMLRPC": "(omegahat / github only?)",
    },
)
broken_packages.inherit(
    ("3.5", "2017-04-25"),
    {
        # "INLA": "never on cran",
    },
)
broken_packages.inherit(("3.5", "2017-04-26"), {}, ["plink"])
broken_packages.inherit(("3.5", "2017-06-09"), {}, ["dbplyr"])  # or is it -10?
broken_packages.inherit(("3.5", "2017-06-19"), {}, ["GenomicFeatures"])  # or is it -10?
broken_packages.inherit(("3.5", "2017-06-30"), {}, ["mcPAFit"])  # new release, maybe...
broken_packages.inherit(
    ("3.5", "2017-07-30"), {}, ["CountClust"]
)  # new cowplot release


broken_packages.inherit(  # start anew.
    ("3.6"),  # 2017-10-31
    {
        "AnnotationHub": "missing BiocInstaller - todo: patch?",
        "bgx": "c error",
        "bigmemoryExtras": "needs bigmemory = 4.5.31, released 2017-11-21",
        "BiocCheck": "missing BiocInstaller - todo: patch?",
        "BiocSklearn": "needs python & sklearn",  # todo
        "BRugs": "needs OpenBUGS, not in nixpkgs. Or in ubuntu. And the website change log says it hasn't updated since 2014. And the ssl certificate is expired.",
        "ccmap": "missing BiocInstaller - todo: patch?",
        "chinese.misc": "Wants write access to nix store. Possibly patchable",
        "clpAPI": "missing clp library",
        "cudaBayesreg": "build is broken, needs nvcc",
        "devEMF": "undefined symbol: XftCharExists",
        "flipflop": "cpp template error",
        "genomation": "needs Rcpp 0.12.14, available 2017-11-24",
        "gpuR": "needs opencl",
        "h5": "can't find h5c++",
        "humarray": "needs biocInstaller",
        # "igraph": "C error in compilation",
        "interactiveDisplay": "tries to access bioconductor.org",
        "kmcudaR": "build is broken, needs nvcc",
        "limmaGUI": "install needs BiocInstaller",  # todo: patch
        "metScanR": "could not resolve hostname",
        "mongolite": "mongolite.so: undefined symbol: BIO_push",
        "MutationalPatterns": "needs cowplot 0.9.2, available 2017-12-18",
        # "nloptr": "undefined symbol:  nlopt_set_ftol_abs- version mismatch?",
        "odbc": "can't find unixodbc-dev, possibly patchable?",  # todo
        # "oligoClasses": "requires biocInstaller during installation",
        "Onassis": "Vignette engine 'knitr' is not registered by any of the packages 'knitr'",
        "OpenCL": "needs OpenCL, not available in nixpkgs 17.03",
        "OrganismDbi": "needs biocInstaller",
        "pbdBASE": "requires blasc_gridinfo from intel?",
        "permGPU": "build is broken, needs nvcc",
        "PReMiuM": "compilation failure",
        # "qtpaint": "build failure",
        "QuasR": "needs biocInstaller",
        "randstr": "queries www.random.org",
        "Rblpapi": "blpapi is bloomberg professional API - unfree, not in nixpkgs",
        "Rcplex": "unfree. Cplex not in nixpkgs",
        "RcppAPT": "needs APT/Debian system",
        "RcppOctave": ["zlib", "bzip2", "icu", "lzma", "pcre", "octave"],
        "redux": "needs hiredis, not found in nixpkgs",
        "remoter": "error: file '~' does not exist",
        "rhdf5": "fails to compile, wrong type?",
        "Rhdf5lib": " no libhdf5.a found",
        "rlo": "needs python&numpy",
        "Rmosek": "needs 'mosek', unavailable",
        "rmumps": "needs libseq, can't find in nixpkgs 17.09",
        "ROracle": "unfree. Oracle OCI not in nixpkgs",
        "rpanel": "can't find BWidget",
        "RQuantLib": "hquantlib is a haskell package - don't think that's what's required?",
        "RSAP": "misssing sapnwrfc.h",
        "rsbml": "libsmbl isn't packagd in nixpkg",
        "rstan": "template error",
        "Rsymphony": "can't find SYMPHONY in nixpkgs",
        # "SDMTools": "all downstreams fail with  undefined symbol: X",
        "sybilSBML": "configure checks for /usr/include and /usr/local/include - and possibly also needs libsmbl, judging by the name?",
        "tesseract": "missing baseapi.h?",
        "textTinyR": "boost trouble",  # todo
        "V8": "v8 version mismatch between R package and nixpkgs",
        "x12": "'error: argument is of length zero'?",
        "XMLRPC": "(omegahat / github only?)",
        "yearn": "needs BiocInstaller",  # todo patch
    },
)
broken_packages.inherit(("3.6", "2017-11-21"), {}, ["bigmemoryExtras"])  # start anew.
broken_packages.inherit(("3.6", "2017-11-24"), {}, ["genomation"])  # start anew.
broken_packages.inherit(  # start anew.
    ("3.6", "2017-12-18"), {}, ["MutationalPatterns"]
)


broken_packages.inherit(  # start anew.
    ("3.7"),  # 2018-05-1
    {
        #
        "AnnotationHub": "missing BiocInstaller - todo: patch?",
        "Cyclops": "error: 'complex' in namespace 'std' does not name a template type",
        "pbdSLAP": "mpi trouble",
        "esATAC": "requires BiocInstaller",
        "facopy": "object 'setting.graph.attributes' is not exported by 'namespace:DOSE'",
        "bgx": "c error",
        "bsts": "error: 'class BOOM::StateSpaceModelBase' has no member named 'one_step_prediction_errors'",
        "bigGP": "build is broken",
        "BiocCheck": "requires BiocInstaller",
        "BRugs": "needs OpenBUGS, not in nixpkgs. Or in ubuntu. And the website change log says it hasn't updated since 2014. And the ssl certificate is expired.",
        "ccmap": "missing BiocInstaller - todo: patch?",
        # "chinese.misc": "Wants write access to nix store. Possibly patchable",
        "ChIPpeakAnno": "requires BiocInstaller",
        "clpAPI": "missing clp library",
        "ClusterSignificance": "needs princurve =2.0.4 available starting 2018-07-15",
        "cudaBayesreg": "build is broken, needs nvcc",
        "devEMF": "undefined symbol: XftCharExists",
        "dSimer": "no matching function for call to 'std::tr1::unordered_map<std::__cxx11::basic_string<char, float>::ins",  # and no update within this release
        "flipflop": "cpp template error",
        "ggtree": "needs ggplot = 2.2.1.9000, try after 2018-07-03",
        "Rmpi": "undefined symbol: mpi_universe_size?",  # todo : figure out and fix
        "gpuR": "needs opencl",
        "HBP": "requires biocInstaller during installation",
        "h5": "no hdf5.dev in this nixpkgs",
        "interactiveDisplay": "tries to access bioconductor.org",
        "kmcudaR": "build is broken, needs nvcc",
        # "oligoClasses": "requires biocInstaller during installation",
        "Onassis": "Vignette engine 'knitr' is not registered by any of the packages 'knitr'",
        "OpenCL": "needs OpenCL, not available in nixpkgs 17.03",
        "OrganismDbi": "needs biocInstaller",
        "pathifier": "needs princurve =2.0.4 available starting 2018-07-10",
        "permGPU": "build is broken, needs nvcc",
        # "qtpaint": "build failure",
        "psygenet2r": "needs biocinstaller",  # todo patch?
        "QuasR": "requires BiocInstaller",
        "randstr": "queries www.random.org",
        "Rblpapi": "blpapi is bloomberg professional API - unfree, not in nixpkgs",
        "Rcplex": "unfree. Cplex not in nixpkgs",
        "RcppAPT": "needs APT/Debian system",
        "ReporteRs": "fgmutils 0.9.4 needs that,though ReporteRs (and ReporteRsjars) is no longer in CRAN",
        # "ReporteRsjars": "removed from cran, but still in packages",
        "Rhdf5lib": " no libhdf5.a found",
        "rlo": "Needs python/numpy",
        "Rmosek": "needs 'mosek', unavailable",
        "ROracle": "unfree. Oracle OCI not in nixpkgs",
        "rpanel": "can't find BWidget",
        "RQuantLib": "hquantlib is a haskell package - don't think that's what's required?",
        "RSAP": "misssing sapnwrfc.h",
        "rsbml": "libsmbl isn't packagd in nixpkg",
        "rsunlight": "object 'ignore.case' is not exported by 'namespace:stringr'. Try after 2018-05-10",
        "Rsymphony": "can't find SYMPHONY in nixpkgs",
        "rTANDEM": "cpp error",
        # "SDMTools": "all downstreams fail with  undefined symbol: X",
        "sybilSBML": "configure checks for /usr/include and /usr/local/include - and possibly also needs libsmbl, judging by the name?",
        "V8": "v8 version mismatch between R package and nixpkgs",
        "x12": "'error: argument is of length zero'?",
        "yearn": "needs BiocInstaller",  # todo patch
        "zoon": "'error: 'class BOOM::StateSpaceModelBase' has no member named 'one_step_prediction_errors'",
    },
)

broken_packages.inherit(
    ("3.7", "2018-05-10"),
    {},
    ["rsunlight"],
)
broken_packages.inherit(
    ("3.7", "2018-05-26"),
    {"GenABEL.data": "removed from cran, but still in packages"},
)

broken_packages.inherit(
    ("3.7", "2018-07-03"),
    {},
    ["ggtree"],
)
broken_packages.inherit(
    ("3.7", "2018-07-10"),
    {},
    ["pathifier"],
)

broken_packages.inherit(
    ("3.7", "2018-07-15"),
    {},
    ["ClusterSignificance"],
)

broken_packages.inherit(
    ("3.7", "2018-07-16"),
    {"ReporteRsjars": "removed from cran, but still in packages"},
)

broken_packages.inherit(
    "3.8",  # start anew. # 2018-10-31
    {
        "anyLib": "needs BiocInstaller",
        "bgx": "c error",
        "BiocSklearn": "needs python&sklearn",
        "BRugs": "needs OpenBUGS, not in nixpkgs. Or in ubuntu. And the website change log says it hasn't updated since 2014. And the ssl certificate is expired.",
        "clpAPI": "missing clp library",
        "cudaBayesreg": "build is broken, needs nvcc",
        "devEMF": "undefined symbol: XftCharExists",
        "dSimer": "no matching function for call to 'std::tr1::unordered_map<std::__cxx11::basic_string<char, float>::ins",  # and no update within this release
        "flipflop": "cpp template error",
        "freetypeharfbuzz": "Downloads from github",
        "GENEAsphere": "object 'epoch.apply' is not exported by 'namespace:GENEAread, try after 2018-11-16",
        "GEOquery": "needs readr >= 1.3.1, try after 2018-12-22",
        "ggtree": "object 'as_tibble' is not exported by 'namespace:tidytree",  # todo: find out when  it's back...
        "gpuR": "needs opencl",
        "greengenes13.5MgDb": 'invalid class "MgDb" object: 1: invalid object for slot "taxa" in class "MgDb":',
        # "gWidgetstcltk": ' [tcl] invalid command name "font".',
        "h5": "no hdf5.dev in this nixpkgs",
        "HBP": "needs BiocInstaller",
        "interactiveDisplay": "tries to access bioconductor.org",
        "kazaam": "mpi trouble",
        "kmcudaR": "build is broken, needs nvcc",
        # "multibiplotGU" "gWidgets2tcltk": ' [tcl] invalid command name "font".',
        # "nloptr": "undefined symbol:  nlopt_set_ftol_abs- version mismatch?",  # todo: I suspect something different behind this
        "OpenCL": "needs OpenCL, not available in nixpkgs 18.09",
        # "optbdmaeAT": '[tcl] invalid command name "font".',
        # "optrcdmaeAT": '[tcl] invalid command name "font".',
        "pbdSLAP": "build is broken with mpi trouble",
        "permGPU": "build is broken, needs nvcc",
        # "qtpaint": "build failure, can't find -lstd?",
        "randstr": "queries www.random.org",
        "Rblpapi": "blpapi is bloomberg professional API - unfree, not in nixpkgs",
        "Rcplex": "unfree. Cplex not in nixpkgs",
        "RcppAPT": "needs APT/Debian system",
        "RcppMeCab": "undefined symbol: mecab_destroy",
        "ReporteRs": "fgmutils 0.9.4 needs that,though ReporteRs (and ReporteRsjars) is no longer in CRAN",
        # "ReporteRsjars": "no longer in CRAN",
        "RGtk2": "needs gtk 2.8, nixpkgs 18.09 has 2.24",
        "Rhdf5lib": " no libhdf5.a found",
        "ribosomaldatabaseproject11.5MgDb": 'error: invalid class "MgDb" object: 1: invalid object for slot "taxa" in class "MgDb": got class "tbl_dbi",',  # todo This might work again when metagenomeFeatures is updated? some time after 2019-01-31...
        "rlo": "needs python&numpy",
        "Rmosek": "needs 'mosek', unavailable",
        "Rmpi": "undefined symbol: mpi_universe_size?",  # todo : figure out and fix
        "ROracle": "unfree. Oracle OCI not in nixpkgs",
        "rpanel": "can't find BWidget",
        "rPython": "needs a python",
        "RQuantLib": "hquantlib is a haskell package - don't think that's what's required?",
        "rsbml": "libsmbl isn't packagd in nixpkg",
        "Rsymphony": "can't find SYMPHONY in nixpkgs",
        "rTANDEM": "cpp error",
        "silva128.1MgDb": 'invalid class "MgDb" object: 1: invalid object for slot "taxa" in class "MgDb":',
        "sybilSBML": "configure checks for /usr/include and /usr/local/include - and possibly also needs libsmbl, judging by the name?",
        "udunits2": "needs udunits2 but only udunits is in nixpkgs",
        "units": "needs udunits2 but only udunits is in nixpkgs",
        "x12": "'error: argument is of length zero'?",
        "yearn": "needs BiocInstaller",  # todo patch
    },
)
broken_packages.inherit(("3.8", "2018-11-16"), {}, ["GENEAsphere"])
broken_packages.inherit(("3.8", "2018-12-22"), {}, ["GEOquery"])

broken_packages.inherit(  # start anew. - 2019-03-05
    ("3.9"),
    {
        "ajv": "  ** testing if installed package keeps a record of temporary installation path-> cannot opon the connection?",
        "BiocSklearn": "needs python&sklearn",
        "BRugs": "needs OpenBUGS, not in nixpkgs. Or in ubuntu. And the website change log says it hasn't updated since 2014. And the ssl certificate is expired.",
        "charm": "  Error: object 'ebayes' is not exported by 'namespace:limma', try after 2019-05-18",
        "clpAPI": "missing clp library",
        "cola": "needs circlize 0.4.7, available 2021-08-22",
        "colormap": "  ** testing if installed package keeps a record of temporary installation path-> cannot opon the connection?",
        "devEMF": "undefined symbol: XftCharExists",
        "freetypeharfbuzz": "Downloads from github",
        "gpuR": "needs opencl",
        "gtrellis": "needs circlize 0.4.8, available 2021-10-22",
        "ical": "  ** testing if installed package keeps a record of temporary installation path-> cannot opon the connection?",
        "ImmuneSpaceR": "needs ggplot 3.2.0, try after 2019-06-17",
        "infercnv": "needs python",  # todo
        "interactiveDisplay": "tries to access bioconductor.org",
        "jsonld": "  ** testing if installed package keeps a record of temporary installation path-> cannot opon the connection?",
        "jsonvalidate": "  ** testing if installed package keeps a record of temporary installation path-> cannot opon the connection?",
        "js": "  ** testing if installed package keeps a record of temporary installation path-> cannot opon the connection?",
        "kazaam": "mpi trouble",
        "kmcudaR": "build is broken, needs nvcc",
        "lawn": "fail with '# CHECK_EQ(0, result) failed\\n Expected: 0\\n Found: 22' - possibly a V8 version issue",
        "MAVE": "no matching function call",
        "mnlogit": " Error: object 'index' is not exported by 'namespace:mlogit', try after 2019-06-03",
        "nloptr": "undefined symbol: nlopt_remove_equality_constraints - version mismatch?",
        "OpenCL": "needs OpenCL, not available in nixpkgs 19.03",
        "opencv": "error: 'pencilSketch' was not declared in this scope",
        "pbdSLAP": "build is broken with mpi trouble",
        "permGPU": "build is broken, needs nvcc",
        "plateCore": "The prototype for class \"flowPlate\" has undefined slot(s): 'plateConfig'",
        "PrInCE": "needs tidyr >=0.8.99, try after 2019-09-12",
        # "qtpaint": "build failure, can't find -lstd?",
        "randomcoloR": "  ** testing if installed package keeps a record of temporary installation path-> cannot opon the connection?",
        "randstr": "queries www.random.org",
        "Rblpapi": "blpapi is bloomberg professional API - unfree, not in nixpkgs",
        "Rcplex": "unfree. Cplex not in nixpkgs",
        "RcppAPT": "needs APT/Debian system",
        "RcppMeCab": "undefined symbol: mecab_strerror",
        "Rcwl": "needs cwltool, not available in nixpkgs 19.03",
        "RGtk2": "needs gtk 2.8, nixpkgs 18.09 has 2.24",
        "rlo": "needs python&numpy",
        "Rmpi": "undefined symbol: mpi_universe_size?",  # todo : figure out and fix
        "ROracle": "unfree. Oracle OCI not in nixpkgs",
        "rpanel": "can't find BWidget",
        "RQuantLib": "hquantlib is a haskell package - don't think that's what's required?",
        "rsbml": "libsmbl isn't packagd in nixpkg",
        "Rsymphony": "can't find SYMPHONY in nixpkgs",  # that does come back up eventually, judging from 21.03
        "sglOptim": "compilation failure",
        "sybilSBML": "configure checks for /usr/include and /usr/local/include - and possibly also needs libsmbl, judging by the name?",
        # these are all V8 failures
        "traitdataform": " wants to talk to raw.githubuser.content.com",
        "V8": " every downstream package fails with '# CHECK_EQ(0, result) failed\\n Expected: 0\\n Found: 22' - possibly a V8 version issue, but using 3_14 doesn't help",
        "wrswoR.benchmark": "talks go raw.githubusercontent.com",
        "x12": "'error: argument is of length zero'?",
    },
)
broken_packages.inherit(("3.9", "2019-05-18"), {}, ["charm"])


broken_packages.inherit(("3.9", "2019-06-03"), {}, ["mnlogit"])

broken_packages.inherit(("3.9", "2019-06-17"), {}, ["ImmuneSpaceR"])


broken_packages.inherit(("3.9", "2019-08-22"), {}, ["cola"])
broken_packages.inherit(("3.9", "2019-09-12"), {}, ["PrInCE"])


broken_packages.inherit(("3.9", "2019-10-22"), {}, ["gtrellis"])

broken_packages.inherit(  # start anew.
    ("3.10"),  # 2019-10-30
    {
        "BRugs": "needs OpenBUGS, not in nixpkgs. Or in ubuntu. And the website change log says it hasn't updated since 2014. And the ssl certificate is expired.",
        "Rblpapi": "blpapi is bloomberg professional API - unfree, not in nixpkgs",
        "Rcplex": "unfree. Cplex not in nixpkgs",
        "RcppAPT": "needs APT/Debian system",
        "RQuantLib": "hquantlib ( if that's even the right package) is broken in nixpgks 15.09)",
        "rmumps": "needs libseq, can't find in nixpkgs 19.09",
        "ROracle": "unfree. Oracle OCI not in nixpkgs",
        "rsbml": "libsmbl isn't packagd in nixpkg",
        "Rsymphony": "can't find SYMPHONY in nixpkgs",
        "sybilSBML": "configure checks for /usr/include and /usr/local/include - and possibly also needs libsmbl, judging by the name?",
        "charm": "deprecated / removed, but still in packages",
        "reactable": "only shows up on 2019-11-21",
        "V8": " every downstream package fails with '# CHECK_EQ(0, result) failed\\n Expected: 0\\n Found: 22' - possibly a V8 version issue, but using 3_14 doesn't help",
        "freetypeharfbuzz": "Downloads from github",
        "devEMF": "undefined symbol: XftCharExists",
        "pbdSLAP": "mpi trouble",
        # "bigGP": "undefined symbol: mpi_universe_size?",
        # "exifr": "Tries to talk to paleolimbot.github.io",
        # "h5": "won't find h5c++",
        "kazaam": "mpi trouble",
        # "kmcudaR": "build is broken, needs nvcc",
        "nloptr": "undefined symbol: nlopt_remove_equality_constraints - version mismatch?",
        "kmcudaR": "build is broken, needs nvcc",
        "permGPU": "build is broken, needs nvcc",
        # "RcppArmadillo": "undefined symbol: _ZNKSt13random_device13_M_getentropyEv",
        # "redux": "needs hiredis, not found in nixpkgs",
        # "regRSM": "undefined symbol: mpi_universe_size?",
        "rlo": "needs python&numpy",
        "BiocSklearn": "needs python&sklearn",
        "Rmpi": "undefined symbol: mpi_universe_size?",
        "rpanel": "build broken, wants DISPLAY?",
        "rphast": "can't find prce_compile / build problems - and disappears on 2020-03-03 anyway",
        "trio": "requires logiRec 1.6.1",
        "wrswoR.benchmark": "talks to github during install",
        "randstr": "queries www.random.org",
        "x12": "'error: argument is of length zero'?",
        "Rcwl": "needs cwltool, not available in 19.09",
        "gpuR": "OpenCL missing?",
        "plyranges": "needs tidyselect =1.0.0 (available 2020-01-28)",
        "BiocPkgTools": "needs tidyselect =1.0.0 (available 2020-01-28)",
        "splatter": "needs checkmate 2.0.0 (available 2020-02-07)",
        "apcf": "won't find gcs.csv in GDAL_DATA path even though it's there and pcs.csv is being found",
        "GeneBook": "attempts to contact github",
        "traitdataform": "attempts to contact 'https://raw.githubusercontent.com/EcologicalTraitData/ETS/v0.9/ETS.csv'",
        # "RNAmodR": "uses AnnotationHub / net access on install",  # Todo
        "mlm4omics": "won't compile with current stan",
    },
)
broken_packages.inherit(("3.10", "2019-11-08"), {}, ["trio"])  # see above for logiRec
broken_packages.inherit(("3.10", "2019-11-21"), {}, ["reactable"])
broken_packages.inherit(("3.10", "2019-12-30"), {}, [])  # update, might start to work
broken_packages.inherit(
    ("3.10", "2020-01-28"), {}, ["plyranges", "BiocPkgTools"]
)  # see above for tidyselect
broken_packages.inherit(
    ("3.10", "2020-02-07"), {}, ["splatter"]
)  # see above for checkmate


broken_packages.inherit(
    ("3.10", "2020-03-03"),
    {
        "rphast": "removed from CRAN on 2020-03-03, but dependencies were not removed",
    },
)


broken_packages.inherit(  # start anew.
    ("3.11"),  # 2020-04-28
    {
        "BRugs": "needs OpenBUGS, not in nixpkgs. Or in ubuntu. And the website change log says it hasn't updated since 2014. And the ssl certificate is expired.",
        "rGEDI": "'https://github.com/caiohamamura/libclidar/archive/v0.4.0.tar.gz': status was 'Couldn't resolve host name'",
        "terra": "ERROR 1: PROJ: proj_create_from_database: Cannot find proj.db",  # tod: probably fixable
        "waddR": "tries to write to $home",
        "bsseq": "needs Iranges>=2.22.2. Try after 2020-04-28",
        "traitdataform": "attempts to contact 'https://raw.githubusercontent.com/EcologicalTraitData/ETS/v0.9/ETS.csv'",
        "rsbml": "libsmbl isn't packagd in nixpkg ",
        "gpuR": "OpenCL missing?",
        "RQuantLib": "hquantlib is a haskell package - don't think that's what's required?",
        "dmdScheme": "cannot open URL 'https://github.com/Exp-Micro-Ecol-Hub/dmdSchemeRepository/raw/master/schemes/dmdScheme_0.9.5.tar.gz'",
        "Rcwl": "needs cwltool, not available in nixpkgs 20.03",
        "tricolore": "Error: object 'theme' is not exported by 'namespace:ggtern'",
        "devEMF": "undefined symbol: XftCharExists",
        "doMPI": "build is broken with mpi trouble",
        "freetypeharfbuzz": "Downloads from github",
        "gpuMagic": "needs opencl",
        "rdomains": " object 'predict.cv.glmnet' is not exported by 'namespace:glmnet', try after 2020-06-16?",
        "kazaam": "mpi trouble",
        "kmcudaR": "build is broken, needs nvcc",
        "MTseeker": "deprecated / removed, but still in packages",
        "nem": "deprecated / removed, but still in packages",
        # "nloptr": "undefined symbol: nlopt_remove_equality_constraints - version mismatch?",
        "pbdSLAP": "mpi trouble",
        # "pbdSLAP": "mpi trouble",
        "permGPU": "build is broken, needs nvcc",
        "PythonInR": "needs python",  # todo
        "qtbase": "Can't get it to find GL/gl.h",
        "randstr": "queries www.random.org",
        "Rblpapi": "blpapi is bloomberg professional API - unfree, not in nixpkgs",
        "Rcplex": "unfree. Cplex not in nixpkgs",
        "RIPSeeker": "deprecated / removed, but still in packages",
        "Rmpi": "undefined symbol: mpi_universe_size?",  # todo : figure out and fix
        "ROracle": "unfree. Oracle OCI not in nixpkgs",
        "rpanel": "build broken, wants DISPLAY?",
        "Rsymphony": "can't find SYMPHONY in nixpkgs",
        "rtfbs": "requeries rphast, which was removed from CRAN on 2020-03-03",
        "switchr": "R package managment (not necessary on Nix). Cannot open the connection to 'http://bioconductor.org/config.yaml'",
        "sybilSBML": "configure checks for /usr/include and /usr/local/include - and possibly also needs libsmbl, judging by the name?",
        "tkRplotR": 'error: [tcl] invalid command name "image".',
        "wrswoR.benchmark": "Could not resolve host: raw.githubusercontent.com",
        "x12": "'error: argument is of length zero'?",
        # "AnnotationDbi": "bioconductor 3.11 was released with AnnotationDbi=1.49.1, but every downstream package needs 1.49.2, try after 2020-04-29 (=tommorw)",  # that's a bioconductor package. smh
        "GeneBook": "attempts to contact github",
        "CensMFM": "objects 'pmvn.genz', 'pmvt.genz' are not exported by 'namespace:tlrmvnmvt'",
        "CensSpatial": "objects 'pmvn.genz', 'pmvt.genz' are not exported by 'namespace:tlrmvnmvt'",
        "flowFit": "object 'Data' is not exported by 'namespace:flowCore'",
        "nethet": "needs parcor, which was archived",
        # "spiR": "could not resolve host: docs.google.com",
        "GO.db.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "PFAM.db.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "anopheles.db0.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "canine.db0.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "chicken.db0.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "ecoliK12.db0.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "ecoliSakai.db0.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "bovine.db0.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "chimp.db0.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "malaria.db0.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "org.Ag.eg.db.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "org.Bt.eg.db.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "org.EcK12.eg.db.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "org.EcSakai.eg.db.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "arabidopsis.db0.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "fly.db0.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "org.Ce.eg.db.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "org.Cf.eg.db.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "org.Dm.eg.db.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "org.Gg.eg.db.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "org.Mmu.eg.db.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "org.Pf.plasmo.db.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "org.Dr.eg.db.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "org.Xl.eg.db.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "org.Ss.eg.db.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "org.Sc.sgd.db.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "org.Pt.eg.db.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "org.At.tair.db.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "pig.db0.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "yeast.db0.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "xenopus.db0.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "rhesus.db0.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "org.Mm.eg.db.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "org.Hs.eg.db.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "worm.db0.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "org.Rn.eg.db.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "zebrafish.db0.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "mouse.db0.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "rat.db0.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
        "human.db0.": "AnnotationDbi 1.49.2 needed. Try 2020-04-28",
    },
)
broken_packages.inherit(
    ("3.11", "2020-04-29"),
    {},
    [
        "bsseq",
        "GO.db.",
        "PFAM.db.",
        "anopheles.db0.",
        "canine.db0.",
        "chicken.db0.",
        "ecoliK12.db0.",
        "ecoliSakai.db0.",
        "bovine.db0.",
        "chimp.db0.",
        "malaria.db0.",
        "org.Ag.eg.db.",
        "org.Bt.eg.db.",
        "org.EcK12.eg.db.",
        "org.EcSakai.eg.db.",
        "arabidopsis.db0.",
        "fly.db0.",
        "org.Ce.eg.db.",
        "org.Cf.eg.db.",
        "org.Dm.eg.db.",
        "org.Gg.eg.db.",
        "org.Mmu.eg.db.",
        "org.Pf.plasmo.db.",
        "org.Dr.eg.db.",
        "org.Xl.eg.db.",
        "org.Ss.eg.db.",
        "org.Sc.sgd.db.",
        "org.Pt.eg.db.",
        "org.At.tair.db.",
        "pig.db0.",
        "yeast.db0.",
        "xenopus.db0.",
        "rhesus.db0.",
        "org.Mm.eg.db.",
        "org.Hs.eg.db.",
        "worm.db0.",
        "org.Rn.eg.db.",
        "zebrafish.db0.",
        "mouse.db0.",
        "rat.db0.",
        "human.db0.",
    ],  # check date
)

broken_packages.inherit(
    ("3.11", "2020-05-14"),
    {
        "parcor": "missing ppls",
    },  # check date
)
broken_packages.inherit(
    ("3.11", "2020-06-16"),
    {},
    ["rdomains"],  # check date
)


broken_packages.inherit(  # start anew. - 2020-10-28
    ("3.12"),
    {
        "BiocPkgTools": "object 'html_text2' is not exported by 'namespace:rvest'",
        "biocthis": "requires usethis >=2.0.1, try after 2021-02-11",
        "bitmexr": "please check your internet connection. 'Crypto'. Please destroy another planet, ktxbye.",
        "BRugs": "needs OpenBUGS, not in nixpkgs. Or in ubuntu. And the website change log says it hasn't updated since 2014. And the ssl certificate is expired.",
        "DESeq": "deprecated but still in PACKAGES.gz",
        "discrim": "The values passed to `set_encoding()` are missing arguments: 'allow_sparse_x'",
        "dmdScheme": "cannot open URL 'https://github.com/Exp-Micro-Ecol-Hub/dmdSchemeRepository/raw/master/schemes/dmdScheme_0.9.9.tar.gz'",
        "drawer": "released later on 2021-03-03",
        "easyRNASeq": "MacOSX only? no source in 3.12",
        "elaborator": "shinyjs: extendShinyjs: `functions` argument must be provided.",
        "flowType": "deprecated but still in PACKAGES.gz",
        "freetypeharfbuzz": "Downloads from github",
        "FunciSNP.data": "deprecated but still in PACKAGES.gz",
        "GeneBook": "attempts to contact github",
        "gpuMagic": "needs opencl",
        "gQTLBase": "objects 'clone', 'is.factor.ff' are not exported by 'namespace:ff'",
        "kazaam": "mpi trouble",
        "kmcudaR": "build is broken, needs nvcc",
        "maGUI": "Error: object 'toptable' is not exported by 'namespace:limma'",
        "modeltime": "The values passed to `set_encoding()` are missing arguments: 'allow_sparse_x'",
        "networkBMA": "compilation failure",
        "parcor": "missing ppls",
        "pbdSLAP": "mpi trouble",
        "permGPU": "build is broken, needs nvcc",
        "PGSEA": "deprecated but still in PACKAGES.gz",
        "prada": "deprecated but still in PACKAGES.gz",
        "PythonInR": "needs python",  # todo
        #   "qtbase": "Can't get it to find GL/gl.h",
        "RAMClustR": "object 'delete.ff' is not exported by 'namespace:ff'",
        "Rariant": "object 'rbind_all' is not exported by 'namespace:dplyr', try after 2021-01-16?",
        "Rblpapi": "blpapi is bloomberg professional API - unfree, not in nixpkgs",
        "Rcplex": "unfree. Cplex not in nixpkgs",
        "Rcwl": "needs cwltool, not available in nixpkgs 20.03",
        "Rmpi": "undefined symbol: mpi_universe_size?",  # todo : figure out and fix
        "Roleswitch": "deprecated but still in PACKAGES.gz",
        "ROracle": "unfree. Oracle OCI not in nixpkgs",
        "rpanel": "build broken, wants DISPLAY?",
        "RQuantLib": "hquantlib is a haskell package - don't think that's what's required?",
        "rsbml": "libsmbl isn't packagd in nixpkg ",
        "Rsymphony": "can't find SYMPHONY in nixpkgs",
        "rTANDEM": "deprecated but still in PACKAGES.gz",
        # second wave
        "SeuratObject": "released later on 2021-01-16",
        "spatstat.core": "released later on 2021-01-23",
        "spatstat.geom": "released later on 2021-01-16",
        "spsComps": "released later on 2021-02-26",
        "spsUtil": "released later on 2021-02-17",
        "switchr": "R package managment (not necessary on Nix). Cannot open the connection to 'http://bioconductor.org/config.yaml'",
        "sybilSBML": "configure checks for /usr/include and /usr/local/include - and possibly also needs libsmbl, judging by the name?",
        "synergyfinder": "requires dplyr >=1.0.3, try after 2021-01-16",
        "terra": "ERROR 1: PROJ: proj_create_from_database: Cannot find proj.db",  # tod: probably fixable
        "tiledb": "cannot open URL 'https://github.com/TileDB-Inc/TileDB/releases/download/2.1.1/tiledb-linux-2.1.1-db11399-full.tar.gz'",
        "tkRplotR": 'error: [tcl] invalid command name "image".',
        "traitdataform": "attempts to contact 'https://raw.githubusercontent.com/EcologicalTraitData/ETS/v0.9/ETS.csv'",
        "waddR": "error in evaluating the argument 'conn' in selecting a method for function 'dbDisconnect': object 'con' not found",
        "x12": "'error: argument is of length zero'?",
    },
)
broken_packages.inherit(
    ("3.12", "2021-01-16"),
    {},
    ["SeuratObject", "spatstat.geom", "synergyfinder"],
)
broken_packages.inherit(("3.12", "2021-01-17"), {}, ["spsUtil"])
broken_packages.inherit(("3.12", "2021-01-23"), {}, ["spatstat.core"])
broken_packages.inherit(("3.12", "2021-01-26"), {}, ["spsComps"])
broken_packages.inherit(("3.12", "2021-02-11"), {}, ["biocthis"])
broken_packages.inherit(("3.12", "2021-03-03"), {}, ["drawer"])


broken_packages.inherit(  # start anew.
    ("3.13"),  # 2021-05-20
    {
        "affyPara": "error: cannot add binding of '.affyParaInternalEnv' to the base environment",
        "bitmexr": "please check your internet connection. 'Crypto'. Please destroy another planet, ktxbye.",
        "BRugs": "needs OpenBUGS, not in nixpkgs. Or in ubuntu. And the website change log says it hasn't updated since 2014. And the ssl certificate is expired.",
        "expp": "object 'ripras' is not exported by 'namespace:spatstat' (apperantly needs spatstat <2.0)",
        "permGPU": "needs nvcc",
        "gpuMagic": "needs opencl",
        "salso": "needs rust 1.49. Try after 2021-05-31 ",
        # "cbpManager": "Error in loadNamespace(x) : there is no package called 'markdown'",
        # "dmdScheme": "cannot open URL 'https://github.com/Exp-Micro-Ecol-Hub/dmdSchemeRepository/raw/master/schemes/dmdScheme_0.9.9.tar.gz'",
        "freetypeharfbuzz": "Downloads from github",
        "proj4": "configure: error: libproj and/or proj.h/proj_api.h not found in standard search locations. Try again after 2021-05-31",  # todo
        "ChemmineOB": "needs openbabel, only present in nixpkgs 21.05, try after 2021-05-31",  # todo,
        "imcdatasets": 'path[1]="/homeless-shelter/.cache/R/BiocFileCache": No such file or directory',
        "IDSpatialStats": "Error: object 'bounding.box.xy' is not exported by 'namespace:spatstat' (apperantly needs spatstat <2.0)",
        "kazaam": "mpi trouble",
        "kmcudaR": "build is broken, needs nvcc",
        "mlbstatsR": "Could not resolve host: site.api.espn.com",
        # "PANTHER.db": "Directory of lock file does not exist: '/homeless-shelter/.cache/R/AnnotationHub'",
        "pbdSLAP": "mpi trouble",
        "Rblpapi": "blpapi is bloomberg professional API - unfree, not in nixpkgs",
        "Rcplex": "unfree. Cplex not in nixpkgs",
        "Rmpi": "undefined symbol: mpi_universe_size?",  # todo : figure out and fix
        "ROracle": "unfree. Oracle OCI not in nixpkgs",
        "rpanel": "build broken, [tcl] can't find package BWidget.",
        "RQuantLib": "hquantlib is a haskell package - don't think that's what's required?",
        "rsbml": "libsmbl isn't packagd in nixpkg ",
        "Rsymphony": "can't find SYMPHONY in nixpkgs",
        "sbw": "object 'unnormdensity' is not exported by 'namespace:spatstat' (apperantly needs spatstat <2.0)",
        "spANOVA": "Error: object 'anova.sarlm' is not exported by 'namespace:spatialreg'",
        "switchr": "R package managment (not necessary on Nix). Cannot open the connection to 'http://bioconductor.org/config.yaml'",
        "terra": "ERROR 1: PROJ: proj_create_from_database: Cannot find proj.db",  # tod: probably fixable
        "AntMAN": "disappars from packages.gz, presumably because sdols is no longer present after 2021-03-30. There is an update on 2021-07-23, try after that date",
        "rLiDAR": ": object 'disc' is not exported by 'namespace:spatstat'",
        "h2o": "tries to mkdir dbuild/h2o/inst/java even when we already fetched it's jars using nix. Try to patch?",
    },
)

broken_packages.inherit(
    ("3.13", "2021-05-28"),
    {
        "GeneTonic": "Error: object 'bs4TabPanel' is not exported by 'namespace:bs4Dash', try after 2021-06-07"
    },
    [],
)
broken_packages.inherit(
    ("3.13", "2021-05-31"),
    {"ProbitSpatial": "build failure: Eigen cpp trouble"},
    ["ChemmineOB", "proj4", "salso"],
)
broken_packages.inherit(("3.13", "2021-06-07"), {}, ["GeneTonic"])
broken_packages.inherit(("3.13", "2021-07-23"), {}, ["AntMAN"])
broken_packages.inherit(  # start anew.
    ("3.14"),  # 2021-10-27
    {
        # actual build failures / things we might be able to fix
        # arrow & rsymphony together is about 13 packages that are still missing. 9 arrow, 4 RSymphony
        "Rsymphony": "can't find SYMPHONY in nixpkgs",
        "pbdBASE": "either can't find symbol set_BLACS_APTS_in_R if you pass --enable-blacsexport, or can't find BI_Iam",  # and nothing is depending on this package, apperantly, and it has been rehoved from cran in 2021-11-05
        # r version mismatches?
        "cn.mops": "Error: object 'values' is not exported by 'namespace:IRanges. TRy after 2021-10-28 (so tomorrow)",
        # proprietary / unsupported by cran_tracker_for_nix
        "ROracle": "unfree. Oracle OCI not in nixpkgs",
        "Rcplex": "unfree. Cplex not in nixpkgs",
        "Rblpapi": "blpapi is bloomberg professional API - unfree, not in nixpkgs",
        "bitmexr": "please check your internet connection. 'Crypto'. Please destroy another planet, ktxbye.",
        "switchr": "R package managment (not necessary on Nix). Cannot open the connection to 'http://bioconductor.org/config.yaml'",
        # deps not in nixpkgs
        "RQuantLib": "hquantlib is a haskell package - don't think that's what's required?",
        "BRugs": "needs OpenBUGS, not in nixpkgs. Or in ubuntu. And the website change log says it hasn't updated since 2014. And the ssl certificate is expired.",
        # opencl/nvcc
        "gpuMagic": "needs opencl",
        "kmcudaR": "build is broken, needs nvcc",
        "permGPU": "needs nvcc",
        # net access
    },
)
broken_packages.inherit(
    ("3.14", "2021-10-28"),
    {},
    ["cn.mops"],  # is IRanges new enough now
)
broken_packages.inherit(
    ("3.14", "2021-11-05"),
    {},
    ["pbdBASE"],  #  removed from cran, no longer need to exclude it
)  #
broken_packages.inherit(
    ("3.14", "2021-11-06"),
    {},
    ["kmcudaR", "permGPU"],  #  removed from cran, no longer need to exclude it
)
broken_packages.inherit(
    ("3.14", "2021-11-08"),
    {
        "DEScan2": "object 'collapse' is not exported by 'namespace:glue'"
    },  # no new release until 2021-11-20 (could possibly be patched, seems to be renamed glue_collapse)
)


broken_packages = broken_packages.to_dict()

# for when a new package can't be used because a dependency hasn't
# catched up yet, so we want to use an older version of the new package
# only works for cran packages.
# these are not bioc version specific, since they're usually pairs
# of start downgrade / end downgrade.
downgrades = Inheritor()
downgrades.inherit("-", {})
downgrades.inherit(
    ("-", "2015-05-28"),
    {"RecordLinkage": "0.4-8"},  # , "Namespace trouble -no table.ff in ffbase",
    [],
)


downgrades.inherit(
    ("-", "2015-06-05"), {}, ["RecordLinkage"]
)  # ffbase release, RecordLinkage should work again

downgrades.inherit(
    ("-", "2016-01-10"),
    {"synchronicity": "1.1.4"},
    [],  # boost trouble
)

downgrades.inherit(
    ("-", "2016-02-17"), {}, ["synchronicity"]
)  # synchronicity release, might work again.


downgrades = downgrades.to_dict()


package_patches = {
    # this is the big gun, when we need to replace a package *completly*
    # {'version': {'bioc|experiment|annotation': [{'name':..., 'version': ..., 'depends': [...], 'imports': [...], 'needs_compilation': True}]}}
    "3.13": {
        "experiment": [
            {
                "name": "BioImageDbs",
                "version": "1.0.5",  # but packages.gz lists 1.0.4..., for which bioconductor.org has no file (I don't see an Archive for experiment either)
                "depends": ["magick", "filesstrings", "animation", "einsum"],
                "imports": [
                    "ExperimentHub",
                    "markdown",
                    "rmarkdown",
                    "EBImage",
                ],
                "suggests": [
                    "knitr",
                    "BiocStyle",
                    "magick",
                    "magrittr",
                    "purrr",
                    "filesstrings",
                    "animation",
                ],
                "linking_to": [],
                "needs_compilation": False,
            },
            {
                "name": "curatedMetagenomicData",
                "version": "3.0.10",  # but packages.gz lists 3.0.10, for which bioconductor.org has no file (I don't see an Archive for experiment either)
                "depends": ["SummarizedExperiment", "TreeSummarizedExperiment"],
                "imports": [
                    "AnnotationHub",
                    "ExperimentHub",
                    "S4Vectors",
                    "dplyr",
                    "magrittr",
                    "purrr",
                    "rlang",
                    "stringr",
                    "tibble",
                    "tidyr",
                    "tidyselect",
                ],
                "suggests": [
                    "BiocStyle",
                    "DT",
                    "knitr",
                    "mia",
                    "readr",
                    "rmarkdown",
                    "scater",
                    "testthat",
                    "uwot",
                    "vegan",
                ],
                "linking_to": [],
                "needs_compilation": False,
            },
        ]
    },
}

additional_r_dependencies = Inheritor("nested_dicts")
additional_r_dependencies.inherit(
    # for when dependencies are missing.
    # we need to use this already at low level,
    # so the graph is complete,
    # not only on export
    "3.0",
    {
        "annotation": {"gahgu133plus2cdf": ["AnnotationDbi"]},
        "software": {"inSilicoMerging": ["inSilicoDb"]},
    },
)
additional_r_dependencies.inherit(
    "3.1",
    {
        "software": {"inSilicoMerging": ["inSilicoDb"], "ChemmineR": ["gridExtra"]},
    },
)
additional_r_dependencies.inherit(
    "3.2",
    {
        "annotation": {"gahgu133plus2cdf": ["AnnotationDbi"]},
        "software": {
            "inSilicoMerging": ["inSilicoDb"],
            # "ChemmineR": ["gridExtra"]
        },
    },
)
additional_r_dependencies.inherit(
    "3.9",
    {
        "cran": {"zonator": ["codetools"]},
    },
)
additional_r_dependencies.inherit(
    "3.10",
    {
        "cran": {"RBesT": ["rstantools"]},
    },
)
additional_r_dependencies.inherit(
    "3.11",
    {
        "software": {
            # these are apperantly all 'bioconductor packages missed some deps that are in DESCRIPTION ???
            "ASICS": ["TSdist"],
            "BatchQC": ["d3heatmap"],
            "CATALYST": ["limma"],
            "CellMixS": ["listarrays"],
            "DAMEfinder": ["vcfR"],
            "sparsenetgls": ["parcor"],
            "decompTumor2Sig": ["vcfR"],
            "Doscheda": ["d3heatmap"],
            "hypeR": ["DT", "gh"],
            "MBQN": ["reshape2"],
            "Melissa": ["clues"],
            "mitch": ["pbmcapply"],
            "Modstrings": ["assertive"],
            "MSstats": ["randomForest"],
            "rWikiPathways": ["RJSONIO"],
            "sevenbridges": ["dplyr"],
            "Structstrings": ["assertive"],
            "tscR": ["TSdist"],
        },
        "cran": {
            "RBesT": ["rstantools"],
            "cbq": ["rstantools"],
            "qmix": ["rstantools"],
        },
    },
)
additional_r_dependencies.inherit(
    "3.12",
    {
        "cran": {
            "CNVRG": ["rstantools"],
            "RBesT": ["rstantools"],
            "densEstBayes": ["rstantools"],
            "gastempt": ["rstantools"],
            "qmix": ["rstantools"],
        },
        "software": {
            "powerTCR": ["tcR"],
            "MicrobiotaProcess": ["randomForest", "DECIPHER", "yaml", "phangorn"],
            "splatter": ["akima"],
            "CiteFuse": ["SNFtool"],
            "escape": [
                "ggrepel",
                "factoextra",
            ],
            "methrix": ["rjson"],
            "AnnotationHubData": ["rBiopaxParser"],
            "crossmeta": [
                "ccmap",
                "doParallel",
                "doRNG",
                "ggplot2",
                "metap",
                "plotly",
                "reshape",
                "rdrop2",
            ],
            "metagene2": ["DBChIP"],
            "KnowSeq": ["gplots", "multtest", "pathview"],
            "sesame": ["HDF5Array"],
            "cmapR": ["prada"],
            "CeTF": ["pbapply"],
            "HTSFilter": ["DESeq"],
            "GenomicOZone": ["sjstats"],
            "regionReport": ["knitcitations"],
            "MOGAMUN": ["nsga2R"],
            "mitch": ["pbmcapply"],
            "sojourner": ["rtiff"],
            "GSVA": ["fastmatch"],
            "BiocNeighbors": ["RcppAnnoy"],
            "psygenet2r": ["BiocManager"],
        },
    },
)
additional_r_dependencies.inherit(
    "3.13",
    {
        "software": {
            "BiocPkgTools": ["rex"],
            "artMS": [
                "biomaRt",
                "ComplexHeatmap",
                "factoextra",
                "FactoMineR",
                "gProfileR",
                "org.Mm.eg.db",
                "PerformanceAnalytics",
            ],
            "martini": ["memoise"],
            "cbpManager": ["markdown"],
        },
        "cran": {
            "RBesT": ["rstantools"],
            "densEstBayes": ["rstantools"],
            "bayesZIB": ["rstantools"],
            "qmix": ["rstantools"],
        },
    },
)
additional_r_dependencies.inherit(
    ("3.13", "2021-06-02"),
    {
        "cran": {
            "valse": ["RcppGSL"],
        }
    },
)
additional_r_dependencies.inherit(
    "3.14",
    {
        "cran": {
            "BINtools": ["rstantools"],
            "bayesZIB": ["rstantools"],
            "densEstBayes": ["rstantools"],
            "qmix": ["rstantools"],
            "red": ["codetools"],
            "oolong": ["mlapi", "text2vec"],  # starting 2021-11-12
        },
        "software": {
            "MicrobiotaProcess": [
                "phyloseq",
                "ggnewscale",
            ],
            "CAGEr": ["beanplot"],
            "martini": ["memoise"],
            "SpidermiR": ["visNetwork", "networkD3"],
            "sangeranalyseR": ["kableExtra"],
        },
    },
)

additional_r_dependencies = additional_r_dependencies.to_dict()

for k, v in additional_r_dependencies.items():
    for k2, v2 in v.items():
        if k2 not in ("software", "cran", "annotation", "experiment"):
            raise ValueError(f"invalid additional_r_dependencies key {k2}")
        for k3, v3 in v2.items():
            if not isinstance(v3, list):
                raise ValueError(f"entry for {k3} was not a list {v3}")


def cran_track_package(name, full_spec=""):
    return ("CRAN_TRACK_PACKAGE", name, full_spec)


native_build_inputs = Inheritor()  # ie. compile time dependencies
# pkgs. get's added automatically if there's no . in the entry.
native_build_inputs.inherit(
    "3.0",
    {
        "rhdf5": ["hdf5"],
        "abn": ["gsl"],
        "adimpro": ["imagemagick", "pkgconfig"],
        "affyio": ["zlib"],
        "ArrayExpressHTS": ["which"],
        "audio": ["portaudio"],
        "BayesLogit": ["openblasCompat"],
        "BayesSAE": ["gsl"],
        "BayesVarSel": ["gsl"],
        "BayesXsrc": ["readline", "ncurses"],
        "BiocCheck": ["which"],
        "Biostrings": ["zlib"],
        # "BitSeq": ["zlib"],
        "bnpmr": ["gsl"],
        "BNSP": ["gsl"],
        "cairoDevice": ["gtk2"],
        "Cairo": ["libtiff", "libjpeg", "cairo"],
        "CARramps": ["pkgs.linuxPackages.nvidia_x11", "liblapack"],
        "chebpol": ["fftw", "pkgconfig"],
        "ChemmineOB": ["openbabel", "pkgconfig"],
        "cit": ["gsl"],
        "Crossover": ["which"],
        "devEMF": ["pkgs.xlibs.libXft"],
        "pmclust": ["openmpi", "openssh"],
        # "DiffBind": ["zlib"],
        "DirichletMultinomial": ["gsl"],
        "diversitree": ["gsl", "fftw"],
        "eiR": ["gsl"],
        "EMCluster": ["liblapack"],
        "fftw": ["fftw"],
        "fftwtools": ["fftw"],
        "flowQ": ["imagemagick"],
        "Formula": ["gmp"],
        "geoCount": ["gsl"],
        "GLAD": ["gsl"],
        "glpkAPI": ["gmp", "glpk"],
        "gMCP": ["which"],
        "gmp": ["gmp"],
        "gsl": ["gsl"],
        "HiCseg": ["gsl"],
        "iBMQ": ["gsl"],
        "igraph": ["gmp"],
        "JavaGD": ["jdk"],
        "jpeg": ["libjpeg"],
        "KFKSDS": ["gsl"],
        "kza": ["fftw"],
        "libamtrack": ["gsl"],
        "ltsk": ["liblapack", "blas"],
        "mixcat": ["gsl"],
        "MMDiff": ["gsl"],
        "motifStack": ["gsl"],
        "MotIV": ["openssl", "gsl"],
        "MSGFplus": ["jdk"],
        "mvabund": ["gsl"],
        "mwaved": ["fftw"],
        "mzR": ["zlib", "netcdf"],
        "ncdf4": ["netcdf"],
        # "ncdfFlow": ["hdf5.dev"],
        "ncdf": ["netcdf"],
        "nloptr": ["nlopt"],
        "npRmpi": ["openmpi"],
        # "openssl": ["openssl"],
        "outbreaker": ["gsl"],
        "pander": ["pandoc", "which"],
        "pbdMPI": ["openmpi", "openssh"],
        "pbdNCDF4": ["netcdf"],
        "pbdPROF": ["openmpi"],
        "pbdSLAP": ["openmpi", "openssh"],
        "PBSmapping": ["which"],
        "PBSmodelling": ["which"],
        "pcaPA": ["gsl"],
        "PICS": ["gsl"],
        "PING": ["gsl"],
        "PKI": ["openssl"],
        "png": ["libpng"],
        "PopGenome": ["zlib"],
        "proj4": ["proj"],
        "qtbase": ["qt4", "cmake"],
        "qtpaint": ["qt4", "cmake"],
        "R2GUESS": ["gsl"],
        "R2SWF": ["zlib", "libpng", "freetype"],
        "RapidPolygonLookup": ["which"],
        "RAppArmor": ["libapparmor"],
        "rapportools": ["which"],
        "rapport": ["which"],
        "rbamtools": ["zlib"],
        "RCA": ["gmp"],
        "rcdd": ["gmp"],
        "RcppCNPy": ["zlib"],
        "RcppGSL": ["gsl_1"],
        "RcppOctave": ["zlib", "bzip2", "icu", "lzma", "pcre", "octave"],
        "RcppRedis": ["hiredis"],
        "RcppZiggurat": ["gsl"],
        # "ReQON": ["zlib"],
        "rgdal": ["proj", "gdal", "pkgconfig"],
        "rgeos": ["geos"],
        "rggobi": ["ggobi", "gtk2", "libxml2"],
        "rgl": ["mesa", "x11"],
        "Rglpk": ["glpk"],
        "rgpui": ["which"],
        "rgp": ["which"],
        "RGtk2": ["gtk2"],
        # "rhdf5": ["hdf5.dev"],
        "Rhpc": ["zlib", "bzip2", "icu", "lzma", "openmpi", "pcre"],
        # "Rhtslib": ["zlib"],
        "ridge": ["gsl"],
        "RJaCGH": ["zlib"],
        "rjags": ["jags"],
        "rJava": [
            "zlib",
            "bzip2",
            "icu",
            "lzma",
            "pcre",
            "jdk",
            "libzip",
        ],
        "rMAT": ["gsl"],
        # "rmatio": ["zlib"],
        "Rmpfr": ["gmp", "mpfr"],
        "Rmpi": ["openmpi"],
        "RMySQL": ["zlib", "pkgs.mysql.lib"],
        "RnavGraph": ["xlibsWrapper"],
        "RNetCDF": ["netcdf", "udunits"],
        "Rniftilib": ["zlib", "openmpi"],
        "RODBCext": ["libiodbc"],
        "RODBC": ["libiodbc"],
        "rpanel": ["tk"],
        "rpg": ["postgresql"],
        "rphast": ["pcre", "zlib", "bzip2", "gzip", "readline"],
        "Rpoppler": ["poppler"],
        "RPostgreSQL": ["postgresql"],
        "RProtoBuf": ["protobuf"],
        "rpud": ["pkgs.linuxPackages.nvidia_x11"],
        "rPython": ["python"],
        "Rsamtools": ["zlib"],
        "RSclient": ["openssl"],
        "Rserve": ["openssl"],
        "Rssa": ["fftw"],
        "rTANDEM": ["expat"],
        "rtfbs": ["zlib", "pcre", "bzip2", "gzip", "readline"],
        "rtiff": ["libtiff"],
        "runjags": ["jags"],
        "RVowpalWabbit": ["zlib", "boost"],
        "rzmq": ["zeromq3"],
        "SAVE": ["zlib", "bzip2", "icu", "lzma", "pcre"],
        "sdcTable": ["gmp", "glpk"],
        "seewave": ["fftw", "libsndfile"],
        "SemiCompRisks": ["gsl"],
        # "seqbias": ["zlib"],
        # "seqinr": ["zlib"],
        "seqminer": ["zlib", "bzip2"],
        "seqTools": ["zlib"],
        # "seqTools": ["zlib"],
        # "ShortRead": ["zlib"],
        "showtext": ["zlib", "libpng", "icu", "freetype"],
        "simplexreg": ["gsl"],
        "SJava": ["jdk"],
        "snpStats": ["zlib"],
        "SOD": ["cudatoolkit"],
        "sprint": ["openmpi"],
        "ssanv": ["proj"],
        "STARSEQ": ["zlib"],
        "stringi": ["icu"],
        "stsm": ["gsl"],
        "survSNP": ["gsl"],
        "sysfonts": ["pkgconfig", "zlib", "libpng", "freetype"],
        "TAQMNGR": ["zlib"],
        "tiff": ["libtiff"],
        "tkrplot": ["pkgs.xlibs.libX11"],
        "topicmodels": ["gsl"],
        "udunits2": ["udunits", "expat"],
        "VBLPCM": ["gsl"],
        "VBmix": ["gsl", "fftw", "qt4"],
        "vcf2geno": ["zlib"],
        "XBRL": ["zlib", "libxml2"],
        "XML": ["libtool", "libxml2", "xmlsec", "libxslt"],
    },
)
native_build_inputs.inherit(("3.0", "2014-10-26"), {}, ["vcf2geno"])
native_build_inputs.inherit(("3.0", "2014-10-31"), {}, ["STARSEQ"])
native_build_inputs.inherit(
    ("3.0", "2015-01-11"),
    {
        "curl": ["curl"],
        "openssl": ["openssl"],
        "seqinr": ["zlib"],
        "rbison": ["glpk"],
        "rDEA": ["glpk"],
    },
)
native_build_inputs.inherit(
    ("3.0", "2015-03-09"),
    {},
    ["Rniftilib"],
)
native_build_inputs.inherit(
    "3.1",
    {
        "abn": ["gsl"],
        "bigGP": ["openmpi"],
        "birte": ["liblapack", "blas"],
        "Cardinal": ["which"],
        "dbConnect": ["curl"],
        "graphscan": ["gsl"],
        "immunoClust": ["gsl"],
        "lfe": ["which"],
        "LowMACA": ["which"],
        "mongolite": ["openssl"],
        "PBSddesolve": ["which"],
        "Rhtslib": ["zlib"],
        "Rlibeemd": ["gsl"],
        "TKF": ["gsl"],
        "V8": ["v8"],
        # "iptools": ["boost"],
        "git2r": ["zlib", "openssl"],
        # "OpenMx": ["autoreconfHook"],
    },
    ["npRmpi"],
    copy_anyway=True,
)
native_build_inputs.inherit(
    ("3.1", "2015-04-21"),
    {
        "xml2": ["libxml2"],
    },
)
native_build_inputs.inherit(
    ("3.1", "2015-06-09"),
    {
        "PEIP": ["liblapack", "blas"],
    },
)

native_build_inputs.inherit(
    ("3.1", "2015-07-11"),
    {
        "PythonInR": ["python"],
    },
)


native_build_inputs.inherit(("3.1", "2015-08-31"), {"spatial": ["which"]})  # 7.3.11
native_build_inputs.inherit(
    ("3.1", "2015-10-01"),
    {
        "VBmix": ["gsl", "fftw", "qt4", "blas", "liblapack"],
        "animation": ["which"],
        # "Rblpapi": ["autoreconfHook"],
        "bedr": ["which"],
        # "xml2": ["autoreconfHook"],
        "curl": ["curl"],
    },
)

native_build_inputs.inherit(
    "3.2",
    {
        "Rsubread": ["zlib"],
        "qtbase": ["qt4"],
        "WhopGenome": ["zlib"],
        "XVector": ["zlib"],
        "synchronicity": ["boost"],
    },
    [],
    copy_anyway=True,
)
native_build_inputs.inherit(("3.2", "2015-11-21"), {}, ["CARramps", "rpud"])


native_build_inputs.inherit(
    ("3.2", "2016-01-10"),
    {
        "rmumps": ["cmake"],
        "SimInf": ["gsl"],
        "sodium": ["libsodium"],
    },
)
native_build_inputs.inherit(("3.2", "2016-01-11"), {}, ["ncdf"])

native_build_inputs.inherit("3.3", {}, [], copy_anyway=True)

native_build_inputs.inherit("3.4", {}, ["MMDiff", "SJava"], copy_anyway=True)
native_build_inputs.inherit(
    "3.5",
    {
        "devEMF": ["pkgs.xlibs.libXft", "x11"],
        "xslt": ["pkgconfig", "libxslt"],
        "clpAPI": ["pkgconfig"],  # todo: if this works, remove exclusion from 3.0
        "gpg": ["gpgme"],
        "V8": ["v8_3_14"],
        "MSeasyTkGUI": ["tk"],
        "RJMCMCNucleosomes": ["gsl_1"],
        "SICtools": ["ncurses"],
        "Rhtslib": ["zlib", "bzip2", "lzma", "curl", "autoconf"],
        "sf": ["gdal", "proj", "pkgconfig", "sqlite", "geos"],
        "tofsims": ["blas", "liblapack"],
        "PharmacoGx": ["which"],
        "gpuR": ["cudatoolkit"],
        "Rsampletrees": ["gsl_1"],
        "gmum.r": ["pcre", "lzma", "bzip2"],
        "TDA": ["mpfr"],
        "RnavGraph": ["xlibsWrapper", "tk"],
        "dynr": ["gsl_1"],
        "gdtools": ["cairo", "pkgconfig", "pkgs.fontconfig.lib", "freetype"],
        "wand": ["file"],  # libmagic is provided by file?
        "covr": ["which"],
        "goldi": ["blas", "liblapack"],
        "ndjson": ["zlib"],
        "spongecake": ["which"],
        "tkrplot": ["tk"],
        "SnakeCharmR": ["python"],
        "permGPU": ["cudatoolkit"],
        "tesseract": ["tesseract", "leptonica"],
        "CHRONOS": ["which"],
        "pbdBASE": ["blas", "liblapack", "openmpi"],
        "sbrl": ["gsl_1", "gmp"],
        "AMOUNTAIN": ["gsl_1"],
        "bio3d": ["zlib"],
        "Cairo": [
            "pkgconfig",
            "libtiff",
            "libjpeg",
            "cairo",
            "x11",
            "pkgs.fontconfig.lib",
        ],
        "DEploid": [
            "zlib",
        ],
        "exifr": ["perl", "pkgs.perlPackages.ImageExifTool"],
        "flowPeaks": ["gsl_1"],
        "HilbertVisGUI": ["pkgconfig", "opencl-headers", "gtkmm2", "gtk2", "which"],
        "HiPLARM": ["blas", "liblapack"],
        "Libra": ["gsl_1"],
        "mongolite": [
            "pkgconfig",
            "pkgs.openssl.dev",
            "pkgs.openssl.out",
            "pkgs.cyrus_sasl.dev",
            "pkgs.cyrus_sasl.out",
            "zlib",
        ],
        "MSGFplus": ["which", "jdk"],
        "mvst": ["gsl_1"],
        # "OpenCL": ["opencl-headers"],
        "pdftools": ["poppler", "pkgconfig"],
        "protolite": ["protobuf"],
        "psbcGroup": [
            "fftw",
            "gsl_1",
        ],
        "rcqp": ["pkgconfig", "pcre", "glib"],
        "s2": ["pkgconfig", "openssl"],
        "stringi": ["pkgs.icu.dev"],  # available 17.03.  #
        "redland": ["redland", "pkgconfig", "librdf_raptor2", "librdf_rasqal"],
        "rsvg": ["librsvg", "pkgconfig"],
        "magick": ["imagemagick", "pkgconfig"],
        "vcfR": ["zlib"],
    },
    [],
    copy_anyway=True,
)
native_build_inputs.inherit(
    "3.6",
    {
        "RcppClassic": ["binutils"],
        "base64": ["pkgs.openssl.dev"],
        "bcrypt": ["pkgs.openssl.dev"],
        "fRLR": ["gsl_1"],
        "gaston": ["zlib"],
        "geosapi": ["pkgs.openssl.dev"],
        "opencpu": ["pkgs.openssl.dev"],
        "h5": ["hdf5"],
        "zstdr": ["cmake"],
        "openPrimeR": ["which"],
        "clustermq": ["which"],
        "RProtoBufLib": ["autoconf", "automake", "protobuf", "libtool"],
        "keyring": [
            "which",
            "pkgconfig",
            "pkgs.openssl",
            "pkgs.openssl.out",
            "libsecret",
            "pkgs.libsecret.dev",
        ],
        "RcppGSL": ["which", "gsl_1"],
        "cld3": ["protobuf"],
        "writexl": ["zlib"],
        "hdf5r": ["hdf5"],
        "jose": ["pkgs.openssl", "pkgs.openssl.out"],
        "jqr": ["jq"],
        "kmcudaR": ["cudatoolkit"],
        "libstableR": ["gsl_1"],
        "MonetDBLite": ["zlib"],
        "pinnacle.API": ["pkgs.openssl.dev"],
        "phylogram": ["pkgs.openssl.dev"],
        "poisbinom": ["fftw"],
        "protolite": ["protobuf", "autoconf", "automake"],
        "rDotNet": ["which"],
        "reconstructr": ["pkgs.openssl.dev"],
        "RSelenium": ["pkgs.openssl.dev"],
        "SensusR": ["pkgs.openssl.dev"],
        "SuperGauss": ["fftw", "pkgconfig"],
        "RMariaDB": ["zlib", "pkgs.mysql.lib", "openssl"],
        "RmecabKo": ["mecab"],
        "rtweet": ["pkgs.openssl.dev"],
        "fastrtext": ["binutils"],
        "MAINT.Data": ["binutils"],
    },
    ["HiPLARM"],
    copy_anyway=True,
)

native_build_inputs.inherit(
    ("3.6", "2017-11-03"),
    {},
    ["RcppOctave"],
)
native_build_inputs.inherit(
    ("3.6", "2018-01-02"),
    {},
    ["rgpui", "rgp"],
)
native_build_inputs.inherit(
    ("3.6", "2018-01-23"),
    {},
    ["sprint"],
)
native_build_inputs.inherit(
    ("3.6", "2018-03-05"),
    {},
    ["VBmix"],
)


native_build_inputs.inherit(
    "3.7",
    {
        "KSgeneral": ["pkgconfig", "fftw"],
        "kde1d": ["binutils"],
        "RMySQL": ["zlib", "pkgs.mysql.connector-c", "openssl"],
        "RMariaDB": ["zlib", "pkgs.mysql.connector-c", "openssl"],
        "Rbowtie2": ["zlib"],
        "JMcmprsk": ["gsl_1"],
        "kazaam": ["openmpi", "openssh"],
        "RcppCWB": [
            "pcre",
            "glib",
            "pkgconfig",
            "ncurses",
            "which",
            "bison",
            "utillinux",
            "flex",
        ],
        "SeqKat": ["binutils"],
        "ISOpureR": ["binutils"],
        "redux": ["hiredis", "pkgconfig"],
        "rmumps": ["zlib"],
        "odbc": ["unixODBC"],
        "bamboo": ["which", "scala"],
        "sdols": ["which", "scala"],
        "shallot": ["which", "scala"],
        "zeligverse": ["which"],
        "gitter": ["which"],
        "valection": ["which"],
        "walker": ["which"],
        "specklestar": ["fftw"],
        "rvinecopulib": ["binutils"],
        "KRIG": ["gsl_1"],
        "ijtiff": ["libtiff"],
        "tabr": ["which"],
        "RPostgres": ["pkgconfig", "postgresql", "which"],
        "landsepi": ["gsl_1"],
        "jiebaRD": ["unzip"],
        "textTinyR": ["boost"],
        "qtbase": ["qt4", "cmake", "(lib.getDev pkgs.libGL)"],
    },
    [
        "gmum.r",
    ],
    copy_anyway=True,
)

native_build_inputs.inherit(
    ("3.7", "2018-05-15"),
    {},
    ["RnavGraph"],
)
native_build_inputs.inherit(
    ("3.7", "2018-08-05"),
    {},
    ["SOD"],
)


native_build_inputs.inherit(
    "3.8",
    {
        "BALD": ["pkgconfig", "jags", "pcre", "lzma", "bzip2", "zlib", "icu"],
        "bioacoustics": ["cmake", "fftw", "soxr"],
        "cairoDevice": ["gtk2", "pkgconfig"],
        "chebpol": ["fftw", "pkgconfig", "gsl_1"],
        "DRIP": ["gsl_1"],
        "fftw": ["pkgconfig", "pkgs.fftw.dev"],
        "GENEAsphere": [
            "mesa_glu",
        ],  # which might allow +extension GLX to work on xvfb
        "geoCount": ["gsl_1", "pkgconfig"],
        "haven": ["zlib"],
        "hipread": ["zlib"],
        "ijtiff": ["which", "libtiff", "pkgconfig"],
        "msgl": ["binutils"],
        "mwaved": ["pkgconfig", "fftw"],
        "phateR": ["which"],
        "RCurl": ["pkgconfig", "curl"],
        "rgl": ["libGLU", "mesa_glu", "x11", "pkgconfig"],
        "ssh": ["libssh"],
        "qtpaint": ["qt4", "cmake"],
        "Rmagic": ["which"],
        "rpf": ["pkgconfig"],
        "rrd": ["rrdtool"],
        "rscala": ["scala", "which"],
        "sglOptim": ["binutils"],
        "shinytest": ["which"],
        "spate": ["pkgconfig", "fftw"],
        "V8": ["v8_3_14"],
        "vapour": ["pkgconfig", "gdal", "proj", "geos"],
        "waved": ["fftw"],
        "wdm": ["binutils"],
    },
    ["flowQ", "rcqp"],
    copy_anyway=True,
)
native_build_inputs.inherit(("3.8", "2018-11-05"), {"lattice": ["which"]})  # 0.20-38
native_build_inputs.inherit(("3.8", "2018-12-25"), {"codetools": ["which"]})  # 0.2-16
native_build_inputs.inherit(
    ("3.8", "2019-03-03"),
    {},
    ["libamtrack"],
)
native_build_inputs.inherit(
    ("3.8", "2019-03-20"),
    {},
    ["pcaPA"],
)

# there is a lot of these comming up
need_which_in_3_9 = """ABAData abc.data ABC.RAP abind ACA AcceptanceSampling
ACCLMA ACD acepack acnr acss.data adagio adaptivetau additivityTests
AdequacyModel ADGofTest admisc ADPF AdvDif4 affxparser Affyhgu133A2Expr
AffymetrixDataTestFiles agop AHCytoBands airGR Ake ald AlgDesign
AlgebraicHaploPackage AlleleRetain AllPossibleSpellings alluvial ALSCPC
amap AMAP.Seq AMCP AMCTestmakeR AmericanCallOpt AMGET
AmmoniaConcentration AMORE AMOUNTAIN anapuce AneuFinderData AnnotLists
aod APCanalysis APSIMBatch ArArRedux ArDec argon2 argosfilter
ArgumentCheck ARHT ARPobservation ARRmData ars ARTP ASAFE ASEB ash
AshkenazimSonChr21 ASICSdata AsioHeaders ASSA assertive.base assertthat
AST astroFns astrolibR astsa AsynchLong ATE AtmRay AUC audio
AutoregressionMDE aweek awsMethods BAC backports BADER BaPreStoPro
BarBorGradient Barnard BAS base64enc BASIX BASS batchmeans BayesCombo
BayesDA BayesH BayesLogit BayesNI bayesQR BayesTreePrior BayesValidate
BayesXsrc BayHaz BaylorEdPsych BBMM BCC1997 BCDating BCgee BCRA bcv
bdsmatrix BeadDataPackR beanplot beeswarm BenfordTests BeyondBenford
bezier BGGE BGSIMD BH Bhat BHC BHH2 BiasedUrn BibPlots BICORN
bigmemory.sri BinaryEMVS binaryLogic bindr binom binr BiocGenerics
BiocManager BiocVersion Biodem BioFTF bio.infer BIOM.utils birk bit
bitops BivGeo BlakerCI BlandAltmanLeh BLModel blockmatrix BlockMessage
BLSM bmp BMS BNDataGenerator bnlearn BNPdensity boa BoardGames Bolstad2
boot BootMRMR BootPR bootstrap bpcp braidrm Branching breakaway
breakpointRdata breastCancerVDX BRETIGEA brew Brobdingnag brotli Brq
BsMD bspec BUCSS BufferedMatrix BurStFin BurStMisc bvls Cairo
Calculator.LR.FNs CancerInSilico carData CARE1 CarletonStats CARLIT
caroline CascadeData CateSelection catnet catR CATT CATTexact CBT
CCAGFA ccdata cclust CCM CCP CDFt CDLasso CDNmoney CDROM CEC CensRegMod
CFAssay CfEstimateQuantiles cghseg CGManalyzer CGP ChangepointTesting
Chaos01 ChargeTransport CheckDigit ChemoSpec CHFF ChillModels ChIPtest
CHNOSZ ChoiceModelR CholWishart choroplethrMaps chromstaRData chron
CIFsmry CIM CINID CircNNTSR CityPlot CLA ClamR ClickClust clipr
clisymbols clues CluMSIDdata clustComp cluster ClusterBootstrap
clusterCrit ClusterRankTest clustertend cmaes cMAP cMap2data CMC cmm
CMplot COBRA COCONUT cocor cOde coenocliner COHCAPanno ColorPalette
colorRamps colorspace colortools combinat CombinePortfolio
CombinePValue CombinS CombMSC CommonJavaJars commonmark commonsMath
compare CompareTests CompQuadForm compute.es Conake CondReg conf.design
CONFESSdata ConfIntVariance ConjointChecks ConnMatTools contfrac
ContourFunctions coop COPDSexualDimorphism.data Copula.Markov
Copula.surv CopyhelpeR CORE corpcor CorrectedFDR corrplot COSNet
countrycode cpm cptcity CR CRAC crayon CREAM CreditMetrics CRM crochet
crossval CRTSize CRWRM CSSP csv CTT CUMP curl CustomerScoringMetrics
CUSUMdesign CVcalibration CVD CVTuningCov DAAGxtras DACF DAIME DALEX2
DALY dapr Dark Dasst data.table date datetimeutils Davies dbEmpLikeGOF
DBI DCG DDM DECIDE decompr decon DEDS deepnet Delaporte deldir Delta
DEMEtics dendroextras denpro densratio DEoptim DEoptimR DepLogo
depthTools Deriv DES desiR deSolve dfcrm dfoptim dgodata dgof diagonals
DiceDesign DiceKriging dichromat dielectric digest DIME DiPhiSeq
diptest DIRECT DirectStandardisation dirmult disclap DiscreteFDR
DiscreteLaplace discretization DiscriMiner distances distcrete
distillery DISTRIB DistributionUtils dlm DNAcopy DNAseqtest DnE docopt
Dodge DoEstRare dotCall64 DOvalidation DriverNet DrugVsDiseasedata DSL DTAXG
DTDA DTDA.ni DTK DTMCPack DTRreg dtt dummies dummy dunn.test DvDdata Dykstra
DYM DynamicDistribution dynamicTreeCut DynClust DynDoc DZEXPM EBASS EBEN EBrank
ecodist ECOSolveR EcoVirtual EDR eegkitdata EffectsRelBaseline effsize
EGSEAdata eigenmodel EL ELBOW elec ellipse ellipsis ELMR ELMSO emdist emg
EMMIXmfa EMMLi emoa EmpiricalBrownsMethod EMT encode english enrichwith ensurer
entropy EntropyEstimation EntropyExplorer enviPat EpiEstim epitools equate err
errors estimability etrunct evaluate evd eventdataR evir Exact exactRankTests
expint extrafontdb FAdist fANCOVA fanplot fansi fastcluster fastdigest fastICA
fastmatch fasttime fdrtool FField fftw fftwtools fgui filehash filelock
filematrix filenamer findpython fingerprint FIs fishMod FITSio flashClust float
flowPeaks flsa fmsb FMStable FNN fontBitstreamVera fontLiberation foreign
formatR Formula fortunes fpca fpCompare fpow fracdiff FRACTION frbs functional
futile.options FuzzyNumbers fuzzyRankTests gamlss.data GANPAdata gap gbRd GCD
gcookbook gcspikelite gdsfmt gee geepack geigen gelnet genalg GenBinomApps
generics GenomeInfoDbData GenSA geodist geomapdata geoscale getopt GFA gglasso
ggplot2movies GIGrvg GillespieSSA git2r glasso glassoFast glinternet glm2
glmmML GlobalOptions globalOptTests glpkAPI glue gmp gmt goftest gower
GPArotation gridBase grndata grnn grplasso grr GSA gsl gsmoothr gss gtable
gtools gvlma GWASExactHW h5vcData hamlet HandTill2001 HaploSim hash HDInterval
heatmap.plus hellno hexView HGNChelper hgu133plus2frmavecs HI HiCseg
HiddenMarkov hierNet highlight highr HistData histogram hmeasure HMM homtest
horseshoe howmany hpar HSAUR2 HSMMSingleCell httpcode httpRequest hwriter
HyperbolicDist hypergea ibdreg iC10TrainingData ica ICC icd.data idr iemiscdata
igraphdata Illumina450ProbeVariants.db Imap IMPACT import impute ineq infotheo
infuser ini inline insight install.load interactionTest InterVA4 InterVA5
intervals invgamma iotools ipfp ISLR Iso ISOcodes ISwR ITALICSData iterators
janeaustenr JASPAR2016 JASPAR2018 JavaGD jiebaRD Jmisc jointDiag jpeg jsonlite
kedd keep kernlab KernSmooth KFAS KMsurv KOdata kolmim kpeaks kriging kstMatrix
kyotil kza L1pack labeling labelVector lagged LaplacesDemon lars lasso2
lassoshooting latexpdf lazyData lazyeval LBE LCA LCFdata lda LDRTools leaps
LearnBayes lfactors lgtdl LiblineaR limma linLIR lintools lisp lisrelToR
listarrays listenv llogistic lmeNBBayes lmf lmodel2 lmom lmPerm locfdr locpol
log4r logging logitnorm loglognorm logspline lomb longmemo LowMACAAnnotation
LowRankQP LPCM LPE lpint lpridge lpSolve lpSolveAPI lpsymphony LSD lsei lsr
ltsa lunar LungCancerACvsSCCGEO LymphoSeqDB MAc MAd magrittr MALDIquant
manipulate mapplots maps march MASS matlab matpow matrixcalc MatrixEQTL
matrixStats MaxSkew MBCluster.Seq mblm mcbiopi mcc MCI mclust mcmc mco
mCSEAdata measurements measures mefa memuse metaRNASeq Metrics MGRASTer mgsub
microbenchmark mime miniGUI minimalRSD minpack.lm minval miRcompData miscTools
mise MissMech mitoODEdata mix mixture mlbench MLEcens mlegp mmap MMWRweek
mnormt modelObj modeltools modes modules moments mosaicData MPDiR mppa mpt mRm
msgps mstR multcompView MultinomialCI multiplex multitaper muStat mvbutils
MVCClass mvmeta mvnmle mvnormtest mvrtn mvtnorm NAEPprimer naivebayes na.tools
naturalsort NatureSounds nat.utils NbClust ncbit ncdf4 ncvreg nipals NISTunits
nleqslv nlmrt nloptr NLP nlstools NMOF nnet nnlasso nnls NonCompart
nontargetData nor1mix norm normalp nortest Nozzle.R1 nsprcomp nsRFA numbers
numDeriv nutshell.audioscrobbler nutshell.bbdb oaqc Oarray objectSignals
ontologyIndex oompaData OpenMPController operators operator.tools
OptimalCutpoints optionstrat orca ore OrgMassSpecR ORIClust
orthogonalsplinebasis osDesign outliers overlap pack packrat paintmap palr pan
parmigene parody parsedate parsetools passport pbapply pbdZMQ pbivnorm
pbmcapply pbs PCAmixdata PCICt PCIT pcse pcxnData pdc pdist PDSCE PeakError
PearsonDS perm PermAlgo permute pgmm pgnorm phonTools phylotate
PhysicalActivity pinfsc50 pingr pipeR pixmap PK pkgcond pkgconfig plogr plot3D
plotfunctions plotrix plotwidgets pls plus PMCMR png POET poibin PoiClaClu
poilog polspline polyclip polynom postlogic powerMediation pps pracma praise
PreciseSums preprocessCore PresenceAbsence prettyGraphs prettyR profileModel
profmem proftools proj4 ProjectTemplate PropCIs PROscorerTools ProtGenerics
proto protoclust proxy PRROC ps pso pspearman pspline psy psychotools pvclust
pwr pwt qap qdapDictionaries qrng qrnn qtl quadprog QUIC qvcalc R2HTML R6
RadioSonde rainfarmr rama ramify RandomFieldsUtils randomForest randomForestSRC
randomizr randtests RANN RApiDatetime rapidjsonr RApiSerialize rappdirs
rateratio.test rbenchmark Rbowtie2 rbugs Rcapture rcdd RCEIM RCircos
RColorBrewer Rcpp Rcpp11 RcppParallel RcppProgress RcppThread Rcsdp rda rDNAse
rdrobust Rdsdp readBrukerFlexData readHAC REAT rebus.base REdaS registry
regress rehh.data reliaR relimp rematch remotes reports Rfit rgen rgenoud
RGMQLlib rhli rhoR RhpcBLASctl RISmed RITANdata rivernet riverplot rJava rje
rjson RJSONIO RKEELdata rkt Rlab rlang rlecuyer rmeta R.methodsS3 rmio Rmpi
rmsfact RMTstat rmutil RNAseqData.HNRNPC.bam.chr14 RNetCDF rngWELL RobAStRDA
robcor robeth robumeta RobustRankAggreg ROC RODBC rootSolve rowr rpart rphast
RPMG RProtoBufLib rrBLUP rredis RRF RRNA RRPP RSpincalc rstackdeque rstantools
rstiefel rstream rstudioapi Rsubread rsvg RSVGTipsDevice Rtauchen rTensor
RTriangle Rttf2pt1 RUnit Runuran rvgtest RViennaCL Rwave RWiener rzmq s20x
SamplingBigData samplingVarEst SamSPECTRAL sas7bdat SAScii scatterplot3d scico
sciplot SCMA scrime SCRT scs SCVA searcher segmented Segmentor3IsBack Sejong
sensitivityfull sensitivitymv separationplot seq2pathway.data seqCNA.annot
seqLogo seqminer serial setRNG sets settings sfa sfsmisc sgeostat shades shape
sig sigclust sigmoid sigPathway simex simpIntLists simplegraph
SimplicialCubature SKAT skewt slam SLC smaa smatr smoothie SMR SMVar SNAGEEdata
snow SnowballC SoDA sodium som someMTP sonicLength sourcetools spacesXYZ spanel
sparcl SparseGrid SparseM sparsepp spatialCovariance SpatialNP SpatialPack
spatstat.utils spc spData splines2 splus2R splusTimeDate SPSL SQUAREM squash
sROC ssanv ssize.fdr stabledist stabs StanHeaders stargazer startupmsg statmod
steepness stemHypoxia sticky stinepack stoichcalc stratification stringdist
stringi subplex subprocess SuppDists survivalROC survJamda.data svd svGUI
SVM2CRMdata svMisc svmpath svUnit swagger sylly sys sysfonts tabuSearch Tariff
tau TCGAbiolinksGUI.data TeachingSampling teigen tensor tensorA tester testit
texreg textutils tframe ThreeWay tictoc tiff tightClust timeDate TimeWarp
timsac tinesath1cdf tis titanic tkRplotR tmvmixnorm topmodel Trading trapezoid
tree triangle trimcluster tripack truncnorm trust tsModel tsne ttutils
TunePareto tuple TurtleGraphics tweedie twiddler tximport txtplot ucminf
udunits2 uniqtag unix uroot utf8 utility uuid varhandle variables vbsr venn
versions VGAM vipor viridisLite VisuClust vortexRdata wavelets waveslim
weathermetrics wesanderson whisker widgetTools wikibooks WilcoxCV withr
woeBinning wpp2012 wpp2017 wrapr wrassp writexl WriteXLS x13binary xfun Xmisc
XML xmlparsedata xtable xtermStyle yacca yaImpute yaml yesno zeallot zip zipfR
zlibbioc zoom""".split()


def rewrite_needs_witch(old_values):
    out = old_values.copy()
    for k in need_which_in_3_9:
        if k in out and not "which" in old_values[k]:
            out[k] = out[k] + ["which"]
        else:
            out[k] = ["which"]
    return out


def rust_inputs(pkg):
    return [
        nix_literal(
            f"(importCargo {{ lockFile = ./../cargos/{pkg}/Cargo.lock; inherit pkgs; }}).cargoHome"
        ),
        "rustc",
        "cargo",
    ]


native_build_inputs.inherit(
    "3.9",  # 2019-05-03
    {
        "apcf": ["gdal", "geos"],
        "av": ["pkgconfig", "ffmpeg", "which"],
        "ccfindR": ["gsl_1"],
        "DepecheR": ["binutils"],
        "gifski": rust_inputs("gifski"),
        "h5": ["hdf5-cpp", "which"],
        "KFKSDS": ["which", "gsl_1"],
        "LCMCR": ["gsl_1", "which"],
        "netboost": ["perl"],
        "opencv": ["pkgconfig", "opencv"],
        "qpdf": ["libjpeg"],
        "Rbowtie": ["zlib", "which"],
        "restatapi": ["pkgconfig"],
        "RGtk2": ["pkgconfig", "pkgs.gtk2.dev"],
        "Rhdf5lib": ["hdf5-cpp", "which", "zlib"],
        "rtk": ["zlib"],
        "udunits2": ["udunits", "expat", "which"],
        "units": ["udunits", "expat"],
        "universalmotif": ["binutils"],
        "unrtf": ["pcre", "lzma", "bzip2", "zlib", "icu"],
    },
    [
        "birte",
        "zstdr",
        "MonetDBLite",
    ],
    copy_anyway=True,
    rewriter=rewrite_needs_witch,
)


def handle_renames(lookup):
    def fix(input):
        output = {}
        for k, v in input.items():
            output[k] = [lookup.get(x, x) for x in v]
        return output

    return fix


native_build_inputs.inherit(
    "3.10",
    {
        "bbl": ["gsl_1"],
        "clpAPI": ["pkgconfig", "clp"],
        "data.table": ["zlib"],
        "DRIP": ["gsl_1"],
        "fftwtools": ["pkgs.fftw.dev"],
        "gdalcubes": ["pkgconfig", "gdal", "proj", "curl", "sqlite"],
        "gert": ["libgit2"],
        "gsl": ["gsl"],  # might need 2?
        "hdf5r": ["hdf5"],
        "hipread": ["zlib"],
        "hSDM": ["gsl_1"],
        "infercnv": ["python"],
        "keyring": ["pkgconfig", "pkgs.openssl", "pkgs.openssl.out", "libsecret"],
        "KFKSDS": ["pkgconfig", "gsl_1"],
        "kmcudaR": ["cudatoolkit"],
        "landsepi": ["gsl_1"],
        "Libra": ["gsl_1"],
        "netboost": ["perl"],
        "odbc": ["libiodbc"],
        "opencv": ["opencv3"],
        "openssl": ["pkgs.openssl", "pkgs.openssl.out"],
        "ragg": ["freetype", "pkgconfig", "libpng", "libtiff"],
        "RcppMeCab": ["mecab"],
        "Rhdf5lib": ["zlib"],
        "RMariaDB": ["zlib", "pkgs.mysql.connector-c", "openssl"],
        "Rmpi": ["openmpi"],
        "RMySQL": ["zlib", "pkgs.mysql.connector-c", "openssl"],
        "RODBC": ["libiodbc"],
        "ROpenCVLite": ["cmake"],
        "rPython": ["which", "python"],
        "rrd": ["pkgconfig", "rrdtool"],
        "Rsampletrees": ["gsl_1"],
        "rscala": ["scala"],
        "rtmpt": ["gsl_1"],
        "scModels": ["mpfr"],
        "SICtools": ["ncurses"],
        "spate": ["pkgconfig", "fftw"],
        "systemfonts": ["fontconfig"],
        "ulid": ["zlib"],
        "units": ["udunits"],
        "V8": ["v8_3_14"],
        "websocket": ["openssl"],
        "writexl": ["zlib"],
        "salso": rust_inputs("salso"),
    },
    ["rMAT", "rphast", "infuser", "rbugs", "VisuClust", "MSeasyTkGUI", "BayesH"],
    copy_anyway=True,
    rewriter=handle_renames(
        {
            "gsl": "gsl_1",
            "openssl": "pkgs.openssl.dev",
            "libtiff": "pkgs.libtiff.dev",
        }
    ),
)
native_build_inputs.inherit(
    "3.11",
    {
        "TKF": ["gsl_1"],
        "missSBM": ["which"],
        "nloptr": ["nlopt", "pkgconfig"],
        "terra": ["gsl_1", "gdal", "pkgconfig", "proj"],
        "registr": ["zlib", "bzip2", "lzma"],
        "imager": ["x11"],
        "rpg": ["pkgconfig", "postgresql"],
        "cytolib": ["which"],
        "rGEDI": ["pkgconfig", "gsl_1", "libgeotiff", "szip"],
        "GMMAT": ["bzip2"],
        "rtiff": ["libtiff"],
        "PythonInR": ["which"],
        "PoissonBinomial": ["fftw"],
        "RMySQL": ["zlib", "libmysqlclient"],
        "RMariaDB": ["zlib", "libmysqlclient", "openssl"],
        "V8": ["v8"],
        "baseflow": rust_inputs("baseflow"),
    },
    [
        "DZEXPM",
        "EDR",
        "mRm",
        "nutshell.audioscrobbler",
        "nutshell.bbdb",
        "rda",
        "reports",
        "rowr",
        "subprocess",
        "SnakeCharmR",
        "sbrl",
        "h5",
        "zeligverse",
        "gitter",
        "KRIG",
        "ARTP",
        "breakaway",
        "DAAGxtras",
        "DALEX2",
        "DEDS",
        "DEMEtics",
        "rpg",
        "rPython",
        "rtfbs",
        "rtiff",
        "dbConnect",
        "TKF",
        "WhopGenome",
        "Segmentor3IsBack",
        "geoCount",
        "R2GUESS",
        "rbamtools",
        "RJaCGH",
        "RODBCext",
    ],
    copy_anyway=True,
)
native_build_inputs.inherit(
    ("3.11", "2020-09-09"),  # wrong date, TODO
    {},
    [
        "outbreaker",
        "qtbase",
        "qtpaint",
    ],
)

native_build_inputs.inherit(
    "3.12",
    {
        "briskaR": ["binutils"],
        "ChemmineOB": ["openbabel", "pkgconfig"],
        "clustermq": ["pkgconfig", "zeromq4"],
        "collapse": ["binutils"],
        "cytolib": ["boost17x"],
        "hadron": ["gsl_1"],
        "image.CannyEdges": [
            "fftw",
            "libpng",
            "pkgconfig",
        ],
        "image.textlinedetector": ["pkgconfig", "opencv4"],
        "n1qn1": ["gfortran"],
        "pathfindR": ["jdk"],
        "prospectr": ["binutils"],
        "registr": [
            "icu",
            "zlib",
            "bzip2",
            "lzma",
        ],
        "rkeops": ["cmake"],
        "symengine": [
            "gmp",
            "cmake",
            "mpfr",
        ],
        "textshaping": ["pkgconfig", "harfbuzz", "freetype", "fribidi"],
        "webp": ["pkgconfig", "libwebp"],
        "websocket": ["openssl"],
    },
    [
        "MotIV",
        "pbdNCDF4",
        "gpuR",
        "Rsampletrees",
        "fastrtext",
        "BaylorEdPsych",
        "CCAGFA",
        "clues",
        "MissMech",
        "modes",
        "mvnmle",
        "PCIT",
        "TKF",
    ],
    copy_anyway=True,
)
native_build_inputs.inherit(
    "3.13",
    {
        "ChemmineOB": ["openbabel3", "pkgconfig", "eigen"],
        "divest": ["zlib"],
        "eaf": ["gsl_1"],
        "fftwtools": ["pkgconfig", "fftw"],
        "GeoFIS": ["gmp", "pkgconfig", "mpfr"],
        "gpuMagic": ["opencl-clang"],
        "kgrams": ["binutils"],
        "multibridge": ["mpfr"],
        "OpenABMCovid19": ["gsl_1"],
        "permGPU": ["cudatoolkit"],
        "resemble": ["binutils"],
        "rgl": [
            "libGLU",
            "pkgs.libGLU.dev",
            "libGL",
            "xlibsWrapper",
            "pkgconfig",
            "libpng",
            "freetype",
            "zlib",
            "pandoc",
        ],
        "SPARSEMODr": ["gsl_1"],
        "stockfish": ["which"],
        "strucchangeRcpp": ["binutils"],
        "tesseract": ["pkgconfig", "tesseract", "leptonica"],
        "tiledb": ["tiledb"],
        "Travel": ["fuse", "pkgconfig"],
    },
    [
        "ACCLMA",
        "cghseg",
        "CR",
        "dgodata",
        "ELBOW",
        "hypergea",
        "mitoODEdata",
        "parsetools",
        "PythonInR",
        "QUIC",
        "rggobi",
        "rpg",
        "rTANDEM",
        "rtiff",
        "rvgtest",
    ],
    copy_anyway=True,
)

native_build_inputs.inherit(
    ("3.13", "2021-05-31"),
    {
        "proj4": ["proj", "sqlite"],
        "XLConnect": ["jdk8"],
        "MSGFplus": ["which", "jdk8"],
    },
)
native_build_inputs.inherit(
    ("3.13", "2021-06-02"),
    {
        "valse": ["gsl_1", "pkgconfig"],
    },
    [
        "ArgumentCheck",
    ],  # lost because gama disappeard from cran
)


native_build_inputs.inherit(
    "3.14",
    {
        "archive": ["pkgconfig", "libarchive"],
        "arrow": ["cmake", cran_track_package("arrow-cpp_5.0.0")],
        "cartogramR": ["fftw"],
        "GPBayes": ["gsl_1"],
        "h2o": ["jdk"],
        "httpuv": ["zlib"],
        "MatchIt": ["binutils"],
        # "MSGFplus": ["which", "jdk8"],
        # "proj4": ["proj", "sqlite"],
        "rawrr": ["mono"],
        "rbedrock": ["cmake", "zlib"],
        "strawr": ["curl"],
        "terra": ["gsl_1", "gdal", "pkgconfig", "proj", "sqlite", "geos"],
        "vapour": ["pkgconfig", "gdal", "proj", "geos", "sqlite"],
        "rsbml": [cran_track_package("libSMBL"), "pkgconfig"],
        "vdiffr": ["libpng"],
        "string2path": rust_inputs("string2path"),
        "HierO": ["bwidget"],
        "caviarpd": rust_inputs("caviarpd"),
        "Rmpi": ["openmpi", "openssh"],
    },
    [
        "AMORE",
        "collapse",
        "DEploid",
        "graphscan",
        "heatmap.plus",
        "Libra",
        "OpenABMCovid19",
        "OpenMPController",
        "sdols",
        "sROC",
    ],
    copy_anyway=True,
)
native_build_inputs.inherit(
    ("3.14", "2021-10-28"),
    {
        "arrow": [
            "cmake",
            cran_track_package(
                "arrow-cpp_6.0.0",
                """
                (
                  pkgs.callPackage ./../packages/arrow-cpp_6.0.0.nix {}
                )
                """,
            ),
        ],
    },
    [],
)
native_build_inputs.inherit(
    ("3.14", "2021-11-04"),
    {
        "IP": ["libidn"],
    },
    ["CLA"],
)
native_build_inputs.inherit(
    ("3.14", "2021-11-05"),
    {
        "cuda.ml": ["which"],
    },
    [],
)
native_build_inputs.inherit(
    ("3.14", "2021-11-06"),
    {},
    [
        "abn",
        "pbdPROF",
        "pbdSLAP",
        "Rhpc",
        "dynr",
        "permGPU",
        "pbdBASE",
        "mvst",
        "kmcudaR",
        "KSgeneral",
        "JMcmprsk",
        "BALD",
        "spate",
        "rGEDI",
    ],
)
native_build_inputs.inherit(
    ("3.14", "2021-11-08"),
    {"dynr": ["gsl_1"]},
)
native_build_inputs.inherit(
    ("3.14", "2021-11-12"),
    {"agtboost": ["binutils"]},
)

native_build_inputs.inherit(
    ("3.14", "2021-11-17"),
    {},
    [
        "bnpmr",
        "kgrams",
    ],
)

native_build_inputs.inherit(
    ("3.14", "2021-11-18"),
    {},
    [
        "IP",
    ],
)

native_build_inputs = native_build_inputs.to_dict()

build_inputs = Inheritor()  # run time dependencies
# note that in here, it's still 'r packages names', so 'nat.blast', not 'nat_blast'
build_inputs.inherit(
    "3.0",
    {
        # sort -t '=' -k 2
        "adimpro": ["which", "pkgs.xorg.xdpyinfo"],
        "cairoDevice": ["pkgconfig"],
        "Cairo": ["pkgconfig"],
        "CARramps": ["which", "cudatoolkit"],
        "dti": ["which", "pkgs.xorg.xdpyinfo", "imagemagick"],
        "ecoretriever": ["which"],
        "flowQ": [
            "imagemagick"
        ],  # pretty sure it's going to need this during runtime as well
        "fftw": ["pkgconfig"],
        "geoCount": ["pkgconfig"],
        "gmatrix": ["cudatoolkit"],
        "gputools": ["which", "cudatoolkit"],
        "kza": ["pkgconfig"],
        "MSGFgui": ["jdk"],
        "mwaved": ["pkgconfig"],
        "nat.nblast": ["which"],
        "nat": ["which"],
        "nat.templatebrains": ["which"],
        "PET": ["which", "pkgs.xorg.xdpyinfo", "imagemagick"],
        "qtbase": ["perl"],
        "qtutils": ["qt4"],
        "R2SWF": ["pkgconfig"],
        "RCurl": ["curl"],
        "rggobi": ["pkgconfig"],
        "RGtk2": ["pkgconfig"],
        "RMark": ["which"],
        "Rpoppler": ["pkgconfig"],
        "RProtoBuf": ["pkgconfig"],
        "rpud": ["which", "cudatoolkit"],
        "RPushbullet": ["which"],
        "rPython": ["which"],
        "Rsymphony": ["pkgconfig", "doxygen", "graphviz", "subversion"],
        "showtext": ["pkgconfig"],
        "spate": ["pkgconfig"],
        "stringi": ["pkgconfig"],
        "svKomodo": ["which"],
        "sysfonts": ["pkgconfig"],
        "tcltk2": ["tcl", "tk"],
        "tikzDevice": ["which", "texLive"],
        "VBmix": ["pkgconfig"],
        "WideLM": ["cudatoolkit"],
        "XML": ["pkgconfig"],
    },
)
build_inputs.inherit(
    "3.1",
    {
        "gridGraphics": ["which"],
    },
    [],
    copy_anyway=True,
)
build_inputs.inherit(
    ("3.1", "2015-07-11"),
    {
        "PythonInR": ["python"],
    },
)

build_inputs.inherit("3.2", {}, [], copy_anyway=True)
build_inputs.inherit(("3.2", "2015-11-21"), {}, ["CARramps", "rpud", "WideLM"])
build_inputs.inherit("3.3", {}, [], copy_anyway=True)
build_inputs.inherit(
    "3.4",
    {
        "tikzDevice": ["which", "pkgs.texlive.combined.scheme-medium"],
    },
    [],
    copy_anyway=True,
)
build_inputs.inherit(("3.4", "2017-03-11"), {}, ["ecoretriever"])

build_inputs.inherit("3.5", {"gridGraphics": ["imagemagick"]}, [], copy_anyway=True)

build_inputs.inherit("3.6", {}, [], copy_anyway=True)
build_inputs.inherit(
    ("3.6", "2017-12-19"),
    {},
    [
        "gmatrix",
        "gputools",
    ],
)

build_inputs.inherit(
    ("3.6", "2018-02-01"),
    {},
    ["qtutils"],
)

build_inputs.inherit(
    ("3.6", "2018-03-05"),
    {},
    ["VBmix"],
)


build_inputs.inherit("3.7", {}, [], copy_anyway=True)
build_inputs.inherit("3.8", {}, ["flowQ"], copy_anyway=True)
build_inputs.inherit("3.9", {}, [], copy_anyway=True)
build_inputs.inherit(
    "3.10",
    {
        "tikzDevice": ["which", "pkgs.texlive.combined.scheme-medium"],
        "openssl": ["pkgconfig", "pkgs.openssl.out"],
        "tesseract": ["pkgconfig"],
        "redland": ["pkgconfig"],
        "landsepi": ["gsl_1"],
        # "BayesSAE": ["gsl_1"],
        # "BayesVarSel": ["gsl_1"],
        # "ChemmineOB": ["openbabel", "pkgconfig"],  # experimental
        # "cld3": ["pkgconfig", "protobuf"],
        # "curl": ["pkgconfig"],
        # "fftwtools": ["pkgconfig"],
        # "HilbertVisGUI": ["pkgconfig"],
        # "KFKSDS": ["gsl_1"],
        # "KSgeneral": ["pkgconfig"],
        # "Libra": ["gsl_1"],
        # "PKI": ["openssl"],
        # "PopGenome": ["zlib"],
        # "R2SWF": ["pkgconfig", "zlib", "libpng", "freetype"],
        # "Rsubread": ["zlib"],
        # "SemiCompRisks": ["gsl_1"],
        # "showtext": ["pkgconfig", "zlib", "libpng", "freetype", "icu"],
        # "stsm": ["gsl_1"],
        # "sysfonts": ["pkgconfig", "zlib", "libpng", "freetype"],
        # "TAQMNGR": ["gsl_1"],
        # "RcppZiggurat": ["gsl_1"],
        # "Rglpk": ["glpk"],
        # "RMySQL": ["zlib", "pkgs.mysql.connector-c", "openssl"],
        # "curl": ["pkgconfig", "curl"],
        # "fftwtools": ["pkgs.fftw.dev"],
        # "BALD": ["jags"],
        # "RODBC": ["libiodbc"],
        # "Rhtslib": ["zlib"],
    },
    [],
    copy_anyway=True,
)
build_inputs.inherit(
    "3.11",
    {},
    [
        "geoCount",
        "rPython",
        "PET",
    ],
    copy_anyway=True,
)
build_inputs.inherit(("3.11", "2020-09-09"), {}, ["qtbase"])  # Todo: fix date

build_inputs.inherit("3.12", {}, [], copy_anyway=True)
build_inputs.inherit(
    "3.13",
    {},
    [
        "rggobi",
        "PythonInR",
    ],
    copy_anyway=True,
)
build_inputs.inherit("3.14", {}, [], copy_anyway=True)
build_inputs.inherit(("3.14", "2021-11-06"), {}, ["spate"])


build_inputs = build_inputs.to_dict()


skip_check = Inheritor("list")
# in R names please, not the safe_for_nix names
skip_check.inherit(
    "3.0",
    [
        "Rmpi",  # tries to run MPI processes
        "gmatrix",  # requires CUDA runtime
        "sprint",  # tries to run MPI processes
    ],
)
skip_check.inherit(
    ("3.0", "2014-10-26"),
    [
        "metaMix",
        "bigGP",
    ],
)  # tries to run MPI processes
skip_check.inherit("3.1", [], [], copy_anyway=True)
skip_check.inherit("3.2", [], [], copy_anyway=True)
skip_check.inherit("3.3", [], [], copy_anyway=True)
skip_check.inherit("3.4", [], [], copy_anyway=True)
skip_check.inherit("3.5", [], [], copy_anyway=True)
skip_check.inherit("3.6", [], [], copy_anyway=True)
skip_check.inherit("3.7", [], ["gmatrix", "sprint"], copy_anyway=True)
skip_check.inherit(
    "3.8",
    [
        "HMP16SData",
        "DuoClustering2018",
        "TabulaMurisData",
    ],
    [],
    copy_anyway=True,
)
skip_check.inherit(
    "3.9",
    [
        "FlowSorted.CordBloodCombined.450k",
        "benchmarkfdrData2019",
        "bodymapRat",
        "depmap",
        "muscData",
        "HDCytoData",
    ],
    [],
    copy_anyway=True,
)
skip_check.inherit(
    "3.10",
    [
        "RNAmodR.Data",
    ],
    ["gmatrix", "sprint"],
    copy_anyway=True,
)  # MPI
skip_check.inherit(
    "3.11",
    [
        "SCATEData",
    ],
    [],
    copy_anyway=True,
)
skip_check.inherit(
    "3.12",
    [
        "clustifyrdatahub",
        "FieldEffectCrc",
        "metaboliteIDmapping",
    ],
    [],
    copy_anyway=True,
)
skip_check.inherit(
    "3.13",
    [
        # many (all?) AnnotationHub dependend packages trie to download / write to home during install
        "GenomicDistributionsData",
        "TENxVisiumData",
        "STexampleData",
        "scpdata",
        "emtdata",
        "msigdb",
        "org.Mxanthus.db",
        "SCATE",
        "SingleMoleculeFootprintingData",
        "PANTHER.db",
    ],
    [],
    copy_anyway=True,
)
skip_check.inherit(
    "3.14",
    [
        # many (all?) AnnotationHub dependend packages trie to download / write to home during install
        "MicrobiotaProcess",
        "nullrangesData",
        "spatialDmelxsim",
        "synaptome.db",
        "imcdatasets",
    ],
    [],
    copy_anyway=True,
)


skip_check = skip_check.to_dict()
# skip_check.inherit("3.2", [], [], copy_anyway=True)


needs_x = set(  # let's presume they never go from 'need X' no 'not need X'
    # so no per version
    # having one of these in your 'suggests'
    # will make you requireX on installation
    # (we don't go for full transitivity here
    # because building anything with X is *slow*)
    [
        "tcltk",
        "tcltk2",
        "gWidgets2RGtk2",
        "gWidgets2tcltk",
        "gWidgetsRGtk2",
        "gWidgetstcltk",
        "tkrplot",
        "cairoDevice",
        "RGtk2",
        "geoR",
        "qtbase",
        # "vegan",  # which 'suggests' tcltk
        "iplots",
        "rgeos",
        "Deducer",
        "mutossGUI",
        # endless tcl loops otherwise
        "euroMix",
        "Geneland",
        "RcmdrPlugin.ROC",
        "spatsurv",
        "ProbForecastGOP",
        "GeoGenetix",
        "soptdmaeA",
        "magick",
        "optbdmaeAT",  # igraph?
        "optrcdmaeAT",  # igraph?
        "rMouse",
        "hierO",  # if it still doesn't work, exclude..
        "loon",
        "rgl",
        "devEMF",
        "pcrsim",
        "MSeasyTkGUI",
        "imager",
        "switchboard",
    ]
)


needs_rust = {
    # location of Cargo.lock inside the tar.gz
    "gifski": "gifski/src/myrustlib",
    "baseflow": True,  # use cran_tracker_for_nix/carosg/pkg_version/Cargo.lock. Because the package has none.
    "string2path": "string2path/src/rust",
    "salso": "salso/src/rustlib",
    "caviarpd": "caviarpd/src/rustlib",
}

patches_by_package_version = {}

patches = Inheritor("dict")
patches.inherit(
    "3.0",
    {
        "affy": ["affy_1.44.no_bioc_installer.patch"],
        "gcrma": ["gcrma_2.38.no_bioc_installer.patch"],
        "webbioc": ["webbioc.1.38.0.no_bioc_installer.patch"],
        "affylmGUI": ["affylmGUI_1.40.2.no_bioc_installer.patch"],
        "BayesBridge": ["BayesBridge.patch"],
        "BayesLogit": ["BayesLogit.patch"],
        "BayesXsrc": ["BayesXsrc.patch"],
        "CARramps": ["CARramps.patch"],
        "EMCluster": ["EMCluster.patch"],
        "gmatrix": ["gmatrix.patch"],
        "gputools": ["gputools.patch"],
        # "iFes": ["iFes.patch"],
        "qtbase": ["qtbase.patch"],
        "RAppArmor": ["RAppArmor.patch"],
        "rpud": ["rpud.patch"],
        "Rserve": ["Rserve.patch"],
        "spMC": ["spMC.patch"],
        "WideLM": ["WideLM.patch"],
        "SDMTools": [
            "SDMTools.patch"
        ],  # see http://dsludwig.github.io/2019/02/12/building-up-to-something.html
        # "oligoClasses": ["oligoClasses_1.42.0.patch"],
    },
)

patches.inherit(
    ("3.0", "2015-01-11"),
    {
        "RMySQL": ["RMySQL.patch"],
    },
)


patches.inherit(
    "3.1",
    {
        "qtbase": ["qtbase.patch"],
        "RMySQL": ["RMySQL.patch"],
        "BayesXsrc": ["BayesXsrc_2.1-2.patch"],
    },
    copy_anyway=True,
)
patches.inherit(
    ("3.1", "2015-05-29"),
    {
        "qtbase": ["qtbase_1.0.9.patch"],
    },  # bc 3.1
)
patches.inherit(("3.1", "2015-10-01"), {}, ["RMySQL"])

patches.inherit(
    "3.2",
    {
        "qtbase": ["qtbase_1.0.9.patch"],
    },
    copy_anyway=True,
)
patches.inherit("3.3", {}, ["CARramps", "rpud", "WideLM"], copy_anyway=True)
patches.inherit("3.4", {}, copy_anyway=True)
patches.inherit(
    "3.5",
    {
        "redland": ["redland.patch"],
        "mongolite": ["mongolite.patch"],
        "affylmGUI": ["affylmGUI_1.50.0.no_bioc_installer.patch"],
        "qtbase": ["qtbase_1.0.14.patch"],
        "tesseract": ["tesseract_1.4.patch"],
        "googleformr": ["googleformr.patch"],  # must prevent net access during install
        "DeepBlueR": ["DeepBlueR.patch"],  # must prevent net access during install
        "RKEELjars": ["RKEELjars.patch"],  # must prevent net access during install
    },
    copy_anyway=True,
)
patches.inherit(
    "3.6",
    {
        "multiMiR": ["multiMiR.patch"],  # must prevent net access during install
    },
    copy_anyway=True,
)
patches.inherit(
    "3.7",
    {
        "tesseract": ["tesseract.patch"],
        "nearfar": ["nearfar.patch"],
    },
    [
        "EMCluster",
        "BayesBridge",
        "gmatrix",
        "gputools",
        "BayesXsrc",
    ],
    copy_anyway=True,
)
patches.inherit(
    "3.8",
    {},
    ["affy", "gcrma", "affylmGUI", "webbioc"],
    copy_anyway=True,
)
patches.inherit("3.9", {}, ["RAppArmor"], copy_anyway=True)
patches.inherit(
    "3.10",
    {
        "Rhdf5lib": ["Rhdf5lib.patch"],
        "tesseract": ["tesseract.patch"],
        "qtbase": ["qtbase_1.0.14.patch"],
        "interactiveDisplay": ["interactiveDisplay.patch"],
        "commonsMath": ["commonsMath.patch"],
    },
    [
        "BayesLogit",
    ],
    copy_anyway=True,
)
patches.inherit(
    "3.11",
    {
        "snapcount": ["snapcount.patch"],
        "spiR": ["spiR.patch"],
    },
    ["mongolite"],
    copy_anyway=True,
)
patches.inherit(
    "3.12",
    {
        "rfaRm": ["rfaRm.patch"],  # try() around on-load network access
        "packagefinder": ["packagefinder.patch"],
    },
    ["qtbase", "SDMTools"],
    copy_anyway=True,
)
patches.inherit(
    "3.13",
    {
        "immunotation": [
            "immunotation_1.0.0.patch"
        ],  # try() around on-load network access
        "ReactomeContentService4R": [
            "ReactomeContentService4R.patch"
        ],  # try() around on-load network access
        "iriR": ["iriR.patch"],  # try() around on-load network access
        "waddR": ["waddR.patch"],  # try() around on-load network access
        "nfl4th": ["nfl4th.patch"],  # try() around on-load network access
        "GeneBook": ["GeneBook.patch"],  # try() around on-load network access
        "SCATEData": ["SCATEData.patch"],
        "dmdScheme": ["dmdScheme.patch"],  # try around on-load network access
        "tesseract": ["tesseract_4.1.2.patch"],
    },
    [],
    copy_anyway=True,
)
patches.inherit(
    ("3.13", "2021-05-31"),
    {
        "salso": ["salso_0.22.patch"],
    },
)
patches.inherit(
    ("3.13", "2021-06-02"),
    {
        "valse": ["valse.patch"],
    },
)

patches.inherit(
    "3.14",
    {
        "immunotation": ["immunotation.patch"],  # try() around on-load network access
        "robis": ["robis.patch"],
        "x13binary": ["x13binary_1.57.patch"],
        "signatureSearch": ["signatureSearch.patch"],
    },
    ["GeneBook", "salso"],
    copy_anyway=True,
)
patches.inherit(("3.14", "2021-11-08"), {}, ["nearfar"])
patches.inherit(
    ("3.14", "2021-11-18"),
    {
        "RKEELjars": [
            "RKEELjars_1.0.20.patch"
        ],  # must prevent net access during install
    },
)


patches = patches.to_dict()

attrs = Inheritor()
shebangs = {"postPatch": "patchShebangs configure"}
fix_strip = {  # don't forget to add binutils to the native_build_inputs
    "postPatch": 'substituteInPlace src/Makevars --replace "/usr/bin/strip" "strip"'
}
fake_home = {
    "HOME": "$TMPDIR",  # cache will be recreated if missing during runtime, so no problem here
}
attrs.inherit(
    "3.0",
    {
        "CARramps": {
            "hydraPlatforms": "stdenv.lib.platforms.none",
            "configureFlags": ["--with-cuda-home=${pkgs.cudatoolkit}"],
        },
        "devEMF": {"NIX_CFLAGS_LINK": "-L${pkgs.xlibs.libXft}/lib -lXft"},
        "gmatrix": {
            "CUDA_LIB_PATH": "${pkgs.cudatoolkit}/lib64",
            "R_INC_PATH": "${pkgs.R}/lib/R/include",
            "CUDA_INC_PATH": "${pkgs.cudatoolkit}/usr_include",
        },
        "gputools": {"CUDA_HOME": "${pkgs.cudatoolkit}"},
        # "iFes": {"CUDA_HOME": "${pkgs.cudatoolkit}"},
        "JavaGD": {
            "preConfigure": """
        export JAVA_CPPFLAGS=-I${pkgs.jdk}/include/
        export JAVA_HOME=${pkgs.jdk}
        """
        },
        # It seems that we cannot override meta attributes with overrideDerivation.
        "Mposterior": {"PKG_LIBS": "-L${pkgs.openblasCompat}/lib -lopenblas"},
        "nloptr": {
            "configureFlags": [
                "--with-nlopt-cflags=-I${pkgs.nlopt}/include "
                "--with-nlopt-libs='-L${pkgs.nlopt}/lib -lnlopt_cxx -lm'"
            ]
        },
        "RAppArmor": {"LIBAPPARMOR_HOME": "${pkgs.libapparmor}"},
        "RcppArmadillo": shebangs,
        "rJava": {
            "preConfigure": """
                export JAVA_CPPFLAGS=-I${pkgs.jdk}/include/
                export JAVA_HOME=${pkgs.jdk}
        """
        },
        "Rmpfr": {"configureFlags": ["--with-mpfr-include=${pkgs.mpfr}/include"]},
        "Rmpi": {
            "configureFlags": [
                "--with-Rmpi-type=OPENMPI",
                "--with-Rmpi-include=${pkgs.openmpi}/include",
                "--with-Rmpi-libpath=${pkgs.openmpi}/lib",
            ]
        },
        "RMySQL": {"MYSQL_DIR": "${pkgs.mysql.lib}"},
        "rpf": shebangs,
        "rpud": {
            "hydraPlatforms": nl("stdenv.lib.platforms.none"),
            "CUDA_HOME": "${pkgs.cudatoolkit}",
        },
        "Rserve": {"configureFlags": ["--with-server" "--with-client"]},
        "RVowpalWabbit": {
            "configureFlags": [
                "--with-boost=${pkgs.boost.dev}",
                "--with-boost-libdir=${pkgs.boost.lib}/lib",
            ],
        },
        "SamplerCompare": {"PKG_LIBS": "-L${pkgs.openblasCompat}/lib -lopenblas"},
        "slfm": {"PKG_LIBS": "-L${pkgs.openblasCompat}/lib -lopenblas"},
        "SJava": {
            "preConfigure": """
        export JAVA_CPPFLAGS=-I${pkgs.jdk}/include
        export JAVA_HOME=${pkgs.jdk}
        """
        },
        "WideLM": {"configureFlags": ["--with-cuda-home=${pkgs.cudatoolkit}"]},
        "rgdal": {
            "PROJ_LIB": "${pkgs.proj}/",
            "configureFlags": ["--with-proj-share=${pkgs.proj}/share/proj"],
        },
    },
)
attrs.inherit(
    ("3.0", "2014-10-22"),
    {
        "openssl": {
            "OPENSSL_INCLUDES": "${pkgs.openssl}/include",
            "LD_LIBRARY_PATH": "${pkgs.openssl.out}/lib;",
        },
    },
)
attrs.inherit(
    ("3.0", "2014-11-21"),
    {
        "curl": {"preConfigure": "export CURL_INCLUDES=${pkgs.curl}/include"},
    },
)
attrs.inherit(
    ("3.0", "2014-12-09"),
    {
        "V8": {
            "preConfigure": "export V8_INCLUDES=${pkgs.v8}/include",
        },
    },
)


attrs.inherit(
    "3.1",
    {
        "HierO": {
            "postUnpack": """
sed -i '3iaddTclPath\("${pkgs.bwidget}/lib"\)' /build/HierO/R/HierO.R
head /build/HierO/R/HierO.R -n 5
"""
        },
    },
    copy_anyway=True,
)

attrs.inherit(
    ("3.1", "2015-04-21"),
    {
        "xml2": {
            "preConfigure": "export LIBXML_INCDIR=${pkgs.libxml2}/include/libxml2"
        },
    },
)


attrs.inherit(
    ("3.1", "2015-05-28"),
    {"OpenMx": shebangs},
)

attrs.inherit(
    ("3.1", "2015-10-01"),
    {
        "curl": shebangs,
        "Rblpapi": shebangs,
        "xml2": shebangs,
        "RMySQL": shebangs,  # dict_add(shebangs, {"MYSQL_DIR": "${pkgs.mysql.connector-c}"}), # wrong todo
    },
)

attrs.inherit(
    "3.2",
    {
        "Rsomoclu": shebangs,
        "mongolite": shebangs,
        "openssl": dict_add(
            shebangs,
            {
                "OPENSSL_INCLUDES": "${pkgs.openssl}/include",
                "LD_LIBRARY_PATH": "${pkgs.openssl.out}/lib;",
            },
        ),
    },
    copy_anyway=True,
)
attrs.inherit(
    ("3.2", "2016-01-10"),
    {
        "gdtools": shebangs,
    },
    ["CARramps", "rpud", "WideLM"],
)
attrs.inherit(
    "3.3",
    {
        "RKEELjars": {
            # rkeel used to download from it's 'master' branch. I have fixed it to the respective releases.
            # you could do it by date and commit,
            # but I ain't got time for such shenanigans
            "JAR_DOWNLOAD": nix_literal(
                """builtins.fetchurl{
        url = "https://github.com/i02momuj/RKEEL/raw/d1665d7a6bda3ab1e37c654ada97cefb39e48cf2/RKEELjars/RKEELjars.zip";
        sha256 = "793490633b0a830702db531dd348b42dae6e2ea9"; 
        }"""
            )
        },  # todo: fix hash
    },
    copy_anyway=True,
)
attrs.inherit(
    "3.4",
    {
        "RVowpalWabbit": {
            "configureFlags": [
                "--with-boost=${pkgs.boost.dev}",
                "--with-boost-libdir=${pkgs.boost}/lib",
            ],
        },
    },
    ["SJava"],
    copy_anyway=True,
)
attrs.inherit(
    "3.5",
    {
        "protolite": shebangs,
        "xslt": shebangs,
        "redland": shebangs,
        "x13binary": shebangs,
        "odbc": shebangs,
        "rpg": shebangs,
        "acs": shebangs,
        "clpAPI": shebangs,
        "gpg": shebangs,
        "lpsymphony": shebangs,
        "magick": shebangs,
        "RcppGetconf": shebangs,
        "rsvg": shebangs,
        "sodium": shebangs,
        "devEMF": {
            "NIX_LDFLAGS": "-lX11",
        },
        "Cairo": {
            "NIX_LDFLAGS": "-lfontconfig",
        },
        "gdtools": dict_add(
            {
                "NIX_LDFLAGS": "-lfontconfig -lfreetype",
            },
            shebangs,
        ),
        "V8": {
            "postPatch": 'substituteInPlace configure --replace " -lv8_libplatform" ""',
            "preConfigure": """
        export INCLUDE_DIR=${pkgs.v8}/include
        export LIB_DIR=${pkgs.v8}/lib
        patchShebangs configure
      """,
        },
        "textTinyR": {
            "configureFlags": [
                "--with-boost=${pkgs.boost.dev}",
                "--with-boost-libdir=${pkgs.boost}/lib",
            ],
        },
        "SICtools": {
            "postPatch": """
substituteInPlace src/Makefile \
      --replace "CFLAGS = " "CFLAGS = -I${pkgs.ncurses.dev}/include " \
      --replace "LDFLAGS = " "LDFLAGS = -L${pkgs.ncurses.out}/lib " \
      --replace "-lcurses" "-lncurses"
      """
        },
        "mongolite": dict_add(
            shebangs,
            {
                "PKGCONFIG_CFLAGS": "-I${pkgs.openssl.dev}/include -I${pkgs.cyrus_sasl.dev}/include -I${pkgs.zlib.dev}/include",
                "PKGCONFIG_LIBS": "-Wl,-rpath,${pkgs.openssl.out}/lib -L${pkgs.openssl.out}/lib -L${pkgs.cyrus_sasl.out}/lib -L${pkgs.zlib.out}/lib -lssl -lcrypto -lsasl2 -lz",
            },
        ),
    },
    copy_anyway=True,
)
attrs.inherit(
    "3.6",
    {
        "cld3": shebangs,
        "fastrtext": fix_strip,
        "ISOpureR": fix_strip,
        "jqr": shebangs,
        "JuniperKernel": shebangs,
        "kde1d": fix_strip,
        "keyring": shebangs,
        "MAINT.Data": fix_strip,
        "RcppClassic": fix_strip,
        "RcppCWB": shebangs,
        "RcppParallel": shebangs,
        "redux": shebangs,
        "RGraphM": shebangs,
        "RMariaDB": shebangs,
        "RPostgres": shebangs,
        "rvinecopulib": fix_strip,
        "rzmq": shebangs,
        "SeqKat": fix_strip,
        "jiebaRD": {
            "postInstall": "cd $out/library/jiebaRD/dict && unzip hmm_model.zip && unzip idf.zip && unzip jieba.dict.zip\n"
        },
        "openssl": dict_add(
            shebangs,
            {
                "PKGCONFIG_CFLAGS": "-I${pkgs.openssl.dev}/include",
                "PKGCONFIG_LIBS": "-Wl,-rpath,${pkgs.openssl.out}/lib -L${pkgs.openssl.out}/lib -lssl -lcrypto",
            },
        ),
        "nloptr": {
            # Drop bundled nlopt source code. Probably unnecessary, but I want to be
            # sure we're using the system library, not this one.
            "preConfigure": "rm -r src/nlopt_src",
        },
    },
    copy_anyway=True,
)
attrs.inherit(
    "3.7",
    {
        "walker": shebangs,
        "fulltext": fake_home,
        "RKEELjars": {
            "JAR_DOWNLOAD": nix_literal(
                """builtins.fetchurl{
url = "https://github.com/i02momuj/RKEEL/raw/d1665d7a6bda3ab1e37c654ada97cefb39e48cf2/RKEELjars/RKEELjars.zip";
sha256 = "10rx41n8i90y91v138m3yx22zblzh9inlcrl4ghkbywlj5i16vzh"; 
}"""
            )
        },  # todo: fix hash
    },
    ["gmatrix", "gputools", "RGraphM"],
    copy_anyway=True,
)

attrs.inherit(
    "3.8",
    {
        "pdftools": shebangs,
        "ps": shebangs,
        "freetypeharfbuzz": shebangs,
        "msgl": fix_strip,
        "ssh": shebangs,
        "rlang": shebangs,
        "sglOptim": fix_strip,
        "wdm": fix_strip,
        "ijtiff": shebangs,
        "rPython": shebangs,
        "DeLorean": shebangs,
    },
    ["Mposterior", "rpf"],
    copy_anyway=True,
)
attrs.inherit(
    "3.9",
    {
        "av": shebangs,
        "restatapi": shebangs,
        "opencv": shebangs,
        "universalmotif": fix_strip,
        "DepecheR": fix_strip,
        "uavRst": {"installFlags": ["--no-staged-install"]},
        "zonator": {"installFlags": ["--no-staged-install"]},
        "V8": {
            "preConfigure": """
        export INCLUDE_DIR=${pkgs.v8_3_14}/include
        export LIB_DIR=${pkgs.v8_3_14}/lib
        patchShebangs configure
      """,
        },
        "gifski": {
            "postPatch": """
            substituteInPlace src/Makevars --replace "cargo build" "cargo build --offline"
            substituteInPlace src/Makevars --replace "export CARGO_HOME=\$(PWD)/.cargo" ""
            """
        },
        "RKEELjars": {
            "JAR_DOWNLOAD": nix_literal(
                """builtins.fetchurl{
url = "https://github.com/i02momuj/RKEEL/raw/fb64fc16ad4478e377877026ec59aa913b705292/RKEELjars/RKEELjars.zip";
sha256 = "10rx41n8i90y91v138m3yx22zblzh9inlcrl4ghkbywlj5i16vzh"; 
}"""
            )
        },  # todo: fix hash
        #
    },
    ["MAINT.Data"],
    copy_anyway=True,
)
attrs.inherit(
    "3.10",
    {
        "arrow": shebangs,
        "BALD": {
            "JAGS_INCLUDE": "${pkgs.jags}/include/JAGS",
            "JAGS_LIB": "${pkgs.jags}/lib",
        },
        "gert": shebangs,
        "JuniperKernel": shebangs,
        "opencv": shebangs,
        # "openssl": { "OPENSSL_INCLUDES": "${pkgs.openssl}/include", "LD_LIBRARY_PATH": '"${pkgs.openssl.out}/lib";', },
        "openssl": dict_add(
            shebangs,
            {
                "PKGCONFIG_CFLAGS": "-I${pkgs.openssl.dev}/include",
                "PKGCONFIG_LIBS": "-Wl,-rpath,${pkgs.openssl.out}/lib -L${pkgs.openssl.out}/lib -lssl -lcrypto",
            },
        ),
        # "RcppCWB": shebangs,
        "RcppGetconf": shebangs,
        "RcppParallel": shebangs,
        "rDEA": shebangs,  # experimental
        "Rglpk": shebangs,  # experimental
        "ROpenCVLite": shebangs,
        "rpg": shebangs,
        "RPostgres": shebangs,
        "rrd": shebangs,
        "strex": shebangs,
        # "sysfonts": {"strictDeps": False},
        "systemfonts": shebangs,
        "tesseract": shebangs,
        "websocket": {
            "PKGCONFIG_CFLAGS": "-I${pkgs.openssl_1_1.dev}/include",
            "PKGCONFIG_LIBS": "-Wl,-rpath,${pkgs.openssl.out}/lib -L${pkgs.openssl.out}/lib -lssl -lcrypto",
        },
        # "apcf": { # won't find gcsv.csv, even though it's in GDAL_DATA path and
        # it is finding pcs.csv in that same path, and it claims to be looking in that path
        #     "GDAL_CONFIG": "${pkgs.gdal}/bin/gdal-config",
        #     "GDAL_DATA": "$pkgs.gdal_2/share/gdal/",
        #     "PROJ_LIB": "$pkgs.proj/out",
        # },
        # "rphast": { # for documentation - Still misses pcre_compile
        # "preInstall": """
        # export CPPFLAGS="-I ${pkgs.pcre.dev}/include"
        # """, },
        # "AnnotationHub": {
        # "postInstall": "R --no-save -e 'library(AnnotationHub);AnnotationHub(localHub=F)'"
        # },
        # "ExperimentHub": {
        # "postInstall": "R --no-save -e 'library(ExperimentHub);ExperimentHub(localHub=F)'"
        # },
        "commonsMath": {
            "COMMONS_MATH_JAR": nix_literal(
                """builtins.fetchurl{
url = "https://search.maven.org/remotecontent?filepath=org/apache/commons/commons-math3/3.6.1/commons-math3-3.6.1.jar";
sha256 = "025ky9z9rfqwgp6l7yl8sp0p9dl57274bf2nsamnb2yjb2qdfmhy"; }
"""
            ),
            "PARALLEL_COLLECTIONS": nix_literal(
                """builtins.fetchurl{
url = "https://search.maven.org/remotecontent?filepath=org/scala-lang/modules/scala-parallel-collections_2.13/0.2.0/scala-parallel-collections_2.13-0.2.0.jar";
sha256 = "1lbf4hqz8l2svz5ic49bhmnqsm1db26srld3aanfk64b63qj4pyi"; }
"""
            ),
        },
        "RKEELjars": {
            "JAR_DOWNLOAD": nix_literal(
                """builtins.fetchurl{
url = "https://github.com/i02momuj/RKEEL/raw/445cd8cceade2316bc12d40406c7c1248e2daeaa/RKEELjars/RKEELjars.zip";
sha256 = "10rx41n8i90y91v138m3yx22zblzh9inlcrl4ghkbywlj5i16vzh";
}"""
            )
        },
    },
    [],
    copy_anyway=True,
)
attrs.inherit(
    "3.11",
    {
        "cytolib": shebangs,
        "RPostgres": dict_add(
            shebangs,  # seems to have gained another bash line...
            {
                "postPatch": 'substituteInPlace configure --replace "/bin/bash" "${pkgs.bash}/bin/bash"',
            },
        ),
        "missSBM": shebangs,
        "rGEDI": {
            "PROJ_LIB": "${pkgs.proj}/",
            "configureFlags": ["--with-proj-share=${pkgs.proj}/share/proj"],
        },
        "terra": {
            "PROJ_LIB": "${pkgs.proj}/",
            # "configureFlags": ["--with-proj-share=${pkgs.proj}/share/proj"],
        },
        "V8": {
            "preConfigure": """
        export INCLUDE_DIR=${pkgs.v8}/include
        export LIB_DIR=${pkgs.v8}/lib
        patchShebangs configure
      """,
            "postPatch": 'substituteInPlace configure --replace " -lv8_libplatform" ""',
        },
        "baseflow": {
            "postPatch": """
            substituteInPlace tools/staticlib.R --replace '--release",' '--release", "--offline",'
            substituteInPlace tools/staticlib.R --replace "Sys.setenv(CARGO_HOME = paste0(getwd(), '/.cargo'))" ""
            substituteInPlace tools/staticlib.R --replace "Sys.setenv(CARGO_HOME = cargo_home_backup)" ""
            """
        },
        "caviarpd": {
            "postPatch": """
            substituteInPlace tools/cargo.R --replace "env <- c(env, CARGO_HOME=n(cargo_home))" ""
            """
        },
    },
    ["JuniperKernel", "rPython", "uavRst"],
    copy_anyway=True,
)
attrs.inherit(
    "3.12",
    {
        "data.table": shebangs,
        "winch": dict_add(
            shebangs,  # seems to have gained another bash line...
            {
                "postPatch": 'substituteInPlace configure --replace "/bin/bash" "${pkgs.bash}/bin/bash"',
            },
        ),
        "image.textlinedetector": shebangs,
        "webp": shebangs,
        "s2": shebangs,
        "websocket": shebangs,
        "textshaping": shebangs,
        "clustermq": shebangs,
        "collapse": fix_strip,
        "prospectr": fix_strip,
        "briskaR": fix_strip,
        "websocket": dict_add(
            shebangs,
            {
                "PKGCONFIG_CFLAGS": "-I${pkgs.openssl.dev}/include",
                "PKGCONFIG_LIBS": "-Wl,-rpath,${pkgs.openssl.out}/lib -L${pkgs.openssl.out}/lib -lssl -lcrypto",
            },
        ),
    },
    ["Rsomoclu", "fastrtext", "websocket"],
    copy_anyway=True,
)
attrs.inherit(
    "3.13",
    {
        #
        "R.cache->>": fake_home,
        # "TreeTools": fake_home,
        "resemble": fix_strip,
        "stockfish": shebangs,
        "strucchangeRcpp": fix_strip,
        "OmnipathR": fake_home,
        "kgrams": fix_strip,
        "wppi": fake_home,  # OmnipathR downstreab
        "proj4": {
            "PROJ_LIB": "${pkgs.proj.dev}",
        },
        "ChemmineOB": {
            "OPEN_BABEL_INCDIR": "${pkgs.openbabel}/include/openbabel3/",
            "preInstall": 'substituteInPlace src/Makevars.in --replace "/usr/local/include/eigen3" "${pkgs.eigen}/include/eigen3"\n',
        },
        "SCATE": fake_home,
        "waddR": fake_home,
        "fgga": fake_home,
        # "rgl": {
        # "RGL_USE_NULL": "true",  # otherwise test-loading the installed package fails
        # },
        "rgl->": {  # rgl and all it's direct downstreams
            "RGL_USE_NULL": "true",  # otherwise test-loading the installed package fails
        },
        "patternize": {  # 2nd level rgl dependency
            "RGL_USE_NULL": "true",  # otherwise test-loading the installed package fails
        },
        "fitbitViz": {  # 2nd level rgl dependency
            "RGL_USE_NULL": "true",  # otherwise test-loading the installed package fails
        },
        "red": {  # test
            "RGL_USE_NULL": "true",  # otherwise test-loading the installed package fails
        },
        "fdasrvf": {  # test
            "RGL_USE_NULL": "true",  # otherwise test-loading the installed package fails
        },
        "GPoM.FDLyapu": {  #  2nd level rgl dependency
            "RGL_USE_NULL": "true",  # otherwise test-loading the installed package fails
        },
        "h2o": {
            "preInstall": """
ls /build
mkdir /build/h2o/inst/java
cp $jarSource/h2o.jar /build/h2o/inst/java
""",
            "jarSource": nix_literal(
                """pkgs.fetchzip{
        url="http://h2o-release.s3.amazonaws.com/h2o/rel-zizler/3/h2o-3.32.1.2.zip";
        sha256="07kkh1px0naq2g0718y1y0khydivsi80v63kdy1frxls1c5ky3kf";
        }"""
            ),
        },
        # "salso": {
        #     "postPatch": """
        #     substituteInPlace tools/staticlib.R --replace '--release' '--release", "--offline'
        #     echo "patched offline mode"
        #     """,
        # },
    },
    ["rpg", "caviarpd"],
    copy_anyway=True,
)
attrs.inherit(
    "3.14",
    {
        "cuml4r": shebangs,
        "NxtIRFcore": shebangs,
        "paxtoolsr": fake_home,
        "MatchIt": fix_strip,
        "pins": fake_home,
        "terra": {
            "PROJ_LIB": "${pkgs.proj}/share/proj",
            # "configureFlags": ["--with-proj-share=${pkgs.proj}/share/proj"],
        },
        "h2o": {
            "preInstall": """
ls /build
mkdir /build/h2o/inst/java
cp $jarSource/h2o.jar /build/h2o/inst/java
""",
            "jarSource": nix_literal(
                """pkgs.fetchzip{
        url="http://h2o-release.s3.amazonaws.com/h2o/rel-zizler/3/h2o-3.34.0.3.zip";
        sha256="07kkh1px0naq2g0718y1y0khydivsi80v63kdy1frxls1c5ky3kf";
        }"""
            ),
        },
        "R.cache->>": fake_home,
        "string2path": {
            "postPatch": """
            substituteInPlace src/Makevars.in --replace "--release" "--release --offline"
            """,
            "preConfigure": "export NOT_CRAN=true\n",
        },
        "x13binary": {
            "X13BINARY": nix_literal(
                """builtins.fetchurl{
url = "https://github.com/x13org/x13prebuilt/raw/master/v1.1.57/linux/64/x13ashtml";
sha256 = "0lpn41lvj4k38ld1w2v9q99gm4bs35ja2zygrndax12rk2a6qjf4";
}"""
            )
        },
        "salso": {
            "postPatch": """
            substituteInPlace tools/cargo.R --replace "env <- c(env, CARGO_HOME=n(cargo_home))" ""
            """
        },
    },
    ["freetypeharfbuzz", "collapse"],
    copy_anyway=True,
)
attrs.inherit(
    ("3.14", "2021-10-30"),
    {
        "fixest->": fake_home,
    },
)
attrs.inherit(
    ("3.14", "2021-11-05"),
    {
        "cuda.ml": shebangs,
    },
)
attrs.inherit(("3.14", "2021-11-06"), {}, ["BALD", "rGEDI"])
attrs.inherit(
    ("3.14", "2021-11-12"),
    {
        "agtboost": fix_strip,
    },
)
attrs.inherit(("3.14", "2021-11-17"), {}, ["kgrams"])


attrs = attrs.to_dict()

overrideDerivations = Inheritor()
overrideDerivations.inherit(
    "3.10",
    {
        "data.table": nl(
            """old: old // {
                    NIX_CFLAGS_COMPILE = old.NIX_CFLAGS_COMPILE + lib.optionalString stdenv.isDarwin " -fopenmp";
                    }
                """
        ),
        "glpkAPI": nl(  # GLPK in nix is too old?
            """old: old // {
                    NIX_CFLAGS_COMPILE = old.NIX_CFLAGS_COMPILE + "--enable-gmp=no";
                    }"""
        ),
    },
)

overrideDerivations = overrideDerivations.to_dict()

# dates at which we also need to build the r_eco_system
# build from above
extra_snapshots = {}
for adict in (
    excluded_packages,
    broken_packages,
    downgrades,
    comments,
    package_patches,
    additional_r_dependencies,
    native_build_inputs,
    build_inputs,
    skip_check,
    patches,
    attrs,
    overrideDerivations,
):
    if not isinstance(adict, dict):
        raise TypeError(adict)
    for key in adict.keys():
        if isinstance(key, tuple):
            if len(key) != 2:
                raise ValueError("Invalid spec", key)
            bc_version, date = key
            parse_date(date)
            if bc_version not in extra_snapshots:
                extra_snapshots[bc_version] = set()
            extra_snapshots[bc_version].add(date)

extra_snapshots = {k: sorted(v) for (k, v) in extra_snapshots.items()}
