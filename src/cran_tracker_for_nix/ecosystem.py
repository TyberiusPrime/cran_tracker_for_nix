import pypipegraph2 as ppg2
import subprocess
from .bioconductor_track import BioConductorTrack
from .cran_track import CranTrack
from .common import store_path


def main():
    try:
        ppg2.new(report_done_filter=5)
        bc = BioConductorTrack()
        bc_jobs = []
        bcvs = []
        releases = list(bc.iter_releases())
        releases = [x for x in releases if x >= '3.6'][:1]
        for bcv in releases:
            print(bcv.version)
            bcvs.append(bcv)
            bc_jobs.append(bcv.update())

        def gen_cran():
            all_the_dates = set()
            for bcv in bcvs:
                all_the_dates.update([x.strftime("%Y-%m-%d") for x in bcv.get_cran_dates()])
            ct = CranTrack(sorted(all_the_dates))
            ct.update()

        ppg2.JobGeneratingJob("CRAN_gen", gen_cran).depends_on(bc_jobs)
        ppg2.run()

    finally:
        commit()


def commit():
    subprocess.check_call(["git", "add", "data"], cwd=store_path.parent)
    p = subprocess.Popen(
        ["git", "commit", "-m", "autocommit"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = p.communicate()
    if p.returncode == 0 or b"no changes added" in stdout:
        return True
    else:
        raise ValueError("git error return", p.returncode, stdout)





