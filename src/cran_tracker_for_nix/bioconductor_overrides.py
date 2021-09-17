from .common import parse_date


def match_override_keys(
    input_dict, version, date, debug=False, none_ok=False, default=dict
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
    key = f"{date:%Y-%m-%d}"
    if debug:
        print("looking for", version, key)
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


def inherit(collector, new_key, new, remove=None, copy_anyway=False):
    """
    Inherit the values from the last entry iff
        - copy_anway is set
    or
        - last_key == new_key[0] or last_key[0] == new_key[0]
        ie. the bioconductor version matches

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
    out.update(new)
    if remove:
        remove = set(remove)
        out = {k: v for (k, v) in out.items() if k not in remove}
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
        out = [x for x in out if not x in remove]
    collector.append((new_key, out))


def inherit_to_dict(inherited):
    return {x[0]: x[1] for x in inherited}


# all of these follow the following rules for their keys
comments = {
    "3.0": """Nixpkgs: 15.09 (Uses https://github.com/TyberiusPrime/nixpkgs instead of nixOS/nixpgs. Font sha256s needed patching).""",
    "3.1": """Nixpkgs: 15.09 (Uses https://github.com/TyberiusPrime/nixpkgs instead of nixOS/nixpgs. Font sha256s needed patching).""",
}

# what flake -source do we use
flake_info = []
inherit(
    flake_info,
    "3.0",
    {
        # that's 15.09
        "nixpkgs.url": "github:TyberiusPrime/nixpkgs?rev=f0d6591d9c219254ff2ecd2aa4e5d22459b8cd1c",
        "r_version": "3.1.3",
        "r_tar_gz_sha256": "04kk6wd55bi0f0qsp98ckjxh95q2990vkgq4j83kiajvjciq7s87",
    },
)
inherit(
    flake_info,
    "3.1",
    {
        "nixpkgs.url": "github:TyberiusPrime/nixpkgs?rev=f0d6591d9c219254ff2ecd2aa4e5d22459b8cd1c",
        "r_version": "3.2.1",
        "r_tar_gz_sha256": "10n9yhs55v1nnmdgsrgfncw29vq3ly70n8gvy1f4lq7l0hzvr7fm",
    },
)
inherit(
    flake_info,
    ("3.1", "2015-10-01"),
    {
        "nixpkgs.url": "github:TyberiusPrime/nixpkgs?rev=f0d6591d9c219254ff2ecd2aa4e5d22459b8cd1c",
        "r_version": "3.2.2",
        "r_tar_gz_sha256": "07a6s865bjnh7w0fqsrkv1pva76w99v86w0w787qpdil87km54cw",
        "patches": ["./r_patches/fix-tests-without-recommended-packages.patch"],
    },
)
inherit(
    flake_info,
    "3.2",
    {  # still 15.09 - we're in october 2015 now.
        "nixpkgs.url": "github:TyberiusPrime/nixpkgs?rev=f0d6591d9c219254ff2ecd2aa4e5d22459b8cd1c",
        "r_version": "3.2.2",
        "r_tar_gz_sha256": "07a6s865bjnh7w0fqsrkv1pva76w99v86w0w787qpdil87km54cw",
        "patches": ["./r_patches/fix-tests-without-recommended-packages.patch"],
    },
)
inherit(
    flake_info,
    "3.3",
    {  # released 2016-05-04 - let's try 16.03 then.
        "nixpkgs.url": "github:nixOS/nixpkgs?rev=d231868990f8b2d471648d76f07e747f396b9421",
        "r_version": "3.3.0",
        # "r_tar_gz_sha256": "10n9yhs55v1nnmdgsrgfncw29vq3ly70n8gvy1f4lq7l0hzvr7fm",
    },
)
inherit(
    flake_info,
    "3.4",
    {  # released 2016-10-18 - let's try 16.09 then.
        "nixpkgs.url": "github:nixOS/nixpkgs?rev=f22817d8d2bc17d2bcdb8ac4308a4bce6f5d1d2b",
        "r_version": "3.3.2",  # 3.3.2 came out 2016-10-31. We're still going to useu it I suppose
        # "r_tar_gz_sha256": "10n9yhs55v1nnmdgsrgfncw29vq3ly70n8gvy1f4lq7l0hzvr7fm",
    },
)
flake_info = inherit_to_dict(flake_info)


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
        "bioc_experiment--MafDb.ALL.wgs.phase1.release.v3.20101123": "newer in bioconductor-annotation",
        "bioc_experiment--MafDb.ESP6500SI.V2.SSA137.dbSNP138": "newer in bioconductor-annotation",
        "bioc_experiment--phastCons100way.UCSC.hg19": "newer in bioconductor-annotation",
        "cran--GOsummaries": "newer in bioconductor",
        "cran--gdsfmt": "newer in bioconductor",
        "cran--oposSOM": "newer in bioconductor",
        # level 0
        "SSOAP": "(omegahat / github only?)",
        # "RDCOMClient": "(omegahat / github only?)",
        "XMLRPC": "(omegahat / github only?)",
        "XMLSchema": "(omegahat / github only?)",
        "SVGAnnotation": "github only?",
        "qtpaint": "missing libQtCore.so.4 and was listed as broken in nixpkgs 15.09",
        "nloptr": "nlopt library is broken in nixpkgs 15.09",
        "HiPLARM": "build is broken, and the package never got any updates and was removed in 2017-07-02",
        "Rmosek": "build is broken according to R/default.nix",
        "bigGP": "build is broken",
        "SOD": "build broken without libOpenCL",
        "BRugs": "needs OpenBUGS, not in nixpkgs. Or in ubuntu. And the website change log says it hasn't updated since 2014. And the ssl certificate is expired.",
        "doMPI": "build is broken with mpi trouble",
        "pmclust": "build is broken with mpi trouble",
        "pbdSLAP": "build is broken with mpi trouble",
        "npRmpi": "build is broken with mpi trouble",
        "cudaBayesreg": "build is broken, needs nvcc",
        "permGPU": "build is broken, needs nvcc",
        "Rcplex": "cplex (c dependency) only shows up later in nixpkgs than 15.09",
        "RSAP": "misssing sapnwrfc.h",
        "jvmr": "broken build. Wants to talk to ddahl.org. Access /home/dahl during build",
        "rpanel": "build broken, wants DISPLAY?",
        "rgdal": "not compatible with GDAL2 (which is what's in nixpkgs at this point)",
        "rsbml": "libsmbl isn't packagd in nixpkg ",
        "sybilSBML": "configure checks for /usr/include and /usr/local/include - and possibly also needs libsmbl, judging by the name?",
        "interactiveDisplayBase": "wants to talk to bioconductor.org during installation",
        "RcppOctave": "build seems incompatible with octave version in nixpkgs.",
        "SDMTools": "all downstreams fail with  undefined symbol: X",
        "oligoClasses": "requires biocInstaller during installation",
        "UniProt.ws": "wants to talk to uniprot.org",
        "BiocCheck": "requries BiocInstaller",
        "affy": "requries BiocInstaller",
        "MSeasyTkGUI": "Needs Tk",
        "ncdfFlow": "no hdf5.dev in this nixpkgs",
        "rhdf5": "no hdf5.dev in this nixpkgs",
        "ltsk": "missing lRlacpack und lRblas?",
        "clpAPI": "insists on /usr/include and /usr/local/include",
        "ROracle": "OCI libraries not found",
        "NCmisc": "requires BiocInstaller",
        "QuasR": "requires BiocInstaller",
        "trackViewer": "tcl issue",
        "RQuantLib": "hquantlib ( if that's even the right package) is broken in nixpgks 15.09)",
        "HilbertVisGUI": "needs OpenCL, not available in nixpkgs 15.09",
        "OpenCL": "needs OpenCL, not available in nixpkgs 15.09",
        # "gWidgetstcltk": "tcl invalid command name 'font'",
        "easyRNASeq": "needs LSD>=3.0, which shows up on 2015-01-10",
        "seqplots": "needs shiny.>=0.11.0 which shows up on 2015-02-11",
        "MSGFgui": "needs shiny.>=0.11.0 which shows up on 2015-02-11",
        "HSMMSingleCell": "needs VGAM > 0.9.5, that shows up on 11-07",
    },
)
inherit(
    excluded_packages,
    ("3.0", "2014-10-26"),
    {
        "bioassayR": "wants RSQLite 1.0.0, which only appeared on 14-10-25",
        "plethy": "wants RSQLite 1.0.0, which only appeared on 14-10-25",
        "cummeRbund": "wants RSQLite 1.0.0, which only appeared on 14-10-25",
        "VariantFiltering": "wants RSQLite 1.0.0, which only appeared on 14-10-25",
        "metaMix": "R install fails with MPI problem",
    },
)

