{ stdenv, R, makeWrapper, recommendedPackages, packages, lndir, nixpkgs }:

let
  # Nix fails if we add in thousands of dependencies,
  # because at some point it adds nativeBuildInputs to a bash argument list.
  # we therefore shard the list of packages, and then join the shards
  mkshart = regex: wname: packages:
    let
      shard_func = x: (builtins.match ("r-" + regex + ".*") x.name) != null;
      subset = (builtins.partition shard_func packages).right;
    in stdenv.mkDerivation {
      name = R.name + "-wrapper-" + wname;
      # preferLocalBuild = true;
      # allowSubstitutes = false;

      # propagatedNativeBuildInputs = subset;

      nativeBuildInputs = subset;
      # #paths = subset;

      # #nativeBuildInputs = [ makeWrapper R ];

       unpackPhase = ":";
       installPhase = ''
         mkdir $out/lib/R/library -p
          # find out what packages we need to symlink
          for i in $nativeBuildInputs; do
            findInputs $i apkg "propagated-native-build-inputs"
          done

          for i in $apkg; do
            if test -d $i/library/; then
              ln -s $i/library/* $out/lib/R/library/
            fi
          done
       '';

      #   echo "Hello world"

      #   #replicate symlink join
      #   mkdir -p $out/lib/R
      #   for i in $paths; do
      #     ${lndir}/bin/lndir $i $out/lib/R
      #   done
      #   pkgs=""
      #   for i in $nativeBuildInputs; do
      #     findInputs $i;
      #   done
      #   echo "pkgs" $pkgs;
      #   echo "buildInputs" $buildInputs
      #   echo "nativeBuildInputs" $nativeBuildInputs
      #   ls -la $out
      #   ls -la $out/lib/R
      #   exit 1
      # '';

      # meta = R.meta // {
      #   # To prevent builds on hydra
      #   hydraPlatforms = [ ];
      # };
    };
  all_packages = recommendedPackages ++ packages;
  shards = [
    # initial examination of the R package set 
    # suggests that this should produce sub 1000 package 
    # sets.
    (mkshart "[Aa]" "A" all_packages)
    (mkshart "[Bb]" "B" all_packages)
    (mkshart "[Cc]" "C" all_packages)
    (mkshart "[Dd]" "D" all_packages)
    (mkshart "[Ee]" "E" all_packages)
    (mkshart "[Ff]" "F" all_packages)
    (mkshart "[Gg]" "G" all_packages)
    (mkshart "[Hh]" "H" all_packages)
    (mkshart "[Ii]" "I" all_packages)
    (mkshart "[Jj]" "J" all_packages)
    (mkshart "[Kk]" "K" all_packages)
    (mkshart "[Ll]" "L" all_packages)
    (mkshart "[Mm]" "M" all_packages)
    (mkshart "[Nn]" "N" all_packages)
    (mkshart "[Oo]" "O" all_packages)
    (mkshart "[Pp]" "P" all_packages)
    (mkshart "[Qq]" "Q" all_packages)
    (mkshart "[Rr]" "R" all_packages)
    (mkshart "[Ss]" "S" all_packages)
    (mkshart "[Tt]" "T" all_packages)
    (mkshart "[Uu]" "U" all_packages)
    (mkshart "[Vv]" "V" all_packages)
    (mkshart "[Ww]" "W" all_packages)
    (mkshart "[XxYyZz]" "XYZ" all_packages)
    (mkshart "[XYZ]" "XYZ" all_packages)
    (mkshart "[^A-Za-z]" "other" all_packages)
  ];
in stdenv.mkDerivation {
  name = R.name + "-wrapper";
  preferLocalBuild = true;
  allowSubstitutes = false;

  buildInputs = [ R nixpkgs.which ];

  paths = [ R nixpkgs.which ] ++ shards;

  nativeBuildInputs = [ makeWrapper R ] ++ shards;

  unpackPhase = ":";
  installPhase = ''

    #wee need more than just bin.
    mkdir -p $out/bin
    for i in $paths; do
      ${lndir}/bin/lndir $i $out
    done

    # make wrappers setting env variables
    cd ${R}/bin
    for exe in *; do
      rm "$out/bin/$exe"

      makeWrapper "${R}/bin/$exe" "$out/bin/$exe" \
        --set R_LIBS_SITE $out/lib/R/library \
        --set LC_ALL C
    done

    # find out what packages we need to symlink
    for i in $nativeBuildInputs; do
      findInputs $i apkg "propagated-native-build-inputs"
    done

    for i in $nativeBuildInputs;  do
      if test -d $i/lib/R/library; then
        ${lndir}/bin/lndir $i/lib/R/library $out/lib/R/library/
      fi
    done
  '';

  # Make the list of recommended R packages accessible to other packages such as rpy2
  passthru = { inherit recommendedPackages; };

  meta = R.meta // {
    # To prevent builds on hydra
    hydraPlatforms = [ ];
    # prefer wrapper over the package
    priority = (R.meta.priority or 0) - 1;
  };
}
