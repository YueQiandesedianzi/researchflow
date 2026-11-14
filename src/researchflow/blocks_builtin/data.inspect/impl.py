import json

import pandas as pd


def inspect(inputs, params, out_dir, log):
    df = pd.read_csv(inputs["dataset"].path)
    report = {
        "rows": int(len(df)),
        "n_columns": int(df.shape[1]),
        "missing_total": int(df.isna().sum().sum()),
        "columns": [str(c) for c in df.columns],
        "dtypes": {str(c): str(t) for c, t in df.dtypes.items()},
        "missing_by_column": {str(c): int(n) for c, n in df.isna().sum().items() if n},
        "duplicated_rows": int(df.duplicated().sum()),
    }
    log(f"体检: {report['rows']} 行 × {report['n_columns']} 列，"
        f"缺失 {report['missing_total']}，重复行 {report['duplicated_rows']}")
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    return {"report": "report.json"}
