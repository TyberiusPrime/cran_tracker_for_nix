# `cran_tracker_for_nix`

`cran_tracker_for_nix` is an attempt to hammer the R ecosystem into
something reproducible.

The approach is conceptually simple: for each date that Bioconductor
changes, we capture the set of packages&versions it provides,
along with the packages available at CRAN on that date (using the MRAN CRAN daily mirror).

For earlier Bioconductor versions, that's the release dates only.
For later (3.6+), that's everytime they moved a package into 'src/contrib/Archive'
during a release's lifetime.

The whole affair is slightly complicated because there isn't necessarily
a consistent view of the R ecosystem on any given date. 

 * Sometimes bioconductor refers to packages that were not actually on CRAN until a few weeks/months later.
 * Sometimes CRAN lists the package, but the mirror does not have it.
 * A tiny number of dependencies were never on CRAN/bioconductor.
 * Some minor-minor version packages have disappeared without a trace.
 * Bioconducer packages have been deprecated, but their dependants have not been pruned.

This has been worked around by simply blacklisting packages at certain dates.

The whole thing get's parsed, every sha256 of a mentioned package get's calculated,
and a comprehensive json per date is output into a seperate git repo, one commit per date.


Limitations:

 * we only start at Bioconductor 3.0, for MRAN, the microsoft daily cran mirror has no older packages.
   This could be worked around with by using CRAN's src/contrib/Archive, but we'd have to recrate the dependency graph as well
 * This isn't 'mix and match'. You get one set of packages per date.
 * Everything outside of CRAN/Bioconductor was not considered. 
 * If I failed to find a dependency within a few minutes, the package was blacklisted.
 * 






