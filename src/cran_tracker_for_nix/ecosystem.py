import pypipegraph2 as ppg2
import datetime
from pathlib import Path
import subprocess
from .bioconductor_track import BioConductorTrack
from .cran_track import CranTrack
from .common import store_path, write_json


class REcosystem:
    def __init__(self, filter_to_releases = None):
        self.bc = BioConductorTrack()
        self.filter_to_releases = filter_to_releases

    def update(self):
        try:
            ppg2.new(report_done_filter=5)
            bc_jobs = []
            bcvs = {}
            releases = list(self.bc.iter_releases())
            if self.filter_to_releases:
                releases = [x for x in releases if x.str_version in self.filter_to_releases][:1]
                if not releases:
                    raise ValueError("filtered all")
            for bcv in releases:
                print(bcv.version)
                bcvs[bcv.version] = bcv
                bc_jobs.append(bcv.update())
            self.bcvs = bcvs

            def gen_cran():
                all_the_dates = set()
                for bcv in bcvs.values():
                    all_the_dates.update(
                        [x.strftime("%Y-%m-%d") for x in bcv.get_cran_dates()]
                    )
                self.ct = CranTrack(sorted(all_the_dates))
                self.ct.update()

            ppg2.JobGeneratingJob("CRAN_gen", gen_cran).depends_on(bc_jobs)
            ppg2.run()

        finally:
            commit()

    def dump(self, date, output_folder):
        """Dump a json with all the info we need to build packages from a given date"""

        bioc_version = self.bc.date_to_version(date)
        ct = CranTrack(CranTrack.list_downloaded_snapshots())
        print(CranTrack.list_downloaded_snapshots())
        print("using bioc", bioc_version)
        r_version = self.bc.get_R_version(bioc_version)
        print("r_version", r_version)
        bioc_release = self.bc.get_release(bioc_version)
        archive_date = bioc_release.find_closest_archive_date(date)
        print("using archive date", archive_date)
        snapshot_date = bioc_release.find_closest_available_snapshot(
            archive_date, ct.snapshot_dates
        )
        print("using snapshot date", snapshot_date)
        header = {
            "R_version": r_version,
            "dump_date": date.strftime("%Y-%m-%d"),
            "archive_date": archive_date.strftime("%Y-%m-%d"),
            "snapshot_date": snapshot_date.strftime("%Y-%m-%d"),
            "sources": [
                # 0
                {"url": ct.get_url(snapshot_date), "archive": False},
                # 1
                {
                    "url": bioc_release.get_url(
                        "software",
                    ),
                    "archive": False,
                },
                # 2
                {
                    "url": bioc_release.get_url(
                        "experiment",
                    ),
                    "archive": False,
                },
                # 3
                {
                    "url": bioc_release.get_url(
                        "annotation",
                    ),
                    "archive": False,
                },
                # 4
                {
                    "url": bioc_release.get_url("software", True),
                    "archive": True,
                },
            ],
        }
        cran_packages = ct.latest_packages_at_date(snapshot_date)
        bioc_experiment_packages = bioc_release.get_packages("experiment", archive_date)
        bioc_annotation_packages = bioc_release.get_packages("annotation", archive_date)
        bioc_software_packages = bioc_release.get_packages("software", archive_date)

        all_packages = {}
        for name, v in cran_packages.items():
            all_packages[name] = {
                "name": name,
                "version": v["version"],
                "depends": sorted(set(v["imports"] + v["depends"])),
                "sha256": Path(
                    f"data/cran/sha256/{name}_{v['version']}.sha256"
                ).read_text(),
                "source": 0,
            }
        for name, v in bioc_experiment_packages.items():
            all_packages[name] = {
                "name": name,
                "version": v["version"],
                "depends": sorted(set(v["imports"] + v["depends"])),
                "sha256": Path(
                    f"data/bioconductor/{bioc_release.str_version}/sha256/{name}_{v['version']}.sha256"
                ).read_text(),
                "source": 2,
            }
        for name, v in bioc_annotation_packages.items():
            all_packages[name] = {
                "name": name,
                "version": v["version"],
                "depends": sorted(set(v["imports"] + v["depends"])),
                "sha256": Path(
                    f"data/bioconductor/{bioc_release.str_version}/sha256/{name}_{v['version']}.sha256"
                ).read_text(),
                "source": 3,
            }
        for name, v in bioc_software_packages.items():
            all_packages[name] = {
                "name": name,
                "version": v["version"],
                "depends": sorted(set(v["imports"] + v["depends"])),
                "sha256": Path(
                    f"data/bioconductor/{bioc_release.str_version}/sha256/{name}_{v['version']}.sha256"
                ).read_text(),
                "source": 4 if v.get("archive", False) else 1,
            }

        self.verify_package_tree(all_packages)
        all_packages = {
            k: all_packages[k] for k in sorted(all_packages)
        }  # enforce deterministic output order
        out = {
            "header": header,
            "packages": all_packages,
        }
        write_json(out, output_filename)

    def verify_package_tree(self, packages):
        ok = True
        for pkg_name, info in packages.items():
            k = "depends"
            for req_name in info[k]:
                if not req_name in packages:
                    print(f"{k} for {pkg_name} missing {req_name}")
                    ok = False
        if not ok:
            raise ValueError("Missing deps/imports")


def main():
    r = REcosystem(["1.8"])
    print("running update")
    r.update()
    dump_track_dir = Path('dumped')
    dump_track_dir.mkdir(exist_ok=True)
    already_dumped = [fn.name for fn in dump_track_dir.glob("*")]
    for date in r.get_cran_dates():
        if not date.strftime("%Y-%m-%d") in already_dumped:
            print('dumping', date)
            r.dump(date, Path("../r_ecosystem_track/r_ecosystem.json.gz"))
            commit('r_ecosystem.json.gz', '../r_ecosystem_track', 'Update to {date:%Y-%m-%d}')
            (dump_track_dir / f"{date:%Y-%m-%d}").write_text("")


#    r.dump(datetime.date(year=2018, month=1, day=15), Path("../r_ecosystem_track"))


def commit(add=['data'], cwd=store_path.parent, message = 'autocommit'):
    """commit our downloaded data"""
    subprocess.check_call(["git", "add"] + add, cwd=cwd)
    p = subprocess.Popen(
        ["git", "commit", "-m", message],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = p.communicate()
    if p.returncode == 0 or b"no changes added" in stdout:
        return True
    else:
        raise ValueError("git error return", p.returncode, stdout)