inherit(
    excluded_packages,
    ("3.0", "2014-10-28"),
    {
        "h2o": "tries to download form s3",
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
        "h2o": "tries to download form s3",
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
        "h5": "no hdf5.dev in this nixpkgs",
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
        "NetPathMiner": "Needs igraph >= 1.0.0",
        "BioNet": "Needs igraph >= 1.0.0",
        "assertive.base": "assertive.base showed up on 2015-07-15",
        "DT": "dt shows up on 2015-08-01",
        "clipper": "missing export in igraph. Needs 1.0.0, perhaps?",
        "NGScopy": "required changepoint version shows up",
    },
)

inherit(
    excluded_packages,
    ("3.1", "2015-05-02"),
    {},
    # {"OpenMx": "configure not found?",},
    ["PPA"],
)

inherit(excluded_packages, ("3.1", "2015-05-16"), {}, ["bamboo"])
inherit(excluded_packages, ("3.1", "2015-06-09"), {}, ["seqplots"])
inherit(
    excluded_packages,
    ("3.1", "2015-06-30"),
    {
        "stringi": "Wants to download icudt55l.zip",
    },
    [],
)
inherit(
    excluded_packages,
    ("3.1", "2015-07-02"),
    {"iptools": "can't find boost::regex"},
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
    {
        # "iptools": "missing boost::regex which I couldn't find",
    },
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
        "SSOAP": "(omegahat / github only?)",
        # "RDCOMClient": "(omegahat / github only?)",
        "XMLRPC": "(omegahat / github only?)",
        "XMLSchema": "(omegahat / github only?)",
        "SVGAnnotation": "github only?",
        "ggrepel": "was added only later",
    },
)
inherit(excluded_packages, ("3.2", "2016-01-10"), {}, ["ggrepel"])

