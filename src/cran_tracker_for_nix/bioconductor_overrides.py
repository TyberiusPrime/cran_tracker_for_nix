from .common import parse_date, format_date, nix_literal

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
    """
    if release_info is None:
        raise ValueError("release_info must be passed")
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


def inherit(collector, new_key, new, remove=None, copy_anyway=False, rewriter=None):
    """
    Inherit the values from the last entry iff
        - copy_anway is set
    or
        - last_key == new_key[0] or last_key[0] == new_key[0]
        ie. the bioconductor version matches

    The rewriter get's passed the copied values, not the new ones

    """
    assert isinstance(copy_anyway, bool)
    assert remove is None or isinstance(remove, list)
    assert isinstance(collector, list)
    assert isinstance(new_key, (tuple, str))
    assert isinstance(new, dict)
    if isinstance(remove, str):
        raise TypeError("remove must be a list")

    last = _get_last(collector, new_key, lambda: {}, copy_anyway)
    out = last.copy()
    if rewriter is not None:
        out = rewriter(out)
    # remove first, fill in then.
    if remove:
        remove = set(remove)
        out = {k: v for (k, v) in out.items() if k not in remove}
    out.update(new)
    collector.append((new_key, out))


def inherit_list(collector, new_key, new, remove=None, copy_anyway=False):
    """Same as inherit, but just for lists"""
    assert isinstance(copy_anyway, bool)
    assert remove is None or isinstance(remove, list)
    assert isinstance(collector, list)
    assert isinstance(new_key, (tuple, str))
    assert isinstance(new, list)
    last = _get_last(collector, new_key, lambda: [], copy_anyway)
    out = last[:]
    out = out + new
    if remove:
        remove = set(remove)
        out = [x for x in out if x not in remove]
    collector.append((new_key, out))


def inherit_to_dict(inherited):
    return {x[0]: x[1] for x in inherited}


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
        "github:nixOS/nixpkgs=?rev=6a3f5bcb061e1822f50e299f5616a0731636e4e7",
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
    # todo: is flake correctly setting
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
        """
