{ stdenv, R, makeWrapper, recommendedPackages, packages, lndir, nixpkgs, lib }:

let
  # Nix fails if we add in thousands of dependencies,
  # because at some point it adds nativeBuildInputs to a bash argument list.
  # we therefore shard the list of packages, and then join the shards
  # for now, sharding on first letter is enough
  # (though we aggregate some very rare letters)
  findRInput = ''
    findRInput() {
      local -r pkg="$1"
      #echo "findRInput $pkg"
      if [[ ''${already_handled[$pkg]} != "1" ]]; then
        already_handled[$pkg]="1"
        if test -d $pkg/library/; then
          #echo "Found lib in $pkg"
          ln -s $pkg/library/* $out/lib/R/library/
        fi
        if test -f $pkg/nix-support/r_links; then 
          mapfile inputs < "$pkg/nix-support/r_links"
          for input in "''${inputs[@]}"
          do
            if [[ $input ]]; then 
              findRInput $input
            fi
          done
        fi
      fi
    }
  '';
  mkshard = a_chunk:
    let
      chunk_no = a_chunk.fst;
      subset = a_chunk.snd;
    in stdenv.mkDerivation {
      name = R.name + "-wrapper-" + builtins.toString chunk_no;
      preferLocalBuild = true;
      allowSubstitutes = false;

      nativeBuildInputs = subset;
      propagatedBuildInputs = subset;
      # propagatedNativeBuildInputs = subset;

      unpackPhase = "echo unpack \${#CMAKE_PREFIX_PATH}";
      configurePhase = "echo configure \${#CMAKE_PREFIX_PATH}";
      patchPhase = "echo patch \${#CMAKE_PREFIX_PATH}";

      buildPhase = "echo build \${#CMAKE_PREFIX_PATH}";

      checkPhase = "echo check \${#CMAKE_PREFIX_PATH}";

      #we tried findInputs, but that stopped working around 20.03
      #because the acc vars were undeclared before this phase
      preInstall = "";
      installPhase = ''
        echo "here"
        set
        echo "end set"
    #export CMAKE_PREFIX_PATH=""
        mkdir $out/nix-support -p
        mkdir $out/lib/R/library -p
        declare -A already_handled

        if [[ $nativeBuildInputs ]]; then
          echo $nativeBuildInputs| tr " " "\\n" >$out/nix-support/r_links
        fi
      '';
      postInstall = "";
      fixupPhase = ":";
      installCheckPhase = ":";

    };
  drv_compare = a: b: builtins.lessThan a.name b.name;
  all_packages = builtins.sort drv_compare
    (recommendedPackages ++ packages); # so the chunks are always the same
  upTo = with lib.lists; n: range 0 n;
  chunks = with lib.lists;
    n: xs:
    (if xs == [ ] then
      [ ]
    else

      [ (take n xs) ] ++ (chunks n (drop n xs)));
  enumerate = with lib.lists; xs: (zipLists (upTo (length xs)) xs);
  package_chunks = enumerate (chunks 100 all_packages);
  shards = builtins.map mkshard package_chunks;
  # and this is the final, aggregate everything derivation.
in stdenv.mkDerivation {
  name = R.name + "-wrapper";
  preferLocalBuild = true;
  allowSubstitutes = false;

  buildInputs = [ R nixpkgs.which ];

  paths = [ R nixpkgs.which ] ++ shards;

  nativeBuildInputs = [ makeWrapper R ] ++ shards;

  unpackPhase = ":";
  installPhase = findRInput + ''

    # we need more than just bin.
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
    declare -A already_handled
    # find out what packages we need to symlink
    for i in $nativeBuildInputs; do
      findRInput $i
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
