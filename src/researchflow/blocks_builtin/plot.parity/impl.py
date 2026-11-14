import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def parity(inputs, params, out_dir, log):
    df = pd.read_csv(inputs["predictions"].path)
    y_true = df["y_true"].to_numpy(dtype=float)
    y_pred = df["y_pred"].to_numpy(dtype=float)
    mask = np.isfinite(y_true) & np.isfinite(y_pred)
    y_true, y_pred = y_true[mask], y_pred[mask]
    if len(y_true) > params["max_points"]:
        rng = np.random.RandomState(42)
        sel = rng.choice(len(y_true), params["max_points"], replace=False)
        y_true, y_pred = y_true[sel], y_pred[sel]
    lo = float(min(y_true.min(), y_pred.min()))
    hi = float(max(y_true.max(), y_pred.max()))
    fig, ax = plt.subplots(figsize=(5, 5), dpi=150)
    ax.scatter(y_true, y_pred, s=8, alpha=0.5, edgecolors="none")
    ax.plot([lo, hi], [lo, hi], "k--", lw=1)
    ax.set_xlabel("y_true")
    ax.set_ylabel("y_pred")
    ax.set_title(params.get("title", "Parity plot"))
    ax.set_xlim(lo, hi)
    ax.set_ylim(lo, hi)
    ax.set_aspect("equal", adjustable="box")
    fig.tight_layout()
    fig.savefig(out_dir / "parity.png")
    plt.close(fig)
    log(f"parity.png（{len(y_true)} 点）")
    return {"figure": "parity.png"}
