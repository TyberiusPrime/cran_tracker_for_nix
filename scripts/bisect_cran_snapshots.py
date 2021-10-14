import sys
import re
import requests
from pathlib import Path
import cran_tracker_for_nix.common as common
import datetime


base_url = "https://mran.microsoft.com/snapshot/"

# we are not using (only) the downloaded files in data/cran
# because those are not the complete picture
# (only fetched for relevant bioconductor dates...) 


def get_data(date):
    cache_file = cache_dir / common.format_date(date)
    name_version = None
    if not cache_file.exists():
        json_file = Path("data/cran/packages/") / (
            common.format_date(date) + ".json.gz"
        )
        if json_file.exists():
            info = common.read_json(json_file)
            print("using", json_file)
            name_version = {x["name"]: x["version"] for x in info}
        else:
            print("fetch", date, end=" ")
            r = requests.get(base_url + common.format_date(date) + "/src/contrib")
            cache_file.write_text(r.text)
    else:
        print("had", date, end=" ")
    if name_version is None:
        raw = cache_file.read_text()
        if "Internal Server Error" in raw:
            raise ValueError()
        tar_gz = [x for x in re.findall(">([^<]+)", raw) if x.endswith(".tar.gz")]
        name_version = [x.split("_", 1) for x in tar_gz]
        name_version = {x[0]: x[1] for x in name_version}
    return name_version


def extract_name_and_version(date):
    name_version = get_data(date)
    if name in name_version:
        res = name_version[name].replace(".tar.gz", "")
    else:
        res = "0.0.0"
    res = common.version_to_tuple_int(res)
    print(res)
    return res


def extract_existance(date):
    name_version = get_data(date)
    if name in name_version:
        print('found at', date)
        return 1
    else:
        print('not found at', date)
        return 0


cache_dir = Path("temp/bisect")
cache_dir.mkdir(exist_ok=True)
earliest = "2014-10-01"
latest = common.format_date(datetime.date.today())

s = sys.argv[1]
if "_" in s:
    name, version = s.split("_")
    version = common.version_to_tuple_int(version)
    print("looking for", name, version)
else:
    name = s
    version = None
    print("Looking for first date for", name)

if len(sys.argv) > 2:
    latest = sys.argv[2]

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
        print("range", lo, hi, (hi - lo).days)
        mid = datemiddle(lo, hi)
        # Use __lt__ to match the logic in list.sort() and in heapq
        while True:
            try:
                if a(mid) < x:
                    lo = mid + datetime.timedelta(days=1)
                else:
                    hi = mid
                break
            except ValueError:
                print("had to go a day to right", lo, hi, mid)
                mid = mid + datetime.timedelta(days=1)
                if mid > hi:
                    raise ValueError(
                        "Went out of range while trying to find a valid value"
                    )
    return lo


if version:
    print(
        f"first rev with {version}",
        bisect_left(extract_name_and_version, version, lower, upper),
    )
else:
    when = bisect_left(extract_existance, 1, lower, upper)
    if when < datetime.date.today():
        print(f"first rev at all", when)
    else:
        print("either new today or not found")
