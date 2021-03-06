{
  description = "version a ware R wrapper";

  inputs = rec {
    nixpkgs.url =
      "github:TyberiusPrime/nixpkgs?rev=f0d6591d9c219254ff2ecd2aa4e5d22459b8cd1c";
    nixpkgs.flake = false;
    flake-utils.url = "github:numtide/flake-utils";
    flake-utils.inputs.nixpkgs.follows = "nixpkgs";
    nixpkgs_master.url = # breakpointhook is not available before 19.03
      "github:nixOS/nixpkgs?rev=e55bd22bbca511c4613a33d809870792d7968d1c";
    import-cargo.url = "github:edolstra/import-cargo";
    import-cargo.inputs.nixpkgs.follows = "nixpkgs";

  };

  outputs = { self, nixpkgs, flake-utils, nixpkgs_master, import-cargo }:

    flake-utils.lib.eachDefaultSystem (system:
      let
        inherit (import-cargo.builders) importCargo;
        pkgs = import nixpkgs {
          inherit system;
          config = {
            allowUnfree = true;
            packageOverrides = super: {
              R = super.R.overrideDerivation (old: rec {
                pname = "R";
                version = "3.1.3";
                major_version = builtins.substring 0 1 version;
                name = pname + "-" + version;

                src = pkgs.fetchurl {
                  url =
                    "http://cran.r-project.org/src/base/R-${major_version}/${name}.tar.gz";
                  sha256 =
                    "04kk6wd55bi0f0qsp98ckjxh95q2990vkgq4j83kiajvjciq7s87";
                };
                patches = [ ]; # R_patches-generated
                #additionalOverrides
              });
            };
          };
        };
        pkgs_master = import nixpkgs_master { inherit system; };
        breakpointHook = pkgs_master.breakpointHook;

        R = pkgs.R;

        overrides = { };
        rPackages = import ./default_r.nix {
          inherit R;
          inherit pkgs;
          inherit overrides;
          inherit breakpointHook;
          inherit importCargo;
          inherit system;
        };
        lib = pkgs.lib;
        rWrapper = pkgs.callPackage ./wrapper.nix {
          recommendedPackages = with rPackages; [
            boot
            class
            cluster
            codetools
            foreign
            KernSmooth
            lattice
            MASS
            Matrix
            mgcv
            # nlme
            nnet
            rpart
            spatial
            survival
          ];
          # Override this attribute to register additional libraries.
          packages = [ ];
          nixpkgs = pkgs;
        };

      in with pkgs; {
        rWrapper = rWrapper;
        rPackages = rPackages;
        defaultPackage = rWrapper.override {
          packages = with rPackages; [ dplyr ] ++ rWrapper.recommendedPackages;
        };
      });
}
