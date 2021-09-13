{
  description = "version a ware R wrapper";

  inputs = rec {
    nixpkgs.url =
      # 15.09 + hash changes to inconsolata and it's input file
      "github:TyberiusPrime/nixpkgs?rev=f0d6591d9c219254ff2ecd2aa4e5d22459b8cd1c";
    nixpkgs.flake = false;
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:

    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
          config = {
            allowUnfree = true;
            packageOverrides = super: {
              R = super.R.overrideDerivation (old: rec {
                name = "R-3.1.3";
                src = pkgs.fetchurl {
                  url = "http://cran.r-project.org/src/base/R-3/${name}.tar.gz";
                  sha256 =
                    "04kk6wd55bi0f0qsp98ckjxh95q2990vkgq4j83kiajvjciq7s87";
                };
                #do_chekc = false;
              });

            };
          };
        };

        R = pkgs.R;

        overrides = { };
        rPackages = import ./default_r.nix {
          inherit R;
          inherit pkgs;
          inherit overrides;
        };
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
        defaultPackage =
          rWrapper.override { packages = with rPackages; [ dplyr ] ++ rWrapper.recommendedPackages; };
      });
}
