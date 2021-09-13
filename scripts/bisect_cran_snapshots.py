import sys
import re
import requests
from pathlib import Path
import cran_tracker_for_nix.common as common
import datetime


base_url = "https://mran.microsoft.com/snapshot/"


def extract_name_and_version(date):
    cache_file = cache_dir / common.format_date(date)
    if not cache_file.exists():
        print("fetch", date)
        r = requests.get(base_url + common.format_date(date) + "/src/contrib")
        cache_file.write_text(r.text)
    print('had', date)
    raw = cache_file.read_text()
    tar_gz = [x for x in re.findall(">([^<]+)", raw) if x.endswith(".tar.gz")]
    name_version = [x.split("_", 1) for x in tar_gz]
    name_version = {x[0]: x[1] for x in name_version}
    if name in name_version:
        res =  name_version[name].replace(".tar.gz", "")
    else:
        res =  "0.0.0"
    return common.version_to_tuple_int(res)


cache_dir = Path("temp/bisect")
cache_dir.mkdir(exist_ok=True)
earliest = "2014-10-01"
latest = common.format_date(datetime.date.today())

name, version = sys.argv[1].split("_")
version = common.version_to_tuple_int(version)

lower = common.parse_date(earliest)
upper = common.parse_date(latest)


def datemiddle(lower, upper):
    lt = datetime.datetime.combine(lower, datetime.datetime.min.time()).timestamp()
    up = datetime.datetime.combine(upper, datetime.datetime.min.time()).timestamp()
    middle = (lt + up) / 2
    return datetime.datetime.fromtimestamp(middle).date()


def bisect_left(a, x, lo, hi):
    """Return the index where to insert item x in list a, assuming a is sorted.
    The return value i is such that all e in a[:i] have e < x, and all e in
    a[i:] have e >= x.  So if x already appears in the list, a.insert(x) will
    insert just before the leftmost x already there.
    Optional args lo (default 0) and hi (default len(a)) bound the
    slice of a to be searched.
    """

    while lo < hi:
        mid = datemiddle(lo, hi)
        # Use __lt__ to match the logic in list.sort() and in heapq
        if a(mid) < x: lo = mid+datetime.timedelta(days=1)
        else: hi = mid
    return lo


print(f'first rev with {version}', bisect_left(extract_name_and_version,
        version, lower, upper))
