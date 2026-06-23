"""T16 benchmark: per-document SHA vs full-catalog SHA.

Compares two context-versioning strategies over the okf/n8n catalog:

  (1) FULL     — hash every .md in okf/n8n (mirrors postal.compute_dir_sha).
  (2) SELECTION — select_tools(<task>, okf/n8n) then selection_sha of those docs.

For each strategy it reports files read, bytes read and elapsed time using a
single shared counting reader so the I/O comparison is apples-to-apples.

NOTE: on a local working copy the elapsed time is trivial; the metric that
matters is files/bytes, because in a blobless sparse clone every file read is
a blob hydration over the network. Fewer files/bytes == fewer blobs fetched.
"""
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from carta.selector import load_okf_index, select_tools, selection_sha  # noqa: E402

OKF = os.path.join(_ROOT, 'okf', 'n8n')

DEFAULT_TASK = 'create a workflow webhook set field respond'


class IOCounter:
    """Counts files and bytes seen by a single reader."""

    def __init__(self):
        self.files = 0
        self.bytes = 0

    def read(self, path):
        with open(path, 'rb') as f:
            data = f.read()
        self.files += 1
        self.bytes += len(data)
        return data

    def reset(self):
        self.files = 0
        self.bytes = 0


def _all_md_files(okf_path):
    """Sorted list of all .md files under okf_path (skills/ + tools/ + root)."""
    out = []
    for root, _dirs, names in os.walk(okf_path):
        for n in names:
            if n.endswith('.md'):
                out.append(os.path.join(root, n))
    out.sort()
    return out


def bench_full(okf_path, counter):
    """FULL strategy: hash every .md in the catalog (mirrors compute_dir_sha)."""
    import hashlib

    counter.reset()
    t0 = time.perf_counter()
    files = _all_md_files(okf_path)
    h = hashlib.sha256()
    for full in files:
        rel = os.path.relpath(full, okf_path).replace(os.sep, '/')
        data = counter.read(full)
        file_sha = hashlib.sha256(data).hexdigest()
        h.update(rel.encode('utf-8'))
        h.update(b'\0')
        h.update(file_sha.encode('utf-8'))
        h.update(b'\0')
    digest = h.hexdigest()
    elapsed = time.perf_counter() - t0
    return {
        'strategy': 'FULL',
        'files': counter.files,
        'bytes': counter.bytes,
        'time_s': elapsed,
        'digest': digest[:12],
    }


def bench_selection(okf_path, task, counter):
    """SELECTION strategy: select relevant docs, hash only those."""
    counter.reset()
    t0 = time.perf_counter()
    docs = select_tools(task, okf_path=okf_path)
    digest = selection_sha(docs, reader=counter.read)
    elapsed = time.perf_counter() - t0
    return {
        'strategy': 'SELECTION',
        'files': counter.files,
        'bytes': counter.bytes,
        'time_s': elapsed,
        'digest': digest[:12],
        'n_docs': len(docs),
    }


def _fmt_bytes(n):
    if n >= 1024:
        return f'{n / 1024:.1f} KB'
    return f'{n} B'


def main(argv):
    task = argv[1] if len(argv) > 1 else DEFAULT_TASK
    counter = IOCounter()

    full = bench_full(OKF, counter)
    sel = bench_selection(OKF, task, counter)

    total_catalog = len(_all_md_files(OKF))

    # Reduction ratios.
    file_red = (1 - sel['files'] / full['files']) * 100.0 if full['files'] else 0.0
    byte_red = (1 - sel['bytes'] / full['bytes']) * 100.0 if full['bytes'] else 0.0

    print(f"Task: {task!r}")
    print(f"Catalog: {OKF}  ({total_catalog} .md files total)\n")

    header = f"{'strategy':<12} {'files':>7} {'bytes':>12} {'time':>10} {'digest':>14}"
    print(header)
    print('-' * len(header))
    print(f"{full['strategy']:<12} {full['files']:>7} {_fmt_bytes(full['bytes']):>12} "
          f"{full['time_s']*1000:>8.2f}ms {full['digest']:>14}")
    sel_files = sel['files']
    print(f"{sel['strategy']:<12} {sel_files:>7} {_fmt_bytes(sel['bytes']):>12} "
          f"{sel['time_s']*1000:>8.2f}ms {sel['digest']:>14}")
    print()

    print(f"Verdict: SELECTION reads {sel['files']}/{full['files']} files "
          f"({file_red:.1f}% fewer) and {sel['bytes']}/{full['bytes']} bytes "
          f"({byte_red:.1f}% fewer).\n")

    print("Network projection (blobless sparse clone):")
    print(f"  FULL hidrata {full['files']} blobs ({_fmt_bytes(full['bytes'])}), "
          f"SELECTION hidrata {sel['files']} blobs ({_fmt_bytes(sel['bytes'])}), "
          f"ahorro {byte_red:.1f}%.")
    print("\nNOTE: local elapsed time is trivial; files/bytes (blobs hydrated over "
          "the network) is the metric that matters.")


if __name__ == '__main__':
    main(sys.argv)