# inherit
#
inherit(
    excluded_packages,
    ("3.7"),
    {
        "iontree": "deprecated in 3.6, removed in 3.7, but still in PACKAGES",
        "domainsignatures": "deprecated in 3.6, removed in 3.7, but still in PACKAGES",
    },
)
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
}


native_build_inputs = []  # ie. compile time dependencies
# pkgs. get's added automatically if there's no . in the entry.
inherit(
    native_build_inputs,
    "3.0",
    {
        "abn": ["gsl"],
        "adimpro": ["imagemagick"],
        "affyio": ["zlib"],
        "ArrayExpressHTS": ["which"],
        "audio": ["portaudio"],
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
        # "HilbertVisGUI": ["pkgconfig", "opencl-headers"],
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
        "RQuantLib": ["hquantlib"],
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
        "stsm": ["gsl"],
        "survSNP": ["gsl"],
        "sysfonts": ["zlib", "libpng", "freetype"],
        "TAQMNGR": ["zlib"],
        "tiff": ["libtiff"],
        "tkrplot": ["pkgs.xlibs.libX11"],
        "topicmodels": ["gsl"],
        "udunits2": ["udunits", "expat"],
        "VBLPCM": ["gsl"],
        "VBmix": ["gsl", "fftw", "qt4"],
        "vcf2geno": ["zlib"],
        # "WhopGenome": ["zlib"],
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
        "xml2": ["libxml2"],
        "V8": ["v8"],
        # "iptools": ["boost"],
        "git2r": ["zlib", "openssl"],
        # "OpenMx": ["autoreconfHook"],
    },
    ["Rniftilib", "npRmpi"],
    copy_anyway=True,
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
        # "PEIP": ["liblapack", "blas"],
    },
    [],
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
build_inputs = inherit_to_dict(build_inputs)


