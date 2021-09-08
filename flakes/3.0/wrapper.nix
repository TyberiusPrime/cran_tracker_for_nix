{ stdenv, R, makeWrapper, recommendedPackages, packages, lndir, nixpkgs}:
stdenv.mkDerivation {
  name = R.name + "-wrapper";
  preferLocalBuild = true;
  allowSubstitutes = false;

  buildInputs = [R nixpkgs.which] ++ recommendedPackages ++ packages;
  paths = [ R ];

  nativeBuildInputs = [makeWrapper R];

  unpackPhase = ":";
  installPhase = ''

    #replicate symlink join
    mkdir -p $out
    for i in $paths; do
      ${lndir}/bin/lndir $i $out
    done

    cd ${R}/bin
    for exe in *; do
      rm "$out/bin/$exe"

      makeWrapper "${R}/bin/$exe" "$out/bin/$exe" \
        --prefix "R_LIBS_SITE" ":" "$R_LIBS_SITE"
    done

  '';

  # Make the list of recommended R packages accessible to other packages such as rpy2
  passthru = { inherit recommendedPackages; };

    meta = R.meta // {
      # To prevent builds on hydra
      hydraPlatforms = [];
      # prefer wrapper over the package
      priority = (R.meta.priority or 0) - 1;
    };
}
