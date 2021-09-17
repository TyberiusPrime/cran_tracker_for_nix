# This file defines the composition for CRAN (R) packages.

{ R, pkgs, overrides, breakpointHook }:

let
  inherit (pkgs) fetchurl stdenv lib;

  buildRPackage = pkgs.callPackage ./generic-builder.nix { inherit R; };

  # Generates package templates given per-repository settings
  #
  # some packages, e.g. cncaGUI, require X running while installation,
  # so that we use xvfb-run if requireX is true.
  mkDerive = { mkHomepage, mkUrls }:
    args:
    lib.makeOverridable ({ name, version, sha256, depends ? [ ], doCheck ? true
      , requireX ? false, broken ? false, hydraPlatforms ? R.meta.hydraPlatforms
      , nativeBuildInputs ? [ ], buildInputs ? [ ], patches ? [ ], url ? false
      , hooks ? { } }:
      buildRPackage ({
        name = name;
        version = version;
        src = fetchurl {
          inherit sha256;
          urls = mkUrls (args // { inherit name version; });
        };
        inherit doCheck requireX;
        propagatedBuildInputs = nativeBuildInputs ++ depends;
        nativeBuildInputs = nativeBuildInputs ++ depends;
        additional_buildInputs = buildInputs;
        patches = patches;
        meta.homepage = mkHomepage name;
        meta.platforms = R.meta.platforms;
        meta.hydraPlatforms = hydraPlatforms;
        meta.broken = broken;
      } // hooks));

  # Templates for generating Bioconductor and CRAN packages
  # from the name, version, sha256, and optional per-package arguments above
  #
  deriveBioc = mkDerive {
    mkHomepage = name:
      "http://bioconductor.org/packages/release/bioc/html/${name}.html";
    mkUrls = { name, version, biocVersion }: [

      "mirror://bioc/${biocVersion}/bioc/src/contrib/${name}_${version}.tar.gz"
      "mirror://bioc/${biocVersion}/bioc/src/contrib/Archive/${name}/${name}_${version}.tar.gz"
      "mirror://bioc/${biocVersion}/bioc/src/contrib/Archive/${name}_${version}.tar.gz"
      "http://bioconductor.org/packages/${biocVersion}/bioc/src/contrib/${name}_${version}.tar.gz"
    ];
  };
  deriveBiocAnn = mkDerive {
    mkHomepage = { name, ... }:
      "http://www.bioconductor.org/packages/${name}.html";
    mkUrls = { name, version, biocVersion }: [
      "mirror://bioc/${biocVersion}/data/annotation/src/contrib/${name}_${version}.tar.gz"
      "http://bioconductor.org/packages/${biocVersion}/data/annotation/src/contrib/${name}_${version}.tar.gz"
    ];
  };
  deriveBiocExp = mkDerive {
    mkHomepage = { name, ... }:
      "http://www.bioconductor.org/packages/${name}.html";
    mkUrls = { name, version, biocVersion }: [
      "mirror://bioc/${biocVersion}/data/experiment/src/contrib/${name}_${version}.tar.gz"
      "http://bioconductor.org/packages/${biocVersion}/data/experiment/src/contrib/${name}_${version}.tar.gz"
    ];
  };
  deriveCran = mkDerive {
    mkHomepage = name: snapshot:
      "http://mran.revolutionanalytics.com/snapshot/${snapshot}/web/packages/${name}/";
    mkUrls = { name, version, snapshot, url ? false }:
      if url then
        url
      else
        [
          "http://mran.revolutionanalytics.com/snapshot/${snapshot}/src/contrib/${name}_${version}.tar.gz"
          #can't use the cran Archive - they occasionally have different sha256 from the snapshots
          #we are using.
          #"http://cran.r-project.org/src/contrib/00Archive/${name}/${name}_${version}.tar.gz"
          #"mirror://cran/src/contrib/00Archive/${name}/${name}_${version}.tar.gz"
          #"mirror://cran/src/contrib/${name}_${version}.tar.gz"
        ];
  };

  defaultOverrides = old: new: old // (otherOverrides old new);

  # Recursive override pattern.
  # `_self` is a collection of packages;
  # `self` is `_self` with overridden packages;
  # packages in `_self` may depends on overridden packages.
  self = (defaultOverrides _self self) // overrides;
  _self = import ./generated/bioc-packages.nix {
    inherit self;
    inherit pkgs;
    inherit breakpointHook;
    derive = deriveBioc;
  } // import ./generated/bioc-annotation-packages.nix {
    inherit self;
    inherit pkgs;
    inherit breakpointHook;
    derive = deriveBiocAnn;
  } // import ./generated/bioc-experiment-packages.nix {
    inherit self;
    inherit pkgs;
    inherit breakpointHook;
    derive = deriveBiocExp;
  }

    // import ./generated/cran-packages.nix {
      inherit self;
      inherit pkgs;
      inherit breakpointHook;
      derive = deriveCran;
    };

  # tweaks for the individual packages and "in self" follow

  packagesWithRDepends = {
    #FactoMineR = [ self.car ];
    #pander = [ self.codetools ];
  };

  #packagesWithNativeBuildInputs = {}; # now generated lists

  #packagesWithBuildInputs = ;

  packagesToSkipCheck = [ ];

  otherOverrides = old: new: {
    xml2 = old.xml2.overrideDerivation (attrs: {
      preConfigure = "export LIBXML_INCDIR=${pkgs.libxml2}/include/libxml2";
    });

    curl = old.curl.overrideDerivation
      (attrs: { preConfigure = "export CURL_INCLUDES=${pkgs.curl}/include"; });

    #this will probably be need to be removed for later variants
    iFes = old.iFes.overrideDerivation (attrs: {
      patches = [ ./patches/iFes.patch ];
      CUDA_HOME = "${pkgs.cudatoolkit}";
    });

    RcppArmadillo = old.RcppArmadillo.overrideDerivation
      (attrs: { patchPhase = "patchShebangs configure"; });

    rpf = old.rpf.overrideDerivation
      (attrs: { patchPhase = "patchShebangs configure"; });

    BayesXsrc = old.BayesXsrc.overrideDerivation
      (attrs: { patches = [ ./patches/BayesXsrc.patch ]; });

    rJava = old.rJava.overrideDerivation (attrs: {
      preConfigure = ''
        export JAVA_CPPFLAGS=-I${pkgs.jdk}/include/
        export JAVA_HOME=${pkgs.jdk}
      '';
    });

    SJava = old.SJava.overrideDerivation (attrs: {
      preConfigure = ''
        export JAVA_CPPFLAGS=-I${pkgs.jdk}/include
        export JAVA_HOME=${pkgs.jdk}
      '';
    });

    JavaGD = old.JavaGD.overrideDerivation (attrs: {
      preConfigure = ''
        export JAVA_CPPFLAGS=-I${pkgs.jdk}/include/
        export JAVA_HOME=${pkgs.jdk}
      '';
    });

    Mposterior = old.Mposterior.overrideDerivation
      (attrs: { PKG_LIBS = "-L${pkgs.openblasCompat}/lib -lopenblas"; });

    Rmpi = old.Rmpi.overrideDerivation
      (attrs: { configureFlags = [ "--with-Rmpi-type=OPENMPI" ]; });

    Rmpfr = old.Rmpfr.overrideDerivation (attrs: {
      configureFlags = [ "--with-mpfr-include=${pkgs.mpfr}/include" ];
    });

    RVowpalWabbit = old.RVowpalWabbit.overrideDerivation (attrs: {
      configureFlags = [
        "--with-boost=${pkgs.boost.dev}"
        "--with-boost-libdir=${pkgs.boost.lib}/lib"
      ];
    });

    RAppArmor = old.RAppArmor.overrideDerivation (attrs: {
      patches = [ ./patches/RAppArmor.patch ];
      LIBAPPARMOR_HOME = "${pkgs.libapparmor}";
    });

    RMySQL = old.RMySQL.overrideDerivation (attrs: {
      #patches = [ ./patches/RMySQL.patch ];
      MYSQL_DIR = "${pkgs.mysql.lib}";
    });

    devEMF = old.devEMF.overrideDerivation
      (attrs: { NIX_CFLAGS_LINK = "-L${pkgs.xlibs.libXft}/lib -lXft"; });

    slfm = old.slfm.overrideDerivation
      (attrs: { PKG_LIBS = "-L${pkgs.openblasCompat}/lib -lopenblas"; });

    SamplerCompare = old.SamplerCompare.overrideDerivation
      (attrs: { PKG_LIBS = "-L${pkgs.openblasCompat}/lib -lopenblas"; });

    gputools = old.gputools.overrideDerivation (attrs: {
      patches = [ ./patches/gputools.patch ];
      CUDA_HOME = "${pkgs.cudatoolkit}";
    });

    # It seems that we cannot override meta attributes with overrideDerivation.
    CARramps = (old.CARramps.override {
      hydraPlatforms = stdenv.lib.platforms.none;
    }).overrideDerivation (attrs: {
      patches = [ ./patches/CARramps.patch ];
      configureFlags = [ "--with-cuda-home=${pkgs.cudatoolkit}" ];
    });

    gmatrix = old.gmatrix.overrideDerivation (attrs: {
      patches = [ ./patches/gmatrix.patch ];
      CUDA_LIB_PATH = "${pkgs.cudatoolkit}/lib64";
      R_INC_PATH = "${pkgs.R}/lib/R/include";
      CUDA_INC_PATH = "${pkgs.cudatoolkit}/usr_include";
    });

    # It seems that we cannot override meta attributes with overrideDerivation.
    rpud = (old.rpud.override {
      hydraPlatforms = stdenv.lib.platforms.none;
    }).overrideDerivation (attrs: {
      patches = [ ./patches/rpud.patch ];
      CUDA_HOME = "${pkgs.cudatoolkit}";
    });

    WideLM = old.WideLM.overrideDerivation (attrs: {
      patches = [ ./patches/WideLM.patch ];
      configureFlags = [ "--with-cuda-home=${pkgs.cudatoolkit}" ];
    });

    EMCluster = old.EMCluster.overrideDerivation
      (attrs: { patches = [ ./patches/EMCluster.patch ]; });

    spMC = old.spMC.overrideDerivation
      (attrs: { patches = [ ./patches/spMC.patch ]; });

    BayesLogit = old.BayesLogit.overrideDerivation (attrs: {
      patches = [ ./patches/BayesLogit.patch ];
      buildInputs = (attrs.buildInputs or [ ]) ++ [ pkgs.openblasCompat ];
    });

    BayesBridge = old.BayesBridge.overrideDerivation
      (attrs: { patches = [ ./patches/BayesBridge.patch ]; });

    openssl = old.openssl.overrideDerivation
      (attrs: { OPENSSL_INCLUDES = "${pkgs.openssl}/include"; });

    Rserve = old.Rserve.overrideDerivation (attrs: {
      patches = [ ./patches/Rserve.patch ];
      configureFlags = [ "--with-server" "--with-client" ];
    });

    nloptr = old.nloptr.overrideDerivation (attrs: {
      configureFlags = [
        "--with-nlopt-cflags=-I${pkgs.nlopt}/include"
        "--with-nlopt-libs='-L${pkgs.nlopt}/lib -lnlopt_cxx -lm'"
      ];
    });

    V8 = old.V8.overrideDerivation (attrs: {
      preConfigure = "export V8_INCLUDES=${pkgs.v8}/include";

    });

  };
in self
