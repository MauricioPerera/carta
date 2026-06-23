# benchmarks/

`bench_sha.py` compares two context-versioning strategies over the `okf/n8n`
catalog: **FULL** (hash every `.md`, mirroring `postal.compute_dir_sha`) vs
**SELECTION** (`select_tools` + `selection_sha` of only the chosen docs). It
reports files read, bytes read and elapsed time for each, plus a network
projection for a blobless sparse clone (blobs hydrated = files read).

Run it with:

```
python benchmarks/bench_sha.py ["optional task text"]
```

**Honest note:** on a local working copy the elapsed time is trivial — the
metric that actually matters is files/bytes, because in a blobless sparse clone
each file read is a blob hydrated over the network. Fewer files/bytes == fewer
blobs fetched == less network and less time on a real clone.