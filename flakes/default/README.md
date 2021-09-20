Per day versioned R ecosystems.

This leverages nix to make R reproducible.

For every day that Bioconductor changed, there's a commit in this repo, with a
nix flake that allows you to install R packages and their ecosystem as you
would have been able to at this date.

'Changed' means either a bioconductor release date, an R (minor) release date, or a date on which 
any bioconductor 'software' package was replaced (only for Bioconductor releases >= 3.6,
before that no 'Archive' was available.).

This goes back to Bioconductor 3.0 - after that, no daily CRAN snapshot mirror was 
available (and the nixpkgs ecosystem also starts to be usable around that time).

See https://github.com/TyberiusPrime/cran_tracker_for_nix
for how this is being generated & additional details.


Each commit has been sucessfully build with each disjoint subset of R packages at that date.
Sometimes packages had to be downgraded, or excluded.

See excluded_packages.txt for packages not included in this build.
See downgraded_packages.txt for packages not included in this build.