skip_check = []
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
# inherit_list(skip_check, ("3.1", "2015-10-01"), ["regRSM"], [])
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
        "Geneland",
        "RcmdrPlugin.ROC",
        "spatsurv",
        "ProbForecastGOP",
        "GeoGenetix",
    ]
)

patches = []
inherit(
    patches,
    "3.0",
    {
        "qtbase": ["./../patches/qtbase.patch"],
    },
)

inherit(
    patches,
    ("3.0", "2015-01-11"),
    {
        "RMySQL": ["./../patches/RMySQL.patch"],
    },
)


inherit(
    patches,
    "3.1",
    {
        "qtbase": ["./../patches/qtbase.patch"],
        "RMySQL": ["./../patches/RMySQL.patch"],
    },
)
inherit(
    patches,
    ("3.1", "2015-05-29"),
    {
        "qtbase": ["./../patches/qtbase_1.0.9.patch"],
    },  # bc 3.1
)
inherit(patches, ("3.1", "2015-10-01"), {}, ["RMySQL"])

# inherit(
# patches,
# ("3.1", "2015-10-01"),
# {},
# [],
# )

patches = inherit_to_dict(patches)

patches_by_package_version = {}

hooks = []
inherit(
    hooks,
    ("3.1", "2015-05-28"),
    {"OpenMx": {"preInstall": ["patchShebangs configure\n"]}},
)

inherit(
    hooks,
    ("3.1", "2015-10-01"),
    {
        "curl": {"preInstall": ["patchShebangs configure\ncat configure\n"]},
        "Rblpapi": {"preInstall": ["patchShebangs configure\n"]},
        "xml2": {"preInstall": ["patchShebangs configure\n"]},
        "RMySQL": {"preInstall": ["patchShebangs configure\n"]},
    },
)
hooks = inherit_to_dict(hooks)

# these get added in addition to the release date / archive date snapshots
# because sometimes the snapshots at release are simply missing packages.
# the value is why we added them (and get's into the README.md of the downstream repo).
# extra_snapshots = {
#     "3.0": {
#         "2014-10-26": "RSQLITE 1.0.0 needed by bioassayR started being available on this date."
#     },
#     "3.1": {
#         "2015-05-02": "* Rcpp 0.11.6 required by PAA",
#         "2015-05-16": "* bamboo",
#         "2015-07-07": "* igraph 1.0.1 for NetPathMiner, BioNet",
#         "2015-07-15": "* assertive.base is required by OmicsMarkeR, shows up on 2015-07-15",
#         "2015-06-09": "* DT, required by seqplots shows up on '2015-06-09'",
#         "2015-10-01": "* changepoint 2.1.1 for NGScopy shows up",
#     },
#     "3.2": {"2016-01-10": "ggrepel was added to CRAN 2016-01-10"},
#     "3.5": {"2017-06-10": "dbplyr was added to CRAN 2017-06-09"},
# }

extra_snapshots = {}
for adict in (
    flake_info,
    excluded_packages,
    downgrades,
    comments,
    package_patches,
    additional_r_dependencies,
    native_build_inputs,
    build_inputs,
    skip_check,
    patches,
    hooks,
):
    if not isinstance(adict, dict):
        raise TypeError(adict)
    for key in adict.keys():
        if isinstance(key, tuple):
            if len(key) != 2:
                raise ValueError("Invalid spec", key)
            bc_version, date = key
            parse_date(date)
            if not bc_version in extra_snapshots:
                extra_snapshots[bc_version] = set()
            extra_snapshots[bc_version].add(date)

extra_snapshots = {k: sorted(v) for (k, v) in extra_snapshots.items()}
