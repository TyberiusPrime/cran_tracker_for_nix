import pypipegraph2 as ppg2
import collections
import json
from pathlib import Path
from lazy import lazy
import datetime
import requests
import re
from . import common


class RTracker:
    def __init__(self):
        self.store_path = (
            (common.store_path / "R").absolute().relative_to(Path(".").absolute())
        )

        (common.store_path).mkdir(exist_ok=True)
        self.cache_file = self.store_path / "rtrack_releases.json"
        self.temp_path = (
            (common.temp_path / "R").absolute().relative_to(Path(".").absolute())
        )

    def update(self):
        j1 = self.fetch_r_releases()

        def gen():
            self.fetch_shas()

        j2 = ppg2.JobGeneratingJob("gen_r_version_shas", gen).depends_on(j1)
        j3 = self.find_github_revs_touching_R_package()

        return [j1, j2, j3]

    def fetch_r_releases(self):
        majors = "3", "4"

        def fetch(output_filename):
            out = {}  # release -> date
            for m in majors:
                r = self.get_releases(m)
                out.update(r)
            common.write_json(out, output_filename)

        return ppg2.FileGeneratingJob(self.cache_file, fetch).depends_on(
            ppg2.FunctionInvariant(RTracker.get_releases),
            ppg2.ParameterInvariant("r_major_releases", majors),
        )

    @lazy
    def r_releases(self):
        return common.read_json(self.cache_file)

    def fetch_shas(self):
        res = []
        for rev in self.r_releases:
            major_version = rev[0]
            res.append(
                common.hash_job(
                    f"https://cran.r-project.org/src/base/R-{major_version}/R-{rev}.tar.gz",
                    self.store_path / f"{rev}.sha256",
                )
            )
        return res

    @staticmethod
    def get_releases(major_version):
        url = f"https://cran.r-project.org/src/base/R-{major_version}/"
        raw = requests.get(url).text
        res = re.findall(
            r'R-(\d+\.\d+\.\d+).tar.gz</a></td><td align="right">(\d{4}-\d{2}-\d{2})',
            raw,
        )
        return {x[0]: datetime.datetime.strptime(x[1], "%Y-%m-%d").date() for x in res}

    def minor_release_dates(self, r_version):
        matching = [
            date
            for (k, date) in self.r_releases.items()
            if k.startswith(r_version + ".")
        ]
        return matching

    def latest_minor_release_at_date(self, r_version, query_date):
        # k looks like 4.1.1'
        matching = [
            k
            for (k, date) in self.r_releases.items()
            if k.startswith(r_version + ".") and date <= query_date
        ]
        matching.sort(key=lambda k: common.version_to_tuple_int(k))
        if not matching:
            raise KeyError(r_version, query_date, self.r_releases)
        return matching[-1]  # the latest by date

    def find_github_revs_touching_R_package(self):
        """query github api for nixpkgs revisions that changed
        pkgs/applications/science/math/R/*, parse the versions
        as given by default.nix, and store them together with their
        commit date.

        This was only used for manual lookup
        """

        def download(output_filename):
            page = 1
            all_the_shas = []
            while True:
                url = f"http://api.github.com/repos/NixOS/nixpkgs/commits?path=pkgs/applications/science/math/R/&per_page=100&page={page}"
                r = requests.get(url)
                j = json.loads(r.text)
                if not j or page > 10:
                    break
                all_the_shas.extend(
                    [(x["sha"], x["commit"]["committer"]["date"]) for x in j]
                )
                page += 1
            common.write_json(all_the_shas, output_filename)

        input_job = ppg2.FileGeneratingJob(
            self.store_path / "nixpkgs_touching_r.json.gz", download
        ).depends_on(common.today_invariant)

        def gen_extracts(input_file=input_job.files[0]):
            (self.store_path / "nixpkgs_touching_r").mkdir(exist_ok=True)
            data = common.read_json(input_file)
            jobs = []
            for commit, date in data:

                def extract(output_filename, commit=commit, date=date):
                    r_version = self.extract_r_version(commit)
                    common.write_json(
                        {
                            "r_version": r_version,
                            "date": datetime.datetime.strptime(
                                date, "%Y-%m-%dT%H:%M:%SZ"
                            ),
                            "commit": commit,
                            "sha256": common.nix_hash_tarball_from_url(
                                f"https://github.com/NixOS/nixpkgs/tarball/{commit}",
                            ),
                            "repo": "NixOS/nixpkgs",
                        },
                        output_filename,
                    )

                jobs.append(
                    ppg2.FileGeneratingJob(
                        self.store_path / "nixpkgs_touching_r" / (commit + ".json.gz"),
                        extract,
                    ).depends_on(
                        ppg2.FunctionInvariant(RTracker.extract_r_version),
                        ppg2.FunctionInvariant(common.nix_hash_tarball_from_url),
                    )
                )

            def do_compile(output_filename, fns=[x.files[0] for x in jobs]):
                by_rev = collections.defaultdict(list)
                for fn in fns:
                    info = common.read_json(fn)
                    by_rev[info["r_version"]].append(info)
                rev_to_commit = {}
                for rev, entries in by_rev.items():
                    # entries.sort(key = lambda x: x['date']) # we sort after filtering
                    rev_to_commit[rev] = entries
                rev_to_commit = {
                    rev: entry
                    for (rev, entry) in sorted(
                        rev_to_commit.items(), key=lambda x: x[0]
                    )
                }
                common.write_json(rev_to_commit, output_filename, do_indent=True)

            ppg2.FileGeneratingJob(
                self.store_path / "nixpkgs_for_r_version.json.gz", do_compile
            ).depends_on(jobs)

        ppg2.JobGeneratingJob("gen_nix_pkgs_for_r", gen_extracts).depends_on(input_job)

    def get_sha(self, r_version):
        return Path(self.store_path / (r_version + ".sha256")).read_text()

    @staticmethod
    def extract_r_version(commit):
        url = f"https://github.com/NixOS/nixpkgs/blob/{commit}/pkgs/applications/science/math/R/default.nix?raw=true"
        r = requests.get(url)
        vers = re.findall(r'version = "(\d+\.\d+\.\d+)";', r.text)
        if vers:
            return vers[0]
        else:
            vers = re.findall(r'name = "R-(\d+\.\d+\.\d+)";', r.text)
            if vers:
                return vers[0]
            else:
                raise ValueError(f"Could not find version from {commit}")


if __name__ == "__main__":
    r = RTracker()
    # print(r.find_github_revs_touching_R_package())
    commits = common.read_json("data/R/nixpkgs_touching_r.json.gz")
    print(commits)
    for c, d in commits:
        print(c, r.extract_r_version(c))
