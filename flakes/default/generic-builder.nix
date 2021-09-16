{ stdenv, R, xvfb_run, utillinux }:

{ name, version, buildInputs ? [ ], additional_buildInputs ? [ ], patches ? [ ]
, ... }@attrs:

stdenv.mkDerivation ({
  name = name + "-" + version;
  buildInputs = buildInputs ++ [ R ]
    ++ stdenv.lib.optionals attrs.requireX [ utillinux xvfb_run ]
    ++ additional_buildInputs;

  patches = patches;

  configurePhase = ''
    runHook preConfigure
    export R_LIBS_SITE="$R_LIBS_SITE''${R_LIBS_SITE:+:}$out/library"
    runHook postConfigure
  '';

  buildPhase = ''
    runHook preBuild
    runHook postBuild
  '';

  installFlags = (if attrs.doCheck or true then [ ] else [ "--no-test-load" ])
    ++ [
      "--byte-compile"
      "--with-keep.source"
      "--no-clean-on-error"
      "--clean"
    ];

  rCommand = if attrs.requireX or false then
  # Unfortunately, xvfb-run has a race condition even with -a option, so that
  # we acquire a lock explicitly.
    "flock ${xvfb_run} xvfb-run -a -e xvfb-error R"
  else
    "R";

  installPhase = ''
    runHook preInstall
    mkdir -p $out/library
    echo $rCommand CMD INSTALL $installFlags --configure-args="$configureFlags" -l $out/library .
    $rCommand CMD INSTALL $installFlags --configure-args="$configureFlags" -l $out/library .
    #remove date stamps
    echo "going for replacement"
    sed -i "s/^\(Built: R [0-9.]*\).*/\\1/" $out/library/${name}/DESCRIPTION
    metaname="$out/library/${name}/Meta/package.rds";
    echo "meta is $metaname"
    ${R}/bin/R -e "x=readRDS(\"$metaname\");x[[\"Built\"]][[\"Date\"]] = \"1970-01-01 00:00:01 UTC\";print(x);saveRDS(x, \"$metaname\")"

    runHook postInstall
  '';

  postFixup = ''
    if test -e $out/nix-support/propagated-native-build-inputs; then
        ln -s $out/nix-support/propagated-native-build-inputs $out/nix-support/propagated-user-env-packages
    fi
  '';

  checkPhase = ''
    # noop since R CMD INSTALL tests packages
  '';
} // attrs // {
  name = "r-" + name;

  strictDeps = true;
})
