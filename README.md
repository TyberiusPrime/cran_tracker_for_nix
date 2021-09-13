# Introduction

`cran_tracker_for_nix` is an attempt to hammer the R ecosystem into
something reproducible.

The approach is conceptually simple: for each date that Bioconductor
changes, we capture the set of packages&versions it provides,
along with the packages available at CRAN on that date (using the MRAN CRAN daily mirror).

For earlier Bioconductor versions, that's the release dates only.
For later (3.6+), that's every time they moved a package into 'src/contrib/Archive'
during a release's lifetime.

The whole affair is slightly complicated because there isn't necessarily
a consistent view of the R ecosystem on any given date.  For example: 

 * Sometimes bioconductor refers to packages that were not actually on CRAN until a few weeks/months later.
 * Sometimes CRAN lists the package, but the mirror does not have it.
 * A tiny number of dependencies were never on CRAN/bioconductor.
 * Some minor-minor version packages have disappeared without a trace.
 * Bioconducer packages have been deprecated, but their dependants have not been pruned.

This has been worked around by simply blacklisting packages at certain dates.

The whole thing get's parsed, every sha256 of a mentioned package get's calculated,
and a comprehensive json per date is output into a seperate git repo, one commit per date.


# Usage:
flake.nix:
```nix
{
  description = "test flake to check package build";

  inputs = rec {
    r_flake.url = "github:TyberiusPrime/r_ecosystem?rev=...";
  };

  outputs = { self, r_flake}: {
    defaultPackage.x86_64-linux = with r_flake;
      rWrapper.x86_64-linux.override {
        packages = with rPackages.x86_64-linux; [ formula_tools operator_tools ];
      };
  };
}
```


# Limitations:

 * we only start at Bioconductor 3.0, for MRAN, the microsoft daily cran mirror has no older packages.
   This could be worked around with by using CRAN's src/contrib/Archive, but we'd have to recreate the dependency graph as well
    and going even further in the c ecosystem get's increasingly tedious.
 * This isn't 'mix and match'. You get one set of packages per date.
 * Everything outside of CRAN/Bioconductor was not considered. 
 * If I failed to find a dependency within a few minutes, the package was blacklisted.
 * For Bioconductor 3.0 (Oct '14), the C-ecosystem is actually from Sep '15, but with R 3.1.3. Couldn't get the nixpkgs before 15.09 to compile, and R 3.1.1 won't pass it's tests (see https://stat.ethz.ch/pipermail/r-devel/2014-November/070028.html)


# Internals

We use pypipegraph2 to keep track of what needs doing, 
and we've made the slightly unconventional choice to commit all the downloaded metadata
and the pipegraph-history as well to this repo. The plan is to run the updates 
daily on some CI.







