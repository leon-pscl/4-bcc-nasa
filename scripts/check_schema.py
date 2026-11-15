import zipfile, tempfile, os
z = zipfile.ZipFile('E:/snapshots/cloud/processed_data_v2.zip')
for prefix in ('monthly_cells/', 'detections/'):
    names = [n for n in z.namelist() if n.startswith(prefix) and n.endswith('.parquet')]
    p = tempfile.mkdtemp()
    z.extract(names[0], p)
    f = os.path.join(p, names[0])
    f = f.replace('\\', '/')
    import duckdb
    con = duckdb.connect()
    q = "DESCRIBE SELECT * FROM read_parquet('" + f + "')"
    cols = [r[0] for r in con.execute(q).fetchall()]
    print(prefix, cols)