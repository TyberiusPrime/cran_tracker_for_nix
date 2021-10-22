{ stdenv, R, xvfb_run, flock, utillinux, pkgs }:

{ name, version, buildInputs ? [ ], additional_buildInputs ? [ ], patches ? [ ]
, ... }@attrs:
let
  # needed for xvfb-run server number spread
  aThousandLocks = stdenv.mkDerivation ({
    name = "AThousandXvfbLocks-0.0.1";
    unpackPhase = ":";
    installPhase = ''
      mkdir $out -p
      for i in {1000..2000..1}
      do
         mkdir $out/$i
      done
    '';
    propagatedNativeBuildInputs = [xvfb_run flock];
    propagatedBuildInputs = [xvfb_run];
  });

in stdenv.mkDerivation ({
  name = name + "-" + version;
  buildInputs = buildInputs ++ [ R ]
    #++ stdenv.lib.optionals attrs.requireX [ utillinux xvfb_run ]
    ++ additional_buildInputs
    ++ (if attrs.requireX then [ aThousandLocks ] else [ ]);
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

  rCommand = "R";
  # Unfortunately, xvfb-run has a race condition even with -a option, so that
  # we acquire a lock explicitly.

  # that's not quite the truth. the -a relies on a shared /tmp as well.
  # and we don't have a readily available per nixbuild-process
  # number
  # but we can guess a number, and then flock only that number
  # allowing multiple instances to run in a parallel most of the time
  # and only occasionally colliding - in which case one blocks the other
  enableParallelBuilding = true;

  installPhase = if attrs.requireX or false then ''
    runHook preInstall
    mkdir -p $out/library
    export SN=$(($RANDOM % 1000+1000))

    # one shell script per level, or you go mad with escaping between
    # flock -> xvbf-run -> (xvfb | R)
    printf "#!%s\n" `${pkgs.which}/bin/which bash` > /build/run.sh
    printf "%s" "xvfb-run --auth-file=/build/.Xauthority --error-file=/build/xvfb-error --server-args=\"-screen 0, 1024x768x24 +extension GLK\" --server-num=$SN /build/run_r.sh" > /build/run.sh

    printf "#!%s\n" `${pkgs.which}/bin/which bash` > /build/run_r.sh
    printf "%s" "R CMD INSTALL $installFlags --configure-args=\"$configureFlags\" -l $out/library ." >>/build/run_r.sh

    chmod +x /build/run.sh
    chmod +x /build/run_r.sh

    flock ${aThousandLocks}/$SN /build/run.sh

    #remove date stamps
    echo "going for replacement"
    sed -i "s/^\(Built: R [0-9.]*\).*/\\1/" $out/library/${name}/DESCRIPTION
    metaname="$out/library/${name}/Meta/package.rds";
    echo "meta is $metaname"
    ${R}/bin/R -e "x=readRDS(\"$metaname\");x[[\"Built\"]][[\"Date\"]] = \"1970-01-01 00:00:01 UTC\";print(x);saveRDS(x, \"$metaname\")"

    runHook postInstall
  '' else ''
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