lib.optionals (!withRecommendedPackages) [
    (fetchpatch {
       name = "fix-tests-without-recommended-packages.patch";
       url = "https://github.com/wch/r-source/commit/7715c67cabe13bb15350cba1a78591bbb76c7bac.patch";
       # this part of the patch reverts something that was committed after R 4.1.0, so ignore it.
       excludes = [ "tests/Pkgs/xDir/pkg/DESCRIPTION" ];
       sha256 = "sha256-iguLndCIuKuCxVCi/4NSu+9RzBx5JyeHx3K6IhpYshQ=";
    })
    (fetchpatch {
      name = "use-codetools-conditionally.patch";
      url = "https://github.com/wch/r-source/commit/7543c28b931db386bb254e58995973493f88e30d.patch";
      sha256 = "sha256-+yHXB5AItFyQjSxfogxk72DrSDGiBh7OiLYFxou6Xlk=";
    })
  ];
  """
    ],
    "4.1.1": bp + ["./r_patches/skip-check-for-aarch64.patch"],
}

include_tz = """preCheck = "export TZ=CET; bin/Rscript -e 'sessionInfo()'";\n"""
additional_r_overrides = {
    "3.3.0": include_tz,  # by 17.09 this is in the nixpkgs R pkg, but not in 17.03 which we use for 3.4.0
    "3.4.0": include_tz,  # by 17.09 this is in the nixpkgs R pkg, but not in 17.03 which we use for 3.4.0
}
flake_overrides = {
    # R version -> path in ./flakes/
    # "3.3.3": "3.3.2",
    "4.0.0": "4.0.0",
}


# packages that we kick out of the index
# per bioconductor release, and sometimes per date.
# the world ain't perfect 🤷
# note that we can kick from specific lists by prefixing with one of
# 'bioc_experiment--'.
# 'bioc_annotation--'.
# 'bioc_software--'. = bioconductor software
# 'cran--'.
# which is necessary when a package is in multiple but we don't want to kick all of them.

excluded_packages = []
inherit(
    excluded_packages,
    "3.0",
    {
        # repository doublettes
        "bioc_experiment--MafDb.ALL.wgs.phase1.release.v3.20101123": "newer in bioconductor-annotation",
        "bioc_experiment--MafDb.ESP6500SI.V2.SSA137.dbSNP138": "newer in bioconductor-annotation",
        "bioc_experiment--phastCons100way.UCSC.hg19": "newer in bioconductor-annotation",
        "cran--GOsummaries": "newer in bioconductor",
        "cran--gdsfmt": "newer in bioconductor",
        "cran--oposSOM": "newer in bioconductor",
        # actual excludes
        # "affy": "requries BiocInstaller",
        "bigGP": "build is broken",
        "bioassayR": "wants RSQLite 1.0.0, which only appeared on 14-10-25",
        "BiocCheck": "requries BiocInstaller",
        "BRugs": "needs OpenBUGS, not in nixpkgs. Or in ubuntu. And the website change log says it hasn't updated since 2014. And the ssl certificate is expired.",
        "clpAPI": "missing clp library",
        "cudaBayesreg": "build is broken, needs nvcc",
        "cummeRbund": "wants RSQLite 1.0.0, which only appeared on 14-10-25",
        "doMPI": "build is broken with mpi trouble",
        "easyRNASeq": "needs LSD>=3.0, which shows up on 2015-01-10",  # bc
        # "gWidgetstcltk": "tcl invalid command name 'font'",
        "HilbertVisGUI": "needs OpenCL, not available in nixpkgs 15.09",
        "HiPLARM": "build is broken, and the package never got any updates and was removed in 2017-07-02",
        "HSMMSingleCell": "needs VGAM > 0.9.5, that shows up on 11-07",  # bc
        "interactiveDisplayBase": "wants to talk to bioconductor.org during installation",
        "jvmr": "broken build. Wants to talk to ddahl.org. Access /home/dahl during build",
        "ltsk": "missing lRlacpack und lRblas?",
        "MSeasyTkGUI": "Needs Tk",
        "MSGFgui": "needs shiny.>=0.11.0 which shows up on 2015-02-11",  # bc
        "ncdfFlow": "no hdf5.dev in this nixpkgs",
        "NCmisc": "requires BiocInstaller",
        "nloptr": "nlopt library is broken in nixpkgs 15.09",
        "npRmpi": "build is broken with mpi trouble",
        "oligoClasses": "requires biocInstaller during installation",
        "OpenCL": "needs OpenCL, not available in nixpkgs 15.09",
        "pbdSLAP": "build is broken with mpi trouble",
        "permGPU": "build is broken, needs nvcc",
        "plethy": "wants RSQLite 1.0.0, which only appeared on 14-10-25",
        "pmclust": "build is broken with mpi trouble",
        "qtpaint": "missing libQtCore.so.4 and was listed as broken in nixpkgs 15.09",
        "QuasR": "requires BiocInstaller",
        "Rcplex": "cplex (c dependency) only shows up later in nixpkgs than 15.09",
        "RcppOctave": "build seems incompatible with octave version in nixpkgs.",
        "rgdal": "not compatible with GDAL2 (which is what's in nixpkgs at this point)",
        "rhdf5": "no hdf5.dev in this nixpkgs",
        "Rmosek": "build is broken according to R/default.nix",
        "ROracle": "OCI libraries not found",
        "rpanel": "build broken, wants DISPLAY?",
        "RQuantLib": "hquantlib ( if that's even the right package) is broken in nixpgks 15.09)",
        "RSAP": "misssing sapnwrfc.h",
        "rsbml": "libsmbl isn't packagd in nixpkg ",
        "SDMTools": "all downstreams fail with  undefined symbol: X",
        "seqplots": "needs shiny.>=0.11.0 which shows up on 2015-02-11",  # bc
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
inherit(
    excluded_packages,
    ("3.0", "2014-10-26"),
    {
        "metaMix": "R install fails with MPI problem",
    },
    # RSQLite 1.0.0 becomes available
    ["bioassayR", "plethy", "cummeRbund", "VariantFiltering"],
)

inherit(
    excluded_packages,
    ("3.0", "2014-10-28"),
    {
        "h2o": "tries to download from s3",
    },
)

inherit(
    excluded_packages,
    ("3.0", "2014-11-07"),
    {},
    ["HSMMSingleCell"],
)

inherit(
    excluded_packages,
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


inherit(
    excluded_packages,
    ("3.1"),
    {
        "cran--saps": "newer in bioconductor",
        "cran--muscle": "newer in bioconductor",
        #  simply missing
        "affy": "requries BiocInstaller",
        "bigGP": "build is broken with mpi trouble",
        "BiocCheck": "requries BiocInstaller",
        "BRugs": "needs OpenBUGS, not in nixpkgs. Or in ubuntu. And the website change log says it hasn't updated since 2014. And the ssl certificate is expired.",
        "ChIPpeakAnno": "requires BiocInstaller",
        "cudaBayesreg": "build is broken, needs nvcc",
        "doMPI": "build is broken with mpi trouble",
        "h2o": "tries to download from s3",
        "HierO": "can't find BWidget",
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
        "oligoClasses": "requires biocInstaller during installation",
        "OpenCL": "needs OpenCL, not available in nixpkgs 15.09",
        "pbdSLAP": "build is broken with mpi trouble",
        "permGPU": "build is broken, needs nvcc",
        "pmclust": "build is broken with mpi trouble",
        "qdap": "build segfaults",
        "qtpaint": "missing libQtCore.so.4 and was listed as broken in nixpkgs 15.09",
        "QuasR": "requires BiocInstaller",
        "Rcplex": "cplex (c dependency) only shows up later in nixpkgs than 15.09",
        "RcppAPT": "needs APT/Debian system",
        "RcppOctave": "build seems incompatible with octave version in nixpkgs.",
        "rgdal": "not compatible with GDAL2 (which is what's in nixpkgs at this point)",
        "rhdf5": "no hdf5.dev in this nixpkgs",
        "Rmosek": "build is broken according to R/default.nix. And changed hash without version change.",
        "ROracle": "OCI libraries not found",
        "rpanel": "can't find BWidget",
        "RQuantLib": "hquantlib ( if that's even the right package) is broken in nixpgks 15.09)",
        "RSAP": "misssing sapnwrfc.h",
        "rsbml": "libsmbl isn't packagd in nixpkg ",
        "Rsymphony": ["pkgconfig", "doxygen", "graphviz", "subversion"],
        "SDMTools": "all downstreams fail with  undefined symbol: X",
        "SOD": "build broken without libOpenCL",
        "spectral.methods": "needs clusterify from Rssa which that package apperantly never had",
        "SSOAP": "(omegahat / github only?)",
        "SVGAnnotation": "github only?",
        "sybilSBML": "configure checks for /usr/include and /usr/local/include - and possibly also needs libsmbl, judging by the name?",
        "XMLRPC": "(omegahat / github only?)",
        "XMLSchema": "(omegahat / github only?)",
        "V8": "mismatch between the nixpkgs version and what R wants",
        "PAA": "requries Rcpp >=0.11.6, which only became available on 2017-05-02",
        "bamboo": "shows up on CRAN at 2017-05-16",
        "seqplots": "DT, required by seqplots shows up on CRAN at 2017-06-09",
        "NetPathMiner": "Needs igraph >= 1.0.0",  # bc
        "BioNet": "Needs igraph >= 1.0.0",
        "assertive.base": "assertive.base showed up on 2015-07-15",
        "DT": "dt shows up on 2015-08-01",
        "clipper": "missing export in igraph. Needs 1.0.0, perhaps?",
        "NGScopy": "required changepoint version shows up 2015-10-01",
        #'WideLM': 'ncvv too old (missing option)',
    },
)
inherit(
    excluded_packages,
    ("3.1", "2015-04-27"),
    {},
)


inherit(
    excluded_packages,
    ("3.1", "2015-05-02"),
    {
        "h5": "no hdf5.dev in this nixpkgs",
    },
    ["PPA"],
)

inherit(excluded_packages, ("3.1", "2015-05-16"), {}, ["bamboo"])
inherit(excluded_packages, ("3.1", "2015-06-09"), {}, ["seqplots"])
# inherit(
#     excluded_packages,
#     ("3.1", "2015-06-30"),
#     {
#         #"stringi": "Wants to download icudt55l.zip",
#     },
#     [],
# )
inherit(
    excluded_packages,
    ("3.1", "2015-07-02"),
    {
        "iptools": "can't find boost::regex",
    },
)
inherit(
    excluded_packages,
    ("3.1", "2015-07-07"),
    {},
    [
        "NetPathMiner",
        "BioNet",
        "clipper",
    ],
)
inherit(
    excluded_packages,
    ("3.1", "2015-07-15"),
    {},
    ["assertive.base"],
)
inherit(excluded_packages, ("3.1", "2015-08-01"), {}, ["DT"])
inherit(
    excluded_packages,
    ("3.1", "2015-10-01"),
    {
        "FIACH": "unknown output-sync type 'RTIFY_SOURCE=2'?",
        "regRSM": "MPI trouble",
        "Rblpapi": "Missing blpapi_session.h?",
    },
    ["NGScopy"],
)

inherit(  # start anew.
    excluded_packages,
    ("3.2"),
    {
        # I expect these to stay broken
        "SSOAP": "(omegahat / github only?)",
        "XMLRPC": "(omegahat / github only?)",
        "XMLSchema": "(omegahat / github only?)",
        "SVGAnnotation": "github only?",
        "h2o": "tries to download from s3",
        "RcppAPT": "needs APT/Debian system",
        "RSAP": "misssing sapnwrfc.h",
        "HierO": "can't find BWidget",
        "HiPLARM": "build is broken, and the package never got any updates and was removed in 2017-07-02",
        "BRugs": "needs OpenBUGS, not in nixpkgs. Or in ubuntu. And the website change log says it hasn't updated since 2014. And the ssl certificate is expired.",
        "interactiveDisplayBase": "wants to talk to bioconductor.org during installation",
        "jvmr": "broken build. Wants to talk to ddahl.org. Access /home/dahl during build",
        # possibly unbreak when we leave 15.09 behind
        "ROracle": "OCI libraries not found",
        "h5": "no hdf5.dev in this nixpkgs",
        "nloptr": "nlopt library is broken in nixpkgs 15.09",
        "RQuantLib": "hquantlib ( if that's even the right package) is broken in nixpgks 15.09)",
        "HilbertVisGUI": "needs OpenCL, not available in nixpkgs 15.09",
        "OpenCL": "needs OpenCL, not available in nixpkgs 15.09",
        "iptools": "can't find boost::regex",
        "cudaBayesreg": "build is broken, needs nvcc",
        "SDMTools": "all downstreams fail with  undefined symbol: X",
        "stringi": "Wants to download icudt55l.zip",
        "rsbml": "libsmbl isn't packagd in nixpkg ",
        "sybilSBML": "configure checks for /usr/include and /usr/local/include - and possibly also needs libsmbl, judging by the name?",
        "affy": "requries BiocInstaller",
        "QuasR": "requires BiocInstaller",
        "Rsymphony": "can't find SYMPHONY in nixpkgs",  # that does come back up eventually, judging from 21.03
        "rhdf5": "no hdf5.dev in this nixpkgs",
        "rpanel": "build broken, wants DISPLAY?",
        "permGPU": "build is broken, needs nvcc",
        "IlluminaHumanMethylation450k.db": "uses 'Defunct' function",
        "OrganismDbi": "needs biocInstaller",
        "oligoClasses": "requires biocInstaller during installation",
        "bigGP": "build is broken",
        "MSeasyTkGUI": "Needs Tk",
        "SOD": "build broken without libOpenCL",
        "Rblpapi": "Missing blpapi_session.h?",
        "doMPI": "build is broken with mpi trouble",
        "regRSM": "MPI trouble",
        "pmclust": "build is broken with mpi trouble",
        "V8": "mismatch between the nixpkgs version and what R wants",
        "Rmosek": "build is broken according to R/default.nix",  # that does come back up eventually, judging from 21.03
        "Rcplex": "cplex (c dependency) only shows up later in nixpkgs than 15.09",
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
inherit(excluded_packages, ("3.2", "2015-12-29"), {}, ["flowCore"])
inherit(
    excluded_packages,
    ("3.2", "2016-01-10"),
    {
        "rjags": "Wrong JAGS version in nixpkgs 15.09",
        "rmumps": "needs libseq, can't find in nixpkgs 15.09",
    },
    ["ggrepel"],
)
inherit(excluded_packages, ("3.2", "2016-02-08"), {}, ["spliceSites"])

inherit(  # start anew.
    excluded_packages,
    ("3.3"),
    {
        "XMLRPC": "(omegahat / github only?)",
        "SVGAnnotation": "github only?",
        "bioc_experiment--IHW": "newer in bioconductor-software",
        "nloptr": "nlopt library is broken in nixpkgs 16.03",
        "ChemmineOB": "openbabel is broken in nixpkgs 16.03",
        "RcppOctave": "octave-package segfaults during build",
    },
)

inherit(  # start anew.
    excluded_packages,
    ("3.4"),
    {
        "XMLRPC": "(omegahat / github only?)",
        "SVGAnnotation": "github only?",
        "cran--PharmacoGx": "newer in bioconductor",
        "cran--statTarget": "newer in bioconductor",
        "cran--synergyfinder": "newer in bioconductor",
        #
        "nloptr": "nlopt library is broken in nixpkgs 17.04",
        "ChemmineOB": "openbabel is broken in nixpkgs 17.04",
    },
)
inherit(  # start anew.
    excluded_packages,
    ("3.5"),  # 2017-04-25
    {
        # --
        "AnnotationHub": "missing BiocInstaller - todo: patch?",
        "BiocCheck": "requries BiocInstaller",  # todo: patch?
        "BRugs": "needs OpenBUGS, not in nixpkgs. Or in ubuntu. And the website change log says it hasn't updated since 2014. And the ssl certificate is expired.",
        "ccmap": "missing BiocInstaller - todo: patch?",
        "chinese.misc": "Wants write access to nix store. Possibly patchable",
        "CountClust": "object 'switch_axis_position' is not exported by 'namespace:cowplot', try newer cowplot after 2017-07-30",
        "cudaBayesreg": "build is broken, needs nvcc",
        "dbplyr": "only shows up on 2017-06-10",
        "DeepBlueR": "attepmts to contact deepblue.mpi-inf.mpg.de",
        "EMCC": "'template with c linkage' error",
        "GenomicFeatures": "needs Rsqlite>=2.0, try after 2017-06-19",
        "h5": "won't find h5c++",
        "HierO": "can't find BWidget",
        "IlluminaHumanMethylation450k.db": 'build fails with "fun is defunct"',
        "interactiveDisplay": "tries to access bioconductor.org",
        "jvmr": "broken build. Wants to talk to ddahl.org. Access /home/dahl during build",
        "mcPAFit": "objects 'GenerateNet', 'GetStatistics', 'PAFit' are not exported by 'namespace:PAFit'",
        "MonetDBLite": "missing libmonetdb5",
        "ncdfFlow": "no hdf5.dev in this nixpkgs, possibly patchable?",
        "nloptr": "nlopt library is broken in nixpkgs 17.03",
        "oligoClasses": "requires biocInstaller during installation",  # todo: pach?
        "plink": "object 'windows' is not exported by 'namespace:grDevices'. Try newer version at 2017-04-26",
        "psygenet2r": "needs biocinstaller",  # todo patch?
        "QUBIC": "compilation failure, was not updated within this BC release",
        "randstr": "queries www.random.org",
        "Rblpapi": "Missing blpaip3",
        "Rcplex": "'This nix expression requires that the cplex installer is already downloaded to your machine. Get it from IBM:'. Antihermetic",
        "RcppAPT": "needs APT/Debian system",
        "RcppOctave": "build seems incompatible with octave version in nixpkgs.",
        "remoter": "error: file '~' does not exist",
        "RKEELjars": "downloads jars from github",
        "rlo": "needs python&numpy",  # todo: decide how we take the python to use
        "Rmosek": "needs 'mosek', unavailable",
        "rmumps": "needs libseq, can't find in nixpkgs 17.03",
        "ROracle": "OCI libraries not found",
        "rpanel": "build broken, wants DISPLAY?",
        "RQuantLib": "hquantlib is a haskell package - don't think that's what's required?",
        "RSAP": "misssing sapnwrfc.h",
        "rsbml": "libsmbl isn't packagd in nixpkg",
        "RSQLServer": "object 'src_translate_env' is not exported by 'namespace:dplyr', try after 2017-06-09 for newer dpylr",
        "Rsymphony": "can't find SYMPHONY in nixpkgs",  # that does come back up eventually, judging from 21.03
        "SDMTools": "all downstreams fail with  undefined symbol: X",
        "SVGAnnotation": "github only?",
        "sybilSBML": "configure checks for /usr/include and /usr/local/include - and possibly also needs libsmbl, judging by the name?",
        "warbleR": "trying to use CRAN without setting a mirror",
        "XMLRPC": "(omegahat / github only?)",
        "HiPLARM": "build is broken, and the package never got any updates and was removed in 2017-07-02",
        "SnakeCharmR": "needs python",  # Todo
        "googleformr": "wants to access the net",
        "odbc": "can't find unixodbc-dev, possibly patchable?",  # todo
        "OpenCL": "needs OpenCL, not available in nixpkgs 17.03",
        "permGPU": "build is broken, needs nvcc",
        "textTinyR": "boost trouble",  # todo
        "InterfaceqPCR": "segfaults on build",
        "limmaGUI": "install needs BiocInstaller",  # todo: patch
        "lpsymphony": "cpp errors",
        "rhdf5": "wrong hdf5.dev version?",
        "gpuR": "OpenCL",
        # "V8": "mismatching
        "clpAPI": "missing clp library",
        "h2o": "tries to download from s3",
        "tesseract": "missing baseapi.h?",
        "pbdBASE": "requires blasc_gridinfo from intel?",
        'mongolite': 'mongolite.so: undefined symbol: BIO_push',
        'devEMF': 'undefined symbol: XftCharExists',
        "qtpaint": "build failure",
    },
)
inherit(
    excluded_packages,
    ("3.5", "2017-04-25"),
    {
        # "INLA": "never on cran",
    },
)
inherit(excluded_packages, ("3.5", "2017-04-26"), {}, ["plink"])
inherit(excluded_packages, ("3.5", "2017-06-09"), {}, ["dbplyr"])  # or is it -10?
inherit(
    excluded_packages, ("3.5", "2017-06-19"), {}, ["GenomicFeatures"]
)  # or is it -10?
inherit(
    excluded_packages, ("3.5", "2017-06-30"), {}, ["mcPAFit"]
)  # new release, maybe...
inherit(
    excluded_packages, ("3.5", "2017-07-30"), {}, ["CountClust"]
)  # new cowplot release


inherit(  # start anew.
    excluded_packages,
    ("3.6"),
    {
        "XMLRPC": "(omegahat / github only?)",
        "bioc_software--JASPAR2018": "same package present in annotation",
        "ROracle": "OCI libraries not found",
        "SVGAnnotation": "github only?",
    },
)
inherit(  # start anew.
    excluded_packages,
    ("3.7"),  # 2018-05-1
    {
        "iontree": "deprecated in 3.6, removed in 3.7, but still in PACKAGES",
        "domainsignatures": "deprecated in 3.6, removed in 3.7, but still in PACKAGES",
        "bioc_software--JASPAR2018": "newer package present in annotation",
        "bioc_software--MetaGxOvarian": "newer package present in experiment",
    },
)
inherit(  # start anew.
    excluded_packages,
    ("3.7", "2018-05-26"),
    {"GenABEL.data": "removed from cran, but still in packages"},
)


inherit(  # start anew.
    excluded_packages,
    ("3.7", "2018-07-16"),
    {"ReporteRsjars": "removed from cran, but still in packages"},
)


inherit(  # start anew. # 2018-10-31
    excluded_packages,
    ("3.8"),
    {
        #
        "cran--mixOmics": "newer in bioconductor",
        # "ReporteRsjars": "removed from cran, but still in packages",
        "ReporteRs": "fgmutils 0.9.4 needs that,though ReporteRs (and ReporteRsjars) is no longer in CRAN",
    },
)
inherit(
    excluded_packages,
    ("3.8", "2018-11-12"),
    {},
    ["ReporteRsjars"],
)

inherit(  # start anew. - 2019-03-05
    excluded_packages,
    ("3.9"),
    {},
)


inherit(  # start anew.
    excluded_packages,
    ("3.10"),  # 2019-10-30
    {
        "bigGP": "undefined symbol: mpi_universe_size?",
        "BRugs": "needs OpenBUGS, not in nixpkgs. Or in ubuntu. And the website change log says it hasn't updated since 2014. And the ssl certificate is expired.",
        "charm": "deprecated / removed, but still in packages",
        "clpAPI": "insists on /usr/include and /usr/local/include",
        "commonsMath": "tries to download jar files",
        "exifr": "Tries to talk to paleolimbot.github.io",
        "freetypeharfbuzz": "Downloads from github",
        "h2o": "tries to download from s3",
        "h5": "won't find h5c++",
        "HierO": "can't find BWidget",
        "kazaam": "mpi trouble",
        "kmcudaR": "build is broken, needs nvcc",
        "multiMiR": "talks to multimr.org",
        "nloptr": "undefined symbol: nlopt_remove_equality_constraints - version mismatch?",
        "pbdSLAP": "mpi trouble",
        "permGPU": "build is broken, needs nvcc",
        "qtbase": "Can't get it to find GL/gl.h",
        "Rblpapi": "Missing blpaip3",
        "Rcplex": "'This nix expression requires that the cplex installer is already downloaded to your machine. Get it from IBM:'. Antihermetic",
        "RcppAPT": "needs APT/Debian system",
        "RcppArmadillo": "undefined symbol: _ZNKSt13random_device13_M_getentropyEv",
        "RcppClassic": "hard coded /usr/bin/strip",
        # "universalmotif": "hard coded /usr/bin/strip",
        "reactable": "only shows up on 2019-11-21",
        "redux": "needs hiredis, not found in nixpkgs",
        "regRSM": "undefined symbol: mpi_universe_size?",
        "RKEELjars": "downloads jars from github",
        "rlo": "needs python&numpy",
        "BiocSklearn": "needs python&sklearn",
        "Rmpi": "undefined symbol: mpi_universe_size?",
        "rmumps": "needs libseq, can't find in nixpkgs 19.09",
        "ROracle": "OCI libraries not found",
        # "rpanel": "build broken, wants DISPLAY?",
        "rphast": "can't find prce_compile / build problems - and disappears on 2020-03-03 anyway",
        "RQuantLib": "hquantlib ( if that's even the right package) is broken in nixpgks 15.09)",
        "rsbml": "libsmbl isn't packagd in nixpkg",
        "Rsymphony": "can't find SYMPHONY in nixpkgs",
        "salso": "downloads from dbdahl.github.io",
        "SDMTools": "all downstreams fail with  undefined symbol: X",
        "SeqKat": "hard coded /usr/bin/strip",
        # "stringi": "Wants to download icudt55l.zip",
        # "stringi": "Wants to download icudt61l.zip",
        "sybilSBML": "configure checks for /usr/include and /usr/local/include - and possibly also needs libsmbl, judging by the name?",
        "TDA": "cpp template issues",
        "trio": "requires logiRec 1.6.1",
        "wrswoR.benchmark": "talks to github during install",
        "randstr": "queries www.random.org",
        "interactiveDisplay": "'trying to use CRAN without setting a mirror'",
        "x12": "'error: argument is of length zero'?",
        "zonator": "ERROR: hard-coded installation path:. Try after 2020-05-18 with 0.6.0",
        "mlm4omics": "won't compile with current stan",
        "Rcwl": "needs cwltool, not available in 20.03",
        "gpuR": "OpenCL missing?",
        "DeepBlueR": "attepmts to contact deepblue.mpi-inf.mpg.de",
        "plyranges": "needs tidyselect >=1.0.0 (available 2020-01-28)",
        "BiocPkgTools": "needs tidyselect >=1.0.0 (available 2020-01-28)",
        "splatter": "needs checkmate 2.0.0 (available 2020-02-07)",
        "apcf": "won't find gcs.csv in GDAL_DATA path even though it's there and pcs.csv is being found",
        "uavRst": "hardcoded installation path",
        "GeneBook": "attempts to contact github",
        "traitdataform": "attempts to contact 'https://raw.githubusercontent.com/EcologicalTraitData/ETS/v0.9/ETS.csv'",
        "googleformr": "attempts to contact docs.google.com",
        "fulltext": "wants to write into home",
        "DuoClustering2018": "uses AnnotationHub / net access on install",  # Todo
        "TabulaMurisData": "uses AnnotationHub / net access on install",  # Todo
        "depmap": "uses AnnotationHub / net access on install",  # Todo
        "bodymapRat": "uses AnnotationHub / net access on install",  # Todo
        "benchmarkfdrData2019": "uses AnnotationHub / net access on install",  # Todo
        "HDCytoData": "uses AnnotationHub / net access on install",  # Todo
        "HMP16SData": "uses AnnotationHub / net access on install",  # Todo
        "RNAmodR": "uses AnnotationHub / net access on install",  # Todo
        "FlowSorted.CordBloodCombined.450k": "uses AnnotationHub / net access on install",  # Todo
        "muscData": "uses AnnotationHub / net access on install",  # Todo
    },
)
inherit(
    excluded_packages, ("3.10", "2019-11-08"), {}, ["trio"]
)  # see above for logiRec
inherit(excluded_packages, ("3.10", "2019-11-21"), {}, ["reactable"])
inherit(
    excluded_packages, ("3.10", "2019-12-30"), {}, ["uavRst"]
)  # update, might start to work
inherit(
    excluded_packages, ("3.10", "2020-01-28"), {}, ["plyranges", "BiocPkgTools"]
)  # see above for tidyselect
inherit(
    excluded_packages, ("3.10", "2020-02-07"), {}, ["splatter"]
)  # see above for checkmate


inherit(
    excluded_packages,
    ("3.10", "2020-03-03"),
    {
        "rphast": "removed from CRAN on 2020-03-03, but dependencies were not removed",
        "h2o": "tries to download from s3",
    },
)


inherit(  # start anew.
    excluded_packages,
    ("3.11"),  # 2020-04-28
    {
        "nem": "deprecated / removed, but still in packages",
        "MTseeker": "deprecated / removed, but still in packages",
        "RIPSeeker": "deprecated / removed, but still in packages",
        "rtfbs": "requeries rphast, which was removed from CRAN on 2020-03-03",
        "qtbase": "Can't get it to find GL/gl.h",
        "zonator": "ERROR: hard-coded installation path:. Try after 2020-05-18 with 0.6.0",
    },
)
inherit(  # start anew.
    excluded_packages,
    ("3.11", "2020-05-14"),
    {
        "parcor": "missing ppls",  # check date
    },
)
inherit(  # start anew.
    excluded_packages,
    ("3.11", "2020-05-18"),
    {},
    ["zonator"],
)


inherit(  # start anew. - 2020-10-28
    excluded_packages,
    ("3.12"),
    {
        "easyRNASeq": "MacOSX only? no source in 3.12",
        "SeuratObject": "released later on 2021-01-16",
        "rTANDEM": "deprecated but still in PACKAGES.gz",
        "prada": "deprecated but still in PACKAGES.gz",
        "Roleswitch": "deprecated but still in PACKAGES.gz",
        "spatstat.core": "released later on 2021-01-23",
        "FunciSNP.data": "deprecated but still in PACKAGES.gz",
        "flowType": "deprecated but still in PACKAGES.gz",
        "DESeq": "deprecated but still in PACKAGES.gz",
        "PGSEA": "deprecated but still in PACKAGES.gz",
        "drawer": "released later on 2021-03-03",
        "spsUtil": "released later on 2021-02-17",
        "spsComps": "released later on 2021-02-26",
        "spatstat.geom": "released later on 2021-01-16",
        "parcor": "missing ppls",
        "qtbase": "Can't get it to find GL/gl.h",
        # "ppls": "removed from CRAN, but groc still suggests it",
    },
)
inherit(
    excluded_packages, ("3.12", "2021-01-16"), {}, ["SeuratObject", "spatstat.geom"]
)
inherit(excluded_packages, ("3.12", "2021-01-17"), {}, ["spsUtil"])
inherit(excluded_packages, ("3.12", "2021-01-23"), {}, ["spatstat.core"])
inherit(excluded_packages, ("3.12", "2021-01-26"), {}, ["spsComps"])
inherit(excluded_packages, ("3.12", "2021-03-03"), {}, ["drawer"])


inherit(  # start anew.
    excluded_packages,
    ("3.13"),
    {
        "cran--RCSL": "newer in bioconductor",
        "cran--interacCircos": "newer in bioconductor",
        "destiny": "no source package / build error according to bioconductor",
        "synapter": "no source package / build error according to bioconductor",
        "metagenomeFeatures": "deprecated, but still in PACKAGES.gz",
        "RDAVIDWebService": "deprecated, but still in PACKAGES.gz",
        "genoset": "deprecated, but still in PACKAGES.gz",
        "bigmemoryExtras": "deprecated, but still in PACKAGES.gz",
        "yulab.utils": "show up on 2021-08-17",
        "ggfun": "show up on ",
        "qtbase": "Can't get it to find GL/gl.h",
    },
)

inherit(excluded_packages, ("3.13", "2021-07-02"), {}, ["ggfun"])
inherit(excluded_packages, ("3.13", "2021-08-17"), {}, ["yulab.utils"])

excluded_packages = inherit_to_dict(excluded_packages)


# for when a new package can't be used because a dependency hasn't
# catched up yet, so we want to use an older version of the new package
# only works for cran packages.
# these are not bioc version specific, since they're usually pairs
# of start downgrade / end downgrade.
downgrades = []
inherit(downgrades, "-", {})
inherit(
    downgrades,
    ("-", "2015-05-28"),
    {"RecordLinkage": "0.4-8"},  # , "Namespace trouble -no table.ff in ffbase",
    [],
)


inherit(
    downgrades, ("-", "2015-06-05"), {}, ["RecordLinkage"]
)  # ffbase release, RecordLinkage should work again

inherit(
    downgrades,
    ("-", "2016-01-10"),
    {"synchronicity": "1.1.4"},
    [],  # boost trouble
)

inherit(
    downgrades, ("-", "2016-02-17"), {}, ["synchronicity"]
)  # synchronicity release, might work again.


downgrades = inherit_to_dict(downgrades)


# ("3.13", "<2=021-07-01"): [
# "ggtree",  # missing ggfun
# ],
package_patches = {
    # this is the big gun, when we need to replace a package *completly*
    # {'version': {'bioc|experiment|annotation': [{'name':..., 'version': ..., 'depends': [...], 'imports': [...], 'needs_compilation': True}]}}
    # "3.0": {
    #     "annotation": [
    #         {
    #             "name": "gahgu133plus2cdf",
    #             "version": "2.2.1",
    #             "depends": [
    #                 "utils",
    #                 "AnnotationDbi",
    #             ],  # annotationdbi was missing
    #             "imports": [],
    #             "linking_to": [],
    #             "needs_compilation": False,
    #         }
    #     ],
    #     "software": [
    #         {
    #             "name": "inSilicoMerging",
    #             "version": "1.10.1",
    #             "depends": [
    #                 "Biobase",
    #                 "inSilicoDb",
    #                 "BiocGenerics",
    #             ],  # inSilicoDb was missing
    #             "imports": [],
    #             "linking_to": [],
    #             "needs_compilation": False,
    #         }
    #     ],
    # }
}

additional_r_dependencies = {
    # for when dependencies are missing.
    # we need to use this already at low level,
    # so the graph is complete,
    # not only on export
    "3.0": {
        "annotation": {"gahgu133plus2cdf": ["AnnotationDbi"]},
        "software": {"inSilicoMerging": ["inSilicoDb"]},
    },
    "3.1": {
        "software": {"inSilicoMerging": ["inSilicoDb"], "ChemmineR": ["gridExtra"]},
    },
    "3.2": {
        "annotation": {"gahgu133plus2cdf": ["AnnotationDbi"]},
        "software": {
            "inSilicoMerging": ["inSilicoDb"],
            # "ChemmineR": ["gridExtra"]
        },
    },
    "3.10": {
        "cran": {"RBesT": ["rstantools"]},
    },
}


native_build_inputs = []  # ie. compile time dependencies
# pkgs. get's added automatically if there's no . in the entry.
inherit(
    native_build_inputs,
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
        "chebpol": ["fftw"],
        "ChemmineOB": ["openbabel", "pkgconfig"],
        "cit": ["gsl"],
        "Crossover": ["which"],
        "devEMF": ["pkgs.xlibs.libXft"],
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
        "pbdMPI": ["openmpi"],
        "pbdNCDF4": ["netcdf"],
        "pbdPROF": ["openmpi"],
        "pbdSLAP": ["openmpi"],
        "PBSmapping": ["which"],
        "PBSmodelling": ["which"],
        "pcaPA": ["gsl"],
        "PICS": ["gsl"],
        "PING": ["gsl"],
        "PKI": ["openssl"],
        "png": ["libpng"],
        "PopGenome": ["zlib"],
        "proj4": ["proj"],
        "qtbase": ["qt4"],
        "qtpaint": ["qt4"],
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
        "RcppGSL": ["gsl"],
        "RcppOctave": ["zlib", "bzip2", "icu", "lzma", "pcre", "octave"],
        "RcppRedis": ["hiredis"],
        "RcppZiggurat": ["gsl"],
        # "ReQON": ["zlib"],
        "rgdal": ["proj", "gdal"],
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
        "spate": ["fftw"],
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
inherit(native_build_inputs, ("3.0", "2014-10-26"), {}, ["vcf2geno"])
inherit(native_build_inputs, ("3.0", "2014-10-31"), {}, ["STARSEQ"])
inherit(
    native_build_inputs,
    ("3.0", "2015-01-11"),
    {
        "curl": ["curl"],
        "openssl": ["openssl"],
        "seqinr": ["zlib"],
        "rbison": ["glpk"],
        "rDEA": ["glpk"],
    },
)
inherit(
    native_build_inputs,
    ("3.0", "2015-03-09"),
    {},
    ["Rniftilib"],
)
inherit(
    native_build_inputs,
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
inherit(
    native_build_inputs,
    ("3.1", "2015-04-21"),
    {
        "xml2": ["libxml2"],
    },
)
inherit(
    native_build_inputs,
    ("3.1", "2015-06-09"),
    {
        "PEIP": ["liblapack", "blas"],
    },
)

inherit(
    native_build_inputs,
    ("3.1", "2015-07-11"),
    {
        "PythonInR": ["python"],
    },
)


inherit(native_build_inputs, ("3.1", "2015-08-31"), {"spatial": ["which"]})  # 7.3.11
inherit(
    native_build_inputs,
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

inherit(
    native_build_inputs,
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
inherit(native_build_inputs, ("3.2", "2015-11-21"), {}, ["CARramps", "rpud", "WideLM"])


inherit(
    native_build_inputs,
    ("3.2", "2016-01-10"),
    {
        "rmumps": ["cmake"],
        "SimInf": ["gsl"],
        "sodium": ["libsodium"],
    },
)
inherit(native_build_inputs, ("3.2", "2016-01-11"), {}, ["ncdf"])

inherit(native_build_inputs, "3.3", {}, [], copy_anyway=True)

inherit(native_build_inputs, "3.4", {}, ["MMDiff", "SJava"], copy_anyway=True)
inherit(
    native_build_inputs,
    "3.5",
    {
        "devEMF": ["pkgs.xlibs.libXft", "x11"],
        "pbdBASE": ["blas"],
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
        "pbdBASE": ["blas", "liblapack"],
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
inherit(native_build_inputs, "3.6", {}, [], copy_anyway=True)
inherit(
    native_build_inputs,
    ("3.6", "2017-11-03"),
    {},
    ["RcppOctave"],
)
inherit(
    native_build_inputs,
    ("3.6", "2018-01-02"),
    {},
    ["rgpui", "rgp"],
)
inherit(
    native_build_inputs,
    ("3.6", "2018-01-23"),
    {},
    ["sprint"],
)
inherit(
    native_build_inputs,
    ("3.6", "2018-03-05"),
    {},
    ["VBmix"],
)


inherit(native_build_inputs, "3.7", {}, [], copy_anyway=True)
inherit(
    native_build_inputs,
    ("3.7", "2018-05-15"),
    {},
    ["RnavGraph"],
)
inherit(
    native_build_inputs,
    ("3.7", "2018-08-05"),
    {},
    ["SOD"],
)


inherit(native_build_inputs, "3.8", {}, ["flowQ"], copy_anyway=True)
inherit(native_build_inputs, ("3.8", "2018-11-05"), {"lattice": ["which"]})  # 0.20-38
inherit(native_build_inputs, ("3.8", "2018-12-25"), {"codetools": ["which"]})  # 0.2-16
inherit(
    native_build_inputs,
    ("3.8", "2019-03-03"),
    {},
    ["libamtrack"],
)
inherit(
    native_build_inputs,
    ("3.8", "2019-03-20"),
    {},
    ["pcaPA"],
)
inherit(
    native_build_inputs,
    "3.9",
    {
        "KernSmooth": ["which"],
        "MASS": ["which"],
        "boot": ["which"],
        "cluster": ["which"],
        "densratio": ["which"],
        "foreign": ["which"],
        "nnet": ["which"],
        "rpart": ["which"],
        "Segmentor3IsBack": ["which"],
        "ARRmData": ["which"],
        "dummy": ["which"],
        "qtbase": ["qt4", "cmake", "(lib.getDev pkgs.libGL)"],
    },
    ["birte"],
    copy_anyway=True,
)


def handle_renames(lookup):
    def fix(input):
        output = {}
        for k, v in input.items():
            output[k] = [lookup.get(x, x) for x in v]
        return output

    return fix


inherit(
    native_build_inputs,
    "3.10",
    {
        "apcf": ["gdal_2", "geos"],
        "BALD": ["jags", "pcre", "lzma", "bzip2", "zlib", "icu"],
        "ijtiff": ["libtiff"],
        "bbl": ["gsl_1"],
        "cairoDevice": ["gtk2", "pkgconfig"],
        # "Cairo": [
        #     "pkgconfig",
        #     "libtiff",
        #     "libjpeg",
        #     "cairo",
        #     "x11",
        #     "fontconfig",
        # ],
        "cld3": ["protobuf"],
        "data.table": ["zlib"],
        "DRIP": ["gsl_1"],
        "fftw": ["pkgconfig", "pkgs.fftw.dev"],
        "fftwtools": ["pkgs.fftw.dev"],
        "fRLR": ["gsl_1"],
        "gaston": ["zlib"],
        "gdalcubes": ["pkgconfig", "gdal", "proj", "curl", "sqlite"],
        "gsl": ["gsl"],  # might need 2?
        # "h5": ["hdf5"],
        "haven": ["zlib"],
        "hdf5r": ["hdf5"],
        "hipread": ["zlib"],
        "hSDM": ["gsl_1"],
        "keyring": ["pkgconfig", "pkgs.openssl", "pkgs.openssl.out"],
        "JMcmprsk": ["gsl_1"],
        "jqr": ["jq"],
        "KFKSDS": ["pkgconfig", "gsl_1"],
        "kmcudaR": ["cudatoolkit"],
        "KSgeneral": ["pkgconfig", "fftw"],
        "LCMCR": ["gsl_1"],
        "Libra": ["gsl_1"],
        "mwaved": ["pkgconfig", "fftw"],
        "odbc": ["libiodbc"],
        "opencv": ["opencv3"],
        "openssl": ["pkgs.openssl", "pkgs.openssl.out"],
        "poisbinom": ["fftw"],
        "qpdf": ["libjpeg"],
        "ragg": ["freetype", "pkgconfig", "libpng", "libtiff"],
        "Rbowtie": ["zlib"],
        "Rbowtie2": ["zlib"],
        "RcppCWB": ["pcre", "glib", "pkgconfig", "ncurses"],
        "RcppMeCab": ["mecab"],
        "RmecabKo": ["mecab"],
        "rtmpt": ["gsl_1"],
        "RCurl": ["pkgconfig", "curl"],
        "RGtk2": ["pkgconfig", "pkgs.gtk2.dev"],
        "Rhdf5lib": ["zlib"],
        "RMariaDB": ["zlib", "pkgs.mysql.connector-c", "openssl"],
        "Rmpi": ["openmpi"],
        "RMySQL": ["zlib", "pkgs.mysql.connector-c", "openssl"],
        "RODBC": ["libiodbc"],
        "RPostgres": ["pkgconfig", "postgresql"],
        "rPython": ["which", "python"],
        "rrd": ["pkgconfig", "rrdtool"],
        "rscala": ["scala"],
        "rtk": ["zlib"],
        "scModels": ["mpfr"],
        "ssh": ["libssh"],
        "spate": ["pkgconfig", "fftw"],
        "specklestar": ["fftw"],
        "systemfonts": ["fontconfig"],
        "udunits2": ["udunits", "expat"],
        "ulid": ["zlib"],
        "units": ["udunits"],
        "unrtf": ["pcre", "lzma", "bzip2", "zlib", "icu"],
        "vapour": ["gdal"],
        "websocket": ["openssl"],
        "writexl": ["zlib"],
        "bioacoustics": ["cmake", "fftw", "soxr"],
        "infercnv": ["python"],
        "rgl": ["libGLU", "mesa", "x11"],
        # "Rcwl": ["cwltool"],
        "netboost": ["perl"],
        "Rsampletrees": ["gsl_1"],
        "SICtools": ["ncurses"],
        "universalmotif": ["binutils"],
        "landsepi": ["gsl_1"],
        "ROpenCVLite": ["cmake"],
        "gert": ["libgit2"],
    },
    # "affyio": ["zlib"],
    # # "BayesSAE": ["gsl_1"],
    # "coga": ["gsl_1"],
    # # "coga": ["gsl_1"],
    # "devEMF": ["zlib", "pkgs.xlibs.libXft.dev", "x11"],
    # "diversitree": ["gsl_1", "fftw"],
    # # does this help?
    # "git2r": [ "pkgs.zlib.dev", "pkgs.openssl.dev", "pkgs.libssh2.dev", "libgit2", "pkgconfig", ],
    # # "GLAD": ["gsl_1"],
    # "gmp": ["pkgs.gmp.dev"],
    # # "HiCseq": ["gsl_1"],
    # # "hSDM": ["gsl_1"],
    # "KSgeneral": ["gsl_1", "pkgconfig"],
    # "PKI": ["pkgs.openssl.dev"],
    # "PopGenome": ["zlib"],
    # "R2SWF": ["pkgconfig", "zlib", "libpng", "freetype"],
    # # "Rcplex": ["cplex"],
    # # "RcppZiggurat": ["gsl_1"],
    # "rgdal": ["pkgs.proj.dev", "gdal"],
    # "Rglpk": ["glpk"],
    # "RKHSMetaMod": ["gsl_1"],
    # # "Rlibeemd": ["gsl_1"],
    # # "SemiCompRisks": ["gsl_1"],
    # "seqinr": ["zlib"],
    # "seqminer": ["zlib"],
    # "seqTools": ["zlib"],
    # "showtext": ["pkgconfig", "zlib", "libpng", "freetype", "icu"],
    # # "simplexreg": ["gsl_1"],
    # "snpStats": ["zlib"],
    # "spate": ["fftw"],
    # # "stsm": ["gsl_1"],
    # "sysfonts": ["pkgconfig", "zlib", "libpng", "freetype"],
    # "TAQMNGR": ["pkgs.zlib.dev"],
    # "ulid": ["zlib"],
    # "unrtf": ["bzip2", "zlib", "lzma", " pcre"],
    # "XBRL": ["zlib", "pkgs.libxml2.dev"],
    # "xml2": nl( "[pkgs.libxml2.dev] ++ lib.optionals stdenv.isDarwin [ pkgs.perl ]"),
    # "XML": ["libtool", "pkgs.libxml2.dev", "xmlsec", "libxslt"],
    # "XML": ["libtool", "pkgs.libxml2.dev", "xmlsec", "libxslt"],
    # "XVector": ["zlib"],
    # },
    ["rMAT", "rphast"],
    copy_anyway=True,
    rewriter=handle_renames(
        {
            "gsl": "gsl_1",
            "openssl": "pkgs.openssl.dev",
            "libtiff": "pkgs.libtiff.dev",
        }
    ),
)
inherit(
    native_build_inputs,
    "3.11",
    {
        "RMySQL": ["zlib", "libmysqlclient"],
    },
    [
        "rpg",
        "rPython",
        "rTANDEM",
        "rtfbs",
        "rtiff",
        "dbConnect",
        "TKF",
        "PythonInR",
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
inherit(
    native_build_inputs,
    ("3.11", "2020-09-09"),  # wrong date, TODO
    {},
    [
        "outbreaker",
        "qtbase",
        "qtpaint",
    ],
)

inherit(native_build_inputs, "3.12", {}, ["MotIV", "pbdNCDF4"], copy_anyway=True)
inherit(
    native_build_inputs,
    "3.13",
    {},
    [
        "rggobi",
        "rMAT",
    ],
    copy_anyway=True,
)

native_build_inputs = inherit_to_dict(native_build_inputs)

build_inputs = []  # run time dependencies
# note that in here, it's still 'r packages names', so 'nat.blast', not 'nat_blast'
inherit(
    build_inputs,
    "3.0",
    {
        # sort -t '=' -k 2
        "adimpro": ["which", "pkgs.xorg.xdpyinfo"],
        "cairoDevice": ["pkgconfig"],
        "Cairo": ["pkgconfig"],
        "CARramps": ["which", "cudatoolkit"],
        "chebpol": ["pkgconfig"],
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
        "qtbase": ["cmake", "perl"],
        "qtpaint": ["cmake"],
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
inherit(
    build_inputs,
    "3.1",
    {
        "gridGraphics": ["which"],
    },
    [],
    copy_anyway=True,
)
inherit(
    build_inputs,
    ("3.1", "2015-07-11"),
    {
        "PythonInR": ["python"],
    },
)

inherit(build_inputs, "3.2", {}, [], copy_anyway=True)
inherit(build_inputs, ("3.2", "2015-11-21"), {}, ["CARramps", "rpud", "WideLM"])
inherit(build_inputs, "3.3", {}, [], copy_anyway=True)
inherit(
    build_inputs,
    "3.4",
    {
        "tikzDevice": ["which", "pkgs.texlive.combined.scheme-medium"],
    },
    [],
    copy_anyway=True,
)
inherit(build_inputs, ("3.4", "2017-03-11"), {}, ["ecoretriever"])

inherit(build_inputs, "3.5", {"gridGraphics": ["imagemagick"]}, [], copy_anyway=True)

inherit(build_inputs, "3.6", {}, [], copy_anyway=True)
inherit(
    build_inputs,
    ("3.6", "2017-12-19"),
    {},
    [
        "gmatrix",
        "gputools",
    ],
)

inherit(
    build_inputs,
    ("3.6", "2018-02-01"),
    {},
    ["qtutils"],
)

inherit(
    build_inputs,
    ("3.6", "2018-03-05"),
    {},
    ["VBmix"],
)


inherit(build_inputs, "3.7", {}, [], copy_anyway=True)
inherit(build_inputs, "3.8", {}, ["flowQ"], copy_anyway=True)
inherit(build_inputs, "3.9", {}, [], copy_anyway=True)
inherit(
    build_inputs,
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
inherit(
    build_inputs,
    "3.11",
    {},
    [
        "geoCount",
        "rPython",
        "PET",
    ],
    copy_anyway=True,
)
inherit(
    build_inputs, ("3.11", "2020-09-09"), {}, ["qtbase", "qtpaint"]  # Todo: fix date
)

inherit(build_inputs, "3.12", {}, [], copy_anyway=True)
inherit(build_inputs, "3.13", {}, [], copy_anyway=True)


build_inputs = inherit_to_dict(build_inputs)


skip_check = []
# in R names please, not the safe_for_nix names
inherit_list(
    skip_check,
    "3.0",
    [
        "Rmpi",  # tries to run MPI processes
        "gmatrix",  # requires CUDA runtime
        "sprint",  # tries to run MPI processes
        "pbdMPI",  # tries to run MPI processes
    ],
)
inherit_list(
    skip_check,
    ("3.0", "2014-10-26"),
    [
        "metaMix",
        "bigGP",
    ],
)  # tries to run MPI processes
inherit_list(skip_check, "3.1", ["pbdMPI"], [], copy_anyway=True)
inherit_list(skip_check, "3.2", ["pbdSLAP"], [], copy_anyway=True)
inherit_list(skip_check, "3.3", [], [], copy_anyway=True)
inherit_list(skip_check, "3.4", [], [], copy_anyway=True)
inherit_list(skip_check, "3.5", [], [], copy_anyway=True)
inherit_list(skip_check, "3.6", [], [], copy_anyway=True)
inherit_list(skip_check, "3.7", [], [], copy_anyway=True)
inherit_list(skip_check, "3.8", [], [], copy_anyway=True)
inherit_list(skip_check, "3.9", [], [], copy_anyway=True)
inherit_list(
    skip_check,
    "3.10",
    [
        "RNAmodR.Data",
    ],
    ["gmatrix", "sprint"],
    copy_anyway=True,
)  # MPI
inherit_list(skip_check, "3.11", [], [], copy_anyway=True)
inherit_list(skip_check, "3.12", [], [], copy_anyway=True)
inherit_list(skip_check, "3.13", [], [], copy_anyway=True)


skip_check = inherit_to_dict(skip_check)
# inherit_list( skip_check,"3.2", [], [], copy_anyway=True)


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
    ]
)

patches = []
inherit(
    patches,
    "3.0",
    {
        "affy": [nl("./../patches/affy_1.44.no_bioc_installer.patch")],
        "gcrma": [nl("./../patches/gcrma_2.38.no_bioc_installer.patch")],
        "webbioc": [nl("./../patches/webbioc.1.38.0.no_bioc_installer.patch")],
        "affylmGUI": [nl("./../patches/affylmGUI_1.40.2.no_bioc_installer.patch")],
        "BayesBridge": [nl("./../patches/BayesBridge.patch")],
        "BayesLogit": [nl("./../patches/BayesLogit.patch")],
        "BayesXsrc": [nl("./../patches/BayesXsrc.patch")],
        "CARramps": [nl("./../patches/CARramps.patch")],
        "EMCluster": [nl("./../patches/EMCluster.patch")],
        "gmatrix": [nl("./../patches/gmatrix.patch")],
        "gputools": [nl("./../patches/gputools.patch")],
        # "iFes": [nl("./../patches/iFes.patch")],
        "qtbase": [nl("./../patches/qtbase.patch")],
        "RAppArmor": [nl("./../patches/RAppArmor.patch")],
        "rpud": [nl("./../patches/rpud.patch")],
        "Rserve": [nl("./../patches/Rserve.patch")],
        "spMC": [nl("./../patches/spMC.patch")],
        "WideLM": [nl("./../patches/WideLM.patch")],
    },
)

inherit(
    patches,
    ("3.0", "2015-01-11"),
    {
        "RMySQL": [nl("./../patches/RMySQL.patch")],
    },
)


inherit(
    patches,
    "3.1",
    {
        "qtbase": [nl("./../patches/qtbase.patch")],
        "RMySQL": [nl("./../patches/RMySQL.patch")],
        "BayesXsrc": [nl("./../patches/BayesXsrc_2.1-2.patch")],
    },
    copy_anyway=True,
)
inherit(
    patches,
    ("3.1", "2015-05-29"),
    {
        "qtbase": [nl("./../patches/qtbase_1.0.9.patch")],
    },  # bc 3.1
)
inherit(patches, ("3.1", "2015-10-01"), {}, ["RMySQL"])

inherit(
    patches,
    "3.2",
    {
        "qtbase": [nl("./../patches/qtbase_1.0.9.patch")],
    },
    copy_anyway=True,
)
inherit(patches, "3.3", {}, ["CARramps", "rpud", "WideLM"], copy_anyway=True)
inherit(patches, "3.4", {}, copy_anyway=True)
inherit(
    patches,
    "3.5",
    {
        "redland": [nl("./../patches/redland.patch")],
        "mongolite": [nl("./../patches/mongolite.patch")],
        "affylmGUI": [nl("./../patches/affylmGUI_1.50.0.no_bioc_installer.patch")],
        "qtbase": [nl("./../patches/qtbase_1.0.14.patch")],
        "tesseract": [nl("./../patches/tesseract_1.4.patch")],
    },
    copy_anyway=True,
)
inherit(patches, "3.6", {}, copy_anyway=True)
inherit(patches, "3.7", {}, copy_anyway=True)
inherit(patches, "3.8", {}, copy_anyway=True)
inherit(patches, "3.9", {}, copy_anyway=True)
inherit(
    patches,
    "3.10",
    {
        "tesseract": [nl("./../patches/tesseract.patch")],
        "qtbase": [nl("./../patches/qtbase_1.0.14.patch")],
        "Rhdf5lib": [nl("./../patches/Rhdf5lib.patch")],
    },
    copy_anyway=True,
)
inherit(
    patches,
    "3.11",
    {},
    copy_anyway=True,
)
inherit(patches, "3.12", {}, copy_anyway=True)
inherit(patches, "3.13", {}, copy_anyway=True)
# inherit(
# patches,
# ("3.1", "2015-10-01"),
# {},
# [],
# )

patches = inherit_to_dict(patches)

patches_by_package_version = {}

attrs = []
shebangs = {"postPatch": "patchShebangs configure"}

inherit(
    attrs,
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
                "--with-nlopt-cflags=-I${pkgs.nlopt}/include"
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
        "Rmpi": {"configureFlags": ["--with-Rmpi-type=OPENMPI"]},
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
    },
)
inherit(
    attrs,
    ("3.0", "2014-10-22"),
    {
        "openssl": {
            "OPENSSL_INCLUDES": "${pkgs.openssl}/include",
            "LD_LIBRARY_PATH": "${pkgs.openssl.out}/lib;",
        },
    },
)
inherit(
    attrs,
    ("3.0", "2014-11-21"),
    {
        "curl": {"preConfigure": "export CURL_INCLUDES=${pkgs.curl}/include"},
    },
)
inherit(
    attrs,
    ("3.0", "2014-12-09"),
    {
        "V8": {
            "preConfigure": "export V8_INCLUDES=${pkgs.v8}/include",
        },
    },
)


inherit(attrs, "3.1", {}, copy_anyway=True)

inherit(
    attrs,
    ("3.1", "2015-04-21"),
    {
        "xml2": {
            "preConfigure": "export LIBXML_INCDIR=${pkgs.libxml2}/include/libxml2"
        },
    },
)


inherit(
    attrs,
    ("3.1", "2015-05-28"),
    {"OpenMx": shebangs},
)

inherit(
    attrs,
    ("3.1", "2015-10-01"),
    {
        "curl": shebangs,
        "Rblpapi": shebangs,
        "xml2": shebangs,
        "RMySQL": shebangs,  # dict_add(shebangs, {"MYSQL_DIR": "${pkgs.mysql.connector-c}"}), # wrong todo
    },
)

inherit(
    attrs,
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
inherit(
    attrs,
    ("3.2", "2016-01-10"),
    {
        "gdtools": shebangs,
    },
    ["CARramps", "rpud", "WideLM"],
)
inherit(attrs, "3.3", {}, copy_anyway=True)
inherit(
    attrs,
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
inherit(
    attrs,
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
      "qtpaint": {
            "NIX_LDFLAGS": "-lstd",
        },

        "Cairo": {
            "NIX_LDFLAGS": "-lfontconfig",
        },
        "gdtools": dict_add({
            "NIX_LDFLAGS": "-lfontconfig -lfreetype",
        }, shebangs),
        "V8": {
            "postPatch": 'substituteInPlace configure --replace " -lv8_libplatform" ""',
            "preConfigure": """
        export INCLUDE_DIR=${pkgs.v8_3_14}/include
        export LIB_DIR=${pkgs.v8_3_14}/lib
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
inherit(attrs, "3.6", {}, copy_anyway=True)
inherit(attrs, "3.7", {}, copy_anyway=True)
inherit(attrs, "3.8", {}, copy_anyway=True)
inherit(attrs, "3.9", {}, copy_anyway=True)
inherit(
    attrs,
    "3.10",
    {
        "arrow": shebangs,
        "av": shebangs,
        "BALD": {
            "JAGS_INCLUDE": "${pkgs.jags}/include/JAGS",
            "JAGS_LIB": "${pkgs.jags}/lib",
        },
        "cld3": shebangs,
        "DeLorean": shebangs,
        "freetypeharfbuzz": shebangs,
        "gifski": shebangs,
        "gert": shebangs,
        "ijtiff": shebangs,
        "keyring": shebangs,
        "jqr": shebangs,
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
        "pdftools": shebangs,
        "ps": shebangs,
        "RcppCWB": shebangs,
        "RcppGetconf": shebangs,
        "RcppParallel": shebangs,
        "rDEA": shebangs,  # experimental
        "redux": shebangs,
        "Rglpk": shebangs,  # experimental
        "RMariaDB": shebangs,
        "ROpenCVLite": shebangs,
        "rpg": shebangs,
        "RPostgres": shebangs,
        "rrd": shebangs,
        "rzmq": shebangs,
        "strex": shebangs,
        # "sysfonts": {"strictDeps": False},
        "systemfonts": shebangs,
        "tesseract": shebangs,
        "universalmotif": {
            "postPatch": 'substituteInPlace src/Makevars --replace "/usr/bin/strip" "strip"',
        },
        "websocket": {
            "PKGCONFIG_CFLAGS": "-I${pkgs.openssl.dev}/include",
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
    },
    ["iFes", "SJava", "Mposterior", "gputools", "gmatrix"],
    copy_anyway=True,
)
inherit(attrs, "3.11", {}, ["glpkAPI"], copy_anyway=True)
inherit(attrs, "3.12", {}, copy_anyway=True)
inherit(attrs, "3.13", {}, copy_anyway=True)
attrs = inherit_to_dict(attrs)

overrideDerivations = []
inherit(
    overrideDerivations,
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

overrideDerivations = inherit_to_dict(overrideDerivations)

# dates at which we also need to build the r_eco_system
# build from above
extra_snapshots = {}
for adict in (
    excluded_packages,
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